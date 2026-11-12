import {invoke, convertFileSrc} from "@tauri-apps/api/core";
import {listen} from "@tauri-apps/api/event";
import type {Anchor, Point, ProjectView} from "./types";
import "./style.css";

const app = document.querySelector<HTMLDivElement>("#app")!;
app.innerHTML = `
<header><div class="brand"><span class="mark">M</span><div><strong>MIDMINTON</strong><small>LOCAL MATCH STUDIO / PHASE 01</small></div></div>
<nav><button id="import">Select video</button><button id="open" class="quiet">Open project</button><button id="diagnostics" class="quiet">Check setup</button></nav></header>
<main><section class="workspace"><div class="section-title"><div><p class="eyebrow">YOUR COURT. YOUR DATA.</p><h1>Watch it. Understand it.</h1></div><span class="badge">Offline processing</span></div>
<div id="stage"><video id="video" controls preload="metadata"></video><canvas id="canvas" aria-label="Court and player marking surface"></canvas><img id="scoreboard" alt="Current match score" hidden><div id="empty"><strong>Your next match starts here.</strong><p>Select a local recording. The original stays untouched.</p></div></div>
<p id="clock" class="muted">No video selected</p>
<div class="toolbar"><button id="prepare" data-project>1 · Prepare video</button><button id="analyse" data-project>2 · Analyse locally</button><button id="export" data-project>3 · Export scored video</button><button id="cancel" class="danger" disabled>Cancel job</button></div>
<section class="job" aria-live="polite"><div><strong id="job-title">Ready when you are</strong><span id="fraction"></span></div><progress id="progress" max="1" value="0"></progress><p id="status">Install the worker and local models on the testing PC before analysis.</p></section>
<details open><summary>Set up this match</summary><p class="muted">At the opening frame mark court corners: near-left, near-right, far-right, far-left. Draw P1/P2 = A and P3/P4 = B; singles uses P1/P3. To recover a player after occlusion, pause later and draw that same ID again, then save and rerun analysis.</p>
<div class="toolbar"><button id="court" data-project>Mark court (4 clicks)</button><button id="roster" data-project>Suggest players</button><select id="player" aria-label="Player box to mark"><option value="">Draw player box…</option><option>P1</option><option>P2</option><option>P3</option><option>P4</option></select><button id="clear-marks" data-project class="quiet">Clear marks</button></div>
<div class="settings-grid"><label>Match type<select id="discipline"><option value="auto">Suggest / uncertain</option><option value="singles">Singles</option><option value="doubles">Doubles</option></select></label><label>First serving team<select id="server"><option>A</option><option>B</option></select></label><label>Initial serving player<select id="initial-server"><option>P1</option><option>P2</option><option>P3</option><option>P4</option></select></label><label>Initial receiver<select id="initial-receiver"><option>P3</option><option>P4</option><option>P1</option><option>P2</option></select></label>
<label>Starting A score<input id="initial-a" type="number" min="0" max="999" value="0"></label><label>Starting B score<input id="initial-b" type="number" min="0" max="999" value="0"></label><label>Game target<input id="target" type="number" min="1" value="21"></label><label>Score cap<input id="cap" type="number" min="1" value="30"></label>
</div><div class="model-row"><button id="people-model" data-project class="quiet">Person model manifest</button><output id="people-path">Not selected</output></div><div class="model-row"><button id="shuttle-model" data-project class="quiet">Shuttle model manifest</button><output id="shuttle-path">Not selected</output></div>
<label class="check"><input id="gpu" type="checkbox">Use CUDA for shuttle inference (4 GB budget; requires GPU runtime)</label><label class="check"><input id="auto-accept" type="checkbox">Experimental: accept sufficiently strong next-serve winner proposals automatically</label><p class="muted">Winner suggestions are heuristics and require target-video validation. Unseen endings and spectator interruptions stay reviewable.</p><button id="save-settings" data-project>Save match setup</button></details>
</section>
<aside><div class="section-title"><div><p class="eyebrow">THE MATCH RECORD</p><h2>Point timeline</h2></div><span id="revision" class="badge">—</span></div>
<div class="toolbar"><button id="undo" data-project class="quiet">Undo</button><button id="redo" data-project class="quiet">Redo</button></div>
<form id="point-form"><input id="point-id" type="hidden"><label>Score transition time (seconds)<input id="point-time" type="number" step="0.001" min="0" required value="0"></label><div class="toolbar"><button type="button" id="use-time" class="quiet">Use video time</button><button type="button" id="new-point" class="quiet">New point</button></div><label>Point outcome<select id="outcome"><option value="A">Team A wins</option><option value="B">Team B wins</option><option value="pending">Unresolved / hidden</option><option value="replay">Replay / no point</option></select></label><button data-project type="submit">Save / confirm point</button></form>
<details><summary>Trusted score checkpoint</summary><p class="muted">Restores score certainty at this time. It does not invent missing shots. Check doubles serving identity after a checkpoint.</p><div class="settings-grid"><label>A<input id="checkpoint-a" type="number" min="0" value="0"></label><label>B<input id="checkpoint-b" type="number" min="0" value="0"></label><label>Game<input id="checkpoint-game" type="number" min="1" value="1"></label><label>Server<select id="checkpoint-server"><option>A</option><option>B</option></select></label></div><button id="checkpoint" data-project>Set at video time</button><div id="checkpoint-list"></div></details>
<div id="score-info" class="muted"></div><div id="points"><p class="empty-list">No points yet. Add one manually or analyse your recording.</p></div><details><summary>Contact / hitter proposals</summary><p class="muted">Trajectory reversals can miss or falsely suggest contacts. Unknown hitters stay unknown.</p><div id="contacts"></div></details><p id="project-path" class="path"></p>
</aside></main><footer>LOCAL FIRST · Originals preserved · Manual decisions stay yours</footer>`;

