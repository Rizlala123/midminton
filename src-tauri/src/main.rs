#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde_json::{json, Value};
use std::{collections::HashSet, fs, io::{BufRead, BufReader, Read, Write}, path::PathBuf,
          process::{Command, Stdio}, sync::Mutex};
use tauri::{Emitter, Manager, State};
use tauri_plugin_dialog::DialogExt;

#[derive(Default)]
struct DesktopState {
    projects: Mutex<HashSet<PathBuf>>,
    selected: Mutex<HashSet<PathBuf>>,
    active: Mutex<Option<PathBuf>>,
}

fn lock_error<T>(_: std::sync::PoisonError<T>) -> String { "Desktop state unavailable; restart the app".into() }

fn worker_root(app: &tauri::AppHandle) -> PathBuf {
    if cfg!(debug_assertions) { PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../python") }
    else { app.path().resource_dir().unwrap_or_default().join("python") }
}

fn python(app: &tauri::AppHandle) -> PathBuf {
    if let Some(path) = std::env::var_os("MIDMINTON_PYTHON") { return path.into(); }
    let local = worker_root(app).join("../.venv/Scripts/python.exe");
    if local.is_file() { local } else { PathBuf::from("python") }
}

fn scope_result(app: &tauri::AppHandle, project: &PathBuf, result: &Value) -> Result<(), String> {
    if let Some(video) = result.get("video").and_then(Value::as_str) {
        let path = PathBuf::from(video).canonicalize().map_err(|e| e.to_string())?;
        // Project opening is a user-authorized action. Grant just the declared media.
        app.asset_protocol_scope().allow_file(path).map_err(|e| e.to_string())?;
    }
    if let Some(frames) = result.get("timeline").and_then(Value::as_array) {
        for frame in frames {
            if let Some(path) = frame.get("path").and_then(Value::as_str) {
                let path = PathBuf::from(path).canonicalize().map_err(|e| e.to_string())?;
                if !path.starts_with(project) { return Err("Scoreboard file outside project".into()); }
                app.asset_protocol_scope().allow_file(path).map_err(|e| e.to_string())?;
            }
        }
    }
    Ok(())
}

fn call_worker(app: &tauri::AppHandle, request: Value, broadcast: bool) -> Result<Value, String> {
    let mut command = Command::new(python(app));
    command.args(["-u", "-m", "midminton.worker"]).env("PYTHONPATH", worker_root(app))
        .env("PYTHONIOENCODING", "utf-8").stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped());
    #[cfg(windows)] {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000); // CREATE_NO_WINDOW
    }
    let mut child = command.spawn().map_err(|e| format!("Cannot start Python. Set MIDMINTON_PYTHON to the target PC virtualenv interpreter: {e}"))?;
    if let Some(mut input) = child.stdin.take() {
        writeln!(input, "{}", request).map_err(|e| e.to_string())?;
    }
    // Drain stderr concurrently, retaining at most 32 KiB; no pipe deadlock.
    let stderr = child.stderr.take().ok_or("Missing worker stderr")?;
    let errors = std::thread::spawn(move || {
        let mut tail = Vec::new();
        for byte in stderr.bytes().flatten() {
            tail.push(byte);
            if tail.len() > 32768 { tail.drain(..16384); }
        }
        String::from_utf8_lossy(&tail).into_owned()
    });
    let output = child.stdout.take().ok_or("Missing worker stdout")?;
    let mut final_result = None;
    let mut failure = None;
    for line in BufReader::new(output).lines() {
        let line = line.map_err(|e| e.to_string())?;
        let Ok(message) = serde_json::from_str::<Value>(&line) else { continue; };
        if broadcast { let _ = app.emit("worker-message", &message); }
        match message.get("type").and_then(Value::as_str) {
            Some("result") => final_result = message.get("data").cloned(),
            Some("error") => failure = Some(message["message"].as_str().unwrap_or("Worker failed").to_string()),
            _ => {}
        }
    }
    let status = child.wait().map_err(|e| e.to_string())?;
    let detail = errors.join().unwrap_or_default();
    if let Some(message) = failure { return Err(message); }
    if !status.success() { return Err(format!("Python worker exited: {detail}")); }
    final_result.ok_or_else(|| format!("No worker result. Check interpreter/packages: {detail}"))
}

