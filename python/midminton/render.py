"""One PNG scoreboard renderer used by both preview and FFmpeg export."""
from pathlib import Path
import json
from .scoring import snapshots
from .media import run_ffmpeg, validate_source, video_filters


def assets(doc, project_dir):
    from PIL import Image, ImageDraw, ImageFont
    output = Path(project_dir) / "scoreboards" / str(doc["revision"])
    output.mkdir(parents=True, exist_ok=True)
    try:
        font = ImageFont.truetype("segoeui.ttf", 29)
        small = ImageFont.truetype("segoeui.ttf", 17)
    except OSError:
        font = ImageFont.truetype("DejaVuSans.ttf", 29)
        small = ImageFont.truetype("DejaVuSans.ttf", 17)
    timeline = snapshots(doc)
    frames = []
    for i, entry in enumerate(timeline):
        path = output / f"{i:05d}.png"
        if not path.exists():
            state = entry["state"]
            image = Image.new("RGBA", (460, 110), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((0, 0, 459, 109), 12, fill=(17, 34, 43, 235))
            score = state["trusted_score"] if state["provisional"] else state["score"]
            draw.text((18, 10), f"A   {score[0]}  -  {score[1]}   B", font=font, fill="white")
            status = f"Game {state['game']}  |  Serve {state['server']}"
            if state["provisional"]:
                status = f"Provisional - {len(state['pending'])} point(s) to review"
            elif state["game_over"]:
                status = f"Game {state['game']} complete"
            draw.text((18, 65), status, font=small, fill=(136, 220, 202))
            image.save(path)
        frames.append({"time": entry["time"], "path": str(path), "state": entry["state"]})
    return frames


def export(doc, project_dir, cancel, progress):
    validate_source(doc)
    project_dir = Path(project_dir)
    frames = assets(doc, project_dir)
    duration = doc["media"]["duration"]
    # Deduplicate simultaneous transitions and don't render points after media end.
    by_time = {f["time"]: f for f in frames if f["time"] < duration}
    frames = [by_time[t] for t in sorted(by_time)]
    concat = project_dir / "scoreboards" / "export.ffconcat"
    lines = ["ffconcat version 1.0"]
    for i, frame in enumerate(frames):
        relative = Path(frame["path"]).relative_to(concat.parent).as_posix()
        end = frames[i+1]["time"] if i+1 < len(frames) else duration
        lines.extend([f"file '{relative}'", "option framerate 1000", f"duration {end-frame['time']:.6f}"])
    lines.extend([lines[-3], "option framerate 1000"])  # Repeat the final image.
    concat.write_text("\n".join(lines)+"\n", encoding="utf-8")
    target = project_dir / f"scored-revision-{doc['revision']}.mp4"
    partial = project_dir / "scored.partial.mp4"
    scale = min(1, 1920/doc["media"]["width"], 1080/doc["media"]["height"])
    width = min(460, max(80, int(doc["media"]["width"]*scale)-32))
    filters = ",".join(video_filters(doc["media"], 1920, 1080))
    try:
        run_ffmpeg(["-i", doc["media"]["path"], "-f", "concat", "-safe", "0", "-i", str(concat),
                    "-filter_complex", f"[0:v]{filters}[base];[1:v]scale={width}:-1[score];[base][score]overlay=16:16:eof_action=repeat[v]",
                    "-map", "[v]", "-map", "0:a?", "-af", f"asetpts=PTS-STARTPTS+{doc['media'].get('audio_offset',0)}/TB", "-t", str(duration),
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-movflags", "+faststart", str(partial)], cancel, progress, duration, project_dir/"export.log")
        if cancel():
            raise InterruptedError("Export cancelled")
        partial.replace(target)
        target.with_suffix(".json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
    finally:
        partial.unlink(missing_ok=True)
    return str(target)