function element<T extends HTMLElement = HTMLElement>(id: string): T {
  return document.getElementById(id) as T;
}
const video = element<HTMLVideoElement>("video");
const canvas = element<HTMLCanvasElement>("canvas");
const overlay = element<HTMLImageElement>("scoreboard");
let view: ProjectView | null = null;
let busy = false;
let calibration: number[][] = [];
let anchors: Anchor[] = [];
let reanchors: Anchor[] = [];
let models: Record<string, string> = {};
let marking = "";
let drag: number[] | null = null;
let currentSprite = "";

function status(message: string, error = false) {
  element("status").textContent = message;
  element("status").classList.toggle("error", error);
}
function value(id: string) { return element<HTMLInputElement>(id).value; }
function number(id: string) {
  const n = Number(value(id));
  if (!Number.isFinite(n) || n < 0) throw new Error("Enter a non-negative number");
  return n;
}
function controls() {
  document.querySelectorAll<HTMLButtonElement>("[data-project]").forEach(button => button.disabled = !view || busy);
  for (const id of ["import", "open", "diagnostics"]) element<HTMLButtonElement>(id).disabled = busy;
  element<HTMLButtonElement>("cancel").disabled = !busy;
}
async function guarded(action: () => Promise<void>) {
  if (busy) return;
  busy = true; controls();
  try { await action(); } catch (error) { status(String(error), true); }
  finally { busy = false; controls(); }
}
async function request(payload: Record<string, unknown>) {
  if (!view) throw new Error("Open a match first");
  return invoke<ProjectView>("request", {payload: {...payload, project: view.project}});
}
function apply(next: ProjectView) {
  view = next;
  const doc = next.document;
  calibration = structuredClone(doc.calibration);
  anchors = structuredClone(doc.anchors);
  reanchors = structuredClone(doc.reanchors || []);
  models = {...doc.models};
  const src = convertFileSrc(next.video);
  if (video.getAttribute("src") !== src) { video.src = src; video.load(); }
  element("empty").hidden = true;
  for (const [id, input] of Object.entries({discipline: doc.discipline, server: doc.rules.server,
      "initial-server": doc.rules.initial_server, "initial-receiver": doc.rules.initial_receiver,
      "initial-a": doc.rules.initial[0], "initial-b": doc.rules.initial[1], target: doc.rules.target, cap: doc.rules.cap})) {
    element<HTMLInputElement>(id).value = String(input);
  }
  element<HTMLInputElement>("gpu").checked = doc.analysis_options.gpu;
  element<HTMLInputElement>("auto-accept").checked = !!doc.analysis_options.auto_accept;
  element("people-path").textContent = models.people || "Not selected";
  element("shuttle-path").textContent = models.shuttle || "Not selected";
  element("revision").textContent = `rev ${doc.revision}`;
  element("project-path").textContent = next.project;
  renderPoints(); drawMarks(); updateScore(); controls();
}
function renderPoints() {
  const list = element("points"); list.replaceChildren();
  for (const point of [...view!.document.events].sort((a,b) => a.time-b.time || a.id.localeCompare(b.id))) {
    const card = document.createElement("article"); card.className = "point";
    const title = document.createElement("button"); title.className = "point-title";
    title.textContent = `${formatTime(point.time)} · ${point.disposition === "point_awarded" ? `Team ${point.winner}` : point.disposition === "replay/no_point" ? "Replay / no point" : "Needs review"}`;
    title.onclick = () => { video.currentTime = point.time; editPoint(point); };
    const meta = document.createElement("small"); meta.textContent = `${point.origin || "manual"} ${point.locked ? "· locked" : "· proposal"} ${point.suggested_winner ? `· suggested ${point.suggested_winner}` : ""} ${point.contaminated ? "· visibility affected" : ""} ${point.evidence || ""}`;
    const remove = document.createElement("button"); remove.className = "quiet delete"; remove.textContent = "Delete";
    remove.disabled = busy;
    remove.dataset.project = "";
    remove.onclick = () => void guarded(async () => { apply(await request({action:"edit", operation:"delete", payload:{id:point.id}, revision:view!.document.revision})); });
    card.append(title, meta, remove); list.append(card);
  }
  const cps = element("checkpoint-list"); cps.replaceChildren();
  for (const checkpoint of view!.document.checkpoints) {
    const button = document.createElement("button"); button.className = "quiet";
    button.textContent = `${formatTime(checkpoint.time)} · ${checkpoint.score.join("–")} · Remove checkpoint`;
    button.onclick = () => void guarded(async () => apply(await request({action:"edit",operation:"delete",payload:{id:checkpoint.id},revision:view!.document.revision})));
    cps.append(button);
  }
  const contacts = element("contacts"); contacts.replaceChildren();
  for (const contact of view!.contacts || []) {
    const button = document.createElement("button"); button.className = "quiet contact";
    button.textContent = `${formatTime(contact.time)} · ${contact.hitter || "Unknown hitter"}${contact.contaminated ? " · obstruction" : ""}`;
    button.onclick = () => { video.currentTime = contact.time; };
    contacts.append(button);
  }
}
function editPoint(point: Point) {
  element<HTMLInputElement>("point-id").value = point.id;
  element<HTMLInputElement>("point-time").value = String(point.time);
  element<HTMLSelectElement>("outcome").value = point.disposition === "point_awarded" ? point.winner! : point.disposition === "replay/no_point" ? "replay" : "pending";
}
function formatTime(seconds: number) { return `${Math.floor(seconds/60)}:${Math.floor(seconds%60).toString().padStart(2,"0")}`; }
function displayTime() { return Math.max(0, Math.min(video.currentTime, (view?.document.media.duration || 0)-0.1)); }
function updateScore() {
  element("clock").textContent = `${formatTime(video.currentTime)} / ${formatTime(video.duration || 0)}`;
  if (!view?.timeline.length) return;
  const timeline = view.timeline;
  let lo = 0, hi = timeline.length;
  while (lo < hi) { const mid = (lo+hi) >>> 1; if (timeline[mid].time <= video.currentTime) lo = mid+1; else hi = mid; }
  const entry = timeline[Math.max(0, lo-1)];
  if (entry.path !== currentSprite) { overlay.src = convertFileSrc(entry.path); currentSprite = entry.path; }
  overlay.hidden = false;
  element("score-info").textContent = entry.state.conflicts.join(" · ") || (entry.state.provisional ? "Score provisional: resolve the earlier gap or add a trusted checkpoint." : `Serving: ${entry.state.serving_player || entry.state.server}`);
}
function drawMarks() {
  const context = canvas.getContext("2d")!;
  context.clearRect(0,0,canvas.width,canvas.height);
  context.lineWidth = Math.max(2,canvas.width/500);
  context.strokeStyle = "#68e4c4"; context.fillStyle = "#68e4c4";
  if (calibration.length) {
    context.beginPath(); calibration.forEach(([x,y],i) => i ? context.lineTo(x*canvas.width,y*canvas.height) : context.moveTo(x*canvas.width,y*canvas.height));
    if (calibration.length === 4) context.closePath(); context.stroke();
    calibration.forEach(([x,y],i) => { context.beginPath(); context.arc(x*canvas.width,y*canvas.height,6,0,Math.PI*2); context.fill(); context.fillText(String(i+1),x*canvas.width+8,y*canvas.height); });
  }
  const active = new Map(anchors.map(a => [a.id,a]));
  for (const anchor of reanchors.filter(a => (a.time || 0) <= video.currentTime).sort((a,b)=>(a.time || 0)-(b.time || 0))) active.set(anchor.id,anchor);
  for (const anchor of active.values()) {
    const [x1,y1,x2,y2] = anchor.box; context.strokeStyle = anchor.team === "A" ? "#68e4c4" : "#ffc87c";
    context.strokeRect(x1*canvas.width,y1*canvas.height,(x2-x1)*canvas.width,(y2-y1)*canvas.height);
    context.font = `${Math.max(14,canvas.width/55)}px sans-serif`; context.fillText(anchor.id,x1*canvas.width,y1*canvas.height-4);
  }
}
function location(event: PointerEvent) {
  const rect = canvas.getBoundingClientRect();
  return [Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width)), Math.max(0,Math.min(1,(event.clientY-rect.top)/rect.height))];
}
function markMode(mode: string) {
  if (!view) return;
  if (mode === "court" && video.currentTime > 0.15) { status("Seek to the opening frame for court calibration. Camera changes need separate projects in this build.",true); return; }
  video.pause(); marking = mode; canvas.classList.toggle("marking",!!mode);
  if (mode === "court") calibration = [];
  status(mode === "court" ? "Click near-left, near-right, far-right, far-left court corners." : `Drag a box around ${mode}.`);
}
canvas.onpointerdown = event => {
  if (!marking || busy) return;
  const point = location(event);
  if (marking === "court") {
    calibration.push(point); if (calibration.length === 4) { marking = ""; canvas.classList.remove("marking"); }
    drawMarks(); return;
  }
  drag = point; canvas.setPointerCapture(event.pointerId);
};
canvas.onpointerup = event => {
  if (!drag || !marking || marking === "court") return;
  const end = location(event); const box = [Math.min(drag[0],end[0]),Math.min(drag[1],end[1]),Math.max(drag[0],end[0]),Math.max(drag[1],end[1])];
  if (box[2]-box[0] > 0.015 && box[3]-box[1] > 0.03) {
    const anchor = {id:marking,team:["P1","P2"].includes(marking)?"A":"B",box};
    if (video.currentTime <= 0.15) { anchors = anchors.filter(a => a.id !== marking); anchors.push(anchor); }
    else {
      reanchors = reanchors.filter(a => a.id !== marking || Math.abs((a.time || 0)-video.currentTime) > 0.2);
      reanchors.push({...anchor,time:video.currentTime});
    }
  }
  drag = null; marking = ""; canvas.classList.remove("marking"); drawMarks();
};
video.onloadedmetadata = () => { canvas.width=video.videoWidth; canvas.height=video.videoHeight; element("stage").style.aspectRatio=`${video.videoWidth}/${video.videoHeight}`; drawMarks(); };
video.ontimeupdate = updateScore; video.onseeked = () => { updateScore(); drawMarks(); };
function onFrame() {
  updateScore();
  if (!video.paused && !video.ended) {
    if ("requestVideoFrameCallback" in video) video.requestVideoFrameCallback(onFrame);
    else requestAnimationFrame(onFrame);
  }
}
video.onplay = onFrame;
element("import").onclick = () => void guarded(async () => {
  const path = await invoke<string|null>("pick_file",{kind:"video"});
  if (path) { apply(await invoke<ProjectView>("open_project",{path,create:true})); status("Project created. Prepare the review video, then mark the court and roster."); }
});
element("open").onclick = () => void guarded(async () => {
  const path = await invoke<string|null>("pick_file",{kind:"project"});
  if (path) { apply(await invoke<ProjectView>("open_project",{path,create:false})); status("Project restored."); }
});
element("diagnostics").onclick = () => void guarded(async () => status(JSON.stringify(await invoke("request",{payload:{action:"diagnostics"}}))));
async function saveSettings() {
  const rule = view!.document.rules;
  apply(await request({action:"edit",operation:"settings",revision:view!.document.revision,payload:{
    discipline:value("discipline"), calibration, anchors, reanchors, models,
    rules:{...rule,server:value("server"),initial_server:value("initial-server"),initial_receiver:value("initial-receiver"),
      initial:[number("initial-a"),number("initial-b")],target:number("target"),cap:number("cap")},
    analysis_options:{gpu:element<HTMLInputElement>("gpu").checked,auto_accept:element<HTMLInputElement>("auto-accept").checked}
  }}));
}
element("save-settings").onclick = () => void guarded(async () => { await saveSettings(); status("Setup saved."); });
element("court").onclick = () => markMode("court");
element<HTMLSelectElement>("player").onchange = () => markMode(value("player"));
element("clear-marks").onclick = () => { calibration=[]; anchors=[]; reanchors=[]; drawMarks(); };
for (const kind of ["people","shuttle"]) element(`${kind}-model`).onclick = () => void guarded(async () => {
  const path = await invoke<string|null>("pick_file",{kind:"model"});
  if (path) { models[kind]=path; element(`${kind}-path`).textContent=path; status("Model selected; save match setup to persist."); }
});
for (const action of ["prepare","analyse","export"]) element(action).onclick = () => void guarded(async () => {
  if (action !== "export") await saveSettings();
  element("job-title").textContent = `Running ${action}`;
  const next = await request({action}); apply(next);
  status(next.export ? `Export saved: ${next.export}` : `${action} complete. Review point candidates before export.`);
});
element("roster").onclick = () => void guarded(async () => {
  await saveSettings(); const next = await request({action:"suggest"}); apply(next); status("Roster suggestion saved. Confirm boxes and discipline before analysis.");
});
element("cancel").onclick = () => void invoke("cancel").then(()=>status("Cancellation requested; waiting for a safe boundary."));
element("use-time").onclick = () => { element<HTMLInputElement>("point-time").value=displayTime().toFixed(3); };
element("new-point").onclick = () => { element<HTMLInputElement>("point-id").value=""; element<HTMLInputElement>("point-time").value=displayTime().toFixed(3); };
element<HTMLFormElement>("point-form").onsubmit = event => { event.preventDefault(); void guarded(async () => {
  const outcome = value("outcome"); const time = number("point-time");
  if (time >= view!.document.media.duration) throw new Error("Choose a point time before the end so its score is visible in export.");
  apply(await request({action:"edit",operation:"point",revision:view!.document.revision,payload:{
    id:value("point-id") || undefined,time,winner:["A","B"].includes(outcome)?outcome:null,
    disposition:outcome==="pending"?"point_pending":outcome==="replay"?"replay/no_point":"point_awarded",
    timing_origin:"manual_display_anchor"}})); status("Point saved; later scores recalculated.");
}); };
element("checkpoint").onclick = () => void guarded(async () => apply(await request({action:"edit",operation:"checkpoint",revision:view!.document.revision,payload:{
  time:displayTime(),score:[number("checkpoint-a"),number("checkpoint-b")],game:number("checkpoint-game"),server:value("checkpoint-server")}})));
for (const [id,direction] of [["undo",-1],["redo",1]] as const) element(id).onclick = () => void guarded(async () => apply(await request({action:"history",direction})));
void listen<{type:string;stage?:string;fraction?:number;message?:string}>("worker-message", event => {
  if (event.payload.type === "progress") {
    element<HTMLProgressElement>("progress").value = event.payload.fraction || 0;
    element("fraction").textContent = `${Math.round((event.payload.fraction || 0)*100)}%`;
    element("job-title").textContent = event.payload.stage || "Processing";
    status(event.payload.message || "Processing locally");
  }
});
controls();