#[tauri::command]
async fn pick_file(app: tauri::AppHandle, state: State<'_, DesktopState>, kind: String) -> Result<Option<String>, String> {
    let handle = app.clone();
    let selected = tauri::async_runtime::spawn_blocking(move || {
        let dialog = handle.dialog().file();
        let dialog = match kind.as_str() {
            "video" => dialog.add_filter("Video", &["mp4", "mov", "mkv", "avi", "webm"]),
            "project" => dialog.add_filter("Midminton project", &["sqlite3"]),
            _ => dialog.add_filter("Model manifest", &["json"]),
        };
        dialog.blocking_pick_file()
    }).await.map_err(|e| e.to_string())?;
    if let Some(file) = selected {
        let path = file.into_path().map_err(|e| e.to_string())?.canonicalize().map_err(|e| e.to_string())?;
        state.selected.lock().map_err(lock_error)?.insert(path.clone());
        Ok(Some(path.to_string_lossy().into_owned()))
    } else { Ok(None) }
}

#[tauri::command]
async fn open_project(app: tauri::AppHandle, state: State<'_, DesktopState>, path: String, create: bool) -> Result<Value, String> {
    let source = PathBuf::from(path).canonicalize().map_err(|e| e.to_string())?;
    if !state.selected.lock().map_err(lock_error)?.contains(&source) { return Err("Select the file with the native picker first".into()); }
    if !create && source.file_name().and_then(|name| name.to_str()) != Some("project.sqlite3") {
        return Err("Select the project's project.sqlite3 file".into());
    }
    let project = if create {
        let base = app.path().app_local_data_dir().map_err(|e| e.to_string())?.join("projects");
        fs::create_dir_all(&base).map_err(|e| e.to_string())?;
        let id = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_err(|e| e.to_string())?.as_nanos();
        let path = base.join(id.to_string());
        fs::create_dir(&path).map_err(|e| e.to_string())?;
        path.canonicalize().map_err(|e| e.to_string())?
    } else { source.parent().ok_or("Invalid project path")?.to_path_buf() };
    let request = json!({"action": if create {"create"} else {"load"}, "project": project, "video": source});
    let handle = app.clone();
    let result = tauri::async_runtime::spawn_blocking(move || call_worker(&handle, request, false)).await.map_err(|e| e.to_string())??;
    scope_result(&app, &project, &result)?;
    state.projects.lock().map_err(lock_error)?.insert(project);
    Ok(result)
}

#[tauri::command]
async fn request(app: tauri::AppHandle, state: State<'_, DesktopState>, mut payload: Value) -> Result<Value, String> {
    let action = payload["action"].as_str().ok_or("Missing action")?.to_owned();
    if action == "diagnostics" {
        return tauri::async_runtime::spawn_blocking(move || call_worker(&app, json!({"action":"diagnostics"}), false)).await.map_err(|e| e.to_string())?;
    }
    if !["load", "edit", "history", "prepare", "analyse", "suggest", "export"].contains(&action.as_str()) { return Err("Unsupported action".into()); }
    let project = PathBuf::from(payload["project"].as_str().ok_or("Missing project")?).canonicalize().map_err(|e| e.to_string())?;
    if !state.projects.lock().map_err(lock_error)?.contains(&project) { return Err("Open this project first".into()); }
    payload["project"] = json!(project);
    let long = ["prepare", "analyse", "suggest", "export"].contains(&action.as_str());
    if long {
        let mut active = state.active.lock().map_err(lock_error)?;
        if active.is_some() { return Err("Another processing job is running".into()); }
        let cancel = project.join("cancel.request");
        if cancel.exists() { fs::remove_file(cancel).map_err(|e| e.to_string())?; }
        *active = Some(project.clone());
    }
    let handle = app.clone();
    let result = tauri::async_runtime::spawn_blocking(move || call_worker(&handle, payload, long)).await;
    if long { *state.active.lock().map_err(lock_error)? = None; }
    let result = result.map_err(|e| e.to_string())??;
    scope_result(&app, &project, &result)?;
    Ok(result)
}

#[tauri::command]
fn cancel(state: State<'_, DesktopState>) -> Result<(), String> {
    if let Some(path) = state.active.lock().map_err(lock_error)?.as_ref() {
        fs::write(path.join("cancel.request"), b"cancel").map_err(|e| e.to_string())?;
    }
    Ok(())
}

fn main() {
    tauri::Builder::default().plugin(tauri_plugin_dialog::init()).manage(DesktopState::default())
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                let active = window.state::<DesktopState>().active.lock().ok().and_then(|guard| guard.clone());
                if let Some(project) = active {
                    api.prevent_close();
                    let _ = fs::write(project.join("cancel.request"), b"cancel");
                    let _ = window.emit("worker-message", json!({"type":"progress", "stage":"cancelling",
                        "fraction":0, "message":"Cancelling the job before closing. Close again after it stops."}));
                }
            }
        })
        .invoke_handler(tauri::generate_handler![pick_file, open_project, request, cancel])
        .run(tauri::generate_context!()).expect("Unable to launch Midminton desktop");
}
