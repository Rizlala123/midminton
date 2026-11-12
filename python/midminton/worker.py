"""One request per process; JSON-lines stdout is the desktop IPC contract."""
from pathlib import Path
import json
import shutil
import sys
import traceback
import uuid
from .store import Project


def emit(kind, **payload):
    print(json.dumps({"type": kind, **payload}, allow_nan=False), flush=True)


def view(project):
    doc = project.read()
    from .render import assets
    scoreboards = assets(doc, project.path)
    run = doc.get("analysis", {}).get("run")
    contacts = [row for _, row in project.rows(run, "contacts")] if run else []
    return {"document": doc, "timeline": scoreboards, "project": str(project.path), "contacts": contacts,
            "video": str(project.path/"review.mp4") if (project.path/"review.mp4").exists() else doc["media"]["path"]}


def handle(request):
    action = request["action"]
    if action == "diagnostics":
        import importlib.util
        return {"python": sys.version, "ffmpeg": shutil.which("ffmpeg"), "ffprobe": shutil.which("ffprobe"),
                "packages": {name: importlib.util.find_spec(name) is not None for name in ("PIL", "cv2", "numpy", "onnxruntime")}}
    project = Project(request["project"])
    cancel_file = project.path/"cancel.request"
    cancel = cancel_file.exists
    progress = lambda stage, fraction, message="": emit("progress", stage=stage, fraction=fraction, message=message)
    if action == "create":
        from .media import probe
        media = probe(request["video"])
        project.create(dict(id=uuid.uuid4().hex, media=media, discipline="auto", anchors=[], calibration=[], models={},
            rules=dict(target=21, margin=2, cap=30, initial=[0, 0], server="A", initial_server="P1", initial_receiver="P3"),
            analysis_options={"gpu": False}, events=[], checkpoints=[]))
    elif action == "edit":
        project.edit(request["operation"], request["payload"], int(request["revision"]))
    elif action == "history":
        project.history(int(request["direction"]))
    elif action == "prepare":
        from .media import make_proxy
        make_proxy(project.read(), project.path, cancel, lambda f: progress("proxy", f, "Preparing local H.264 review video"))
    elif action == "analyse":
        from .vision.pipeline import analyse
        result = analyse(project, cancel, progress)
        emit("progress", stage="complete", fraction=1, message=result["notice"])
    elif action == "suggest":
        from .vision.pipeline import suggest
        suggest(project)
    elif action == "export":
        from .render import export
        document = project.read()
        output = export(document, project.path, cancel, lambda f: progress("export", f, "Rendering the reviewed score revision"))
        result = view(project)
        result["export"] = output
        return result
    elif action != "load":
        raise ValueError("Unknown worker action")
    return view(project)


def main():
    try:
        request = json.loads(sys.stdin.readline(1024*1024))
        emit("result", data=handle(request))
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        emit("error", message=str(exc), cancelled=isinstance(exc, InterruptedError))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
