"""FFmpeg helpers: argument arrays only; bounded decoding lives in vision.pipeline."""
from pathlib import Path
import json
import subprocess
import queue
import threading


def video_duration(stream):
    value = stream.get("duration")
    if value not in (None, "N/A"):
        return float(value)
    tagged = stream.get("tags", {}).get("DURATION")
    if tagged:
        hours, minutes, seconds = tagged.split(":")
        return int(hours)*3600+int(minutes)*60+float(seconds)-float(stream.get("start_time", 0))
    raise ValueError("Cannot establish video-stream duration. Remux this recording to MP4 before importing")


def probe(path):
    path = Path(path).resolve(strict=True)
    if not path.is_file():
        raise ValueError("Choose a video file")
    result = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                            capture_output=True, text=True, timeout=60, check=True,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    data = json.loads(result.stdout)
    stream = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    if not stream:
        raise ValueError("No video stream found")
    duration = video_duration(stream)
    if not 0 < duration <= 86400:
        raise ValueError("Video duration must be between zero and 24 hours")
    audio = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    audio_offset = float(audio.get("start_time", 0)) - float(stream.get("start_time", 0)) if audio else 0
    return dict(path=str(path), duration=duration, width=stream["width"], height=stream["height"], audio_offset=audio_offset,
                transfer=stream.get("color_transfer", "unknown"), size=path.stat().st_size,
                modified=path.stat().st_mtime_ns, codec=stream["codec_name"])


def validate_source(doc):
    path = Path(doc["media"]["path"])
    stat = path.stat()
    if stat.st_size != doc["media"]["size"] or stat.st_mtime_ns != doc["media"]["modified"]:
        raise ValueError("The original video changed after import. Create a new project for that recording")


def video_filters(media, max_width, max_height):
    filters = []
    if media["transfer"] in {"smpte2084", "arib-std-b67"}:
        filters.append("zscale=t=linear:npl=100,format=gbrpf32le,tonemap=hable,zscale=t=bt709:m=bt709:r=tv")
    filters.append(f"scale=w='min({max_width},iw)':h='min({max_height},ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1,setpts=PTS-STARTPTS")
    return filters


def run_ffmpeg(arguments, cancel, progress, duration, log_path):
    log_path = Path(log_path)
    with log_path.open("wb") as log:
        process = subprocess.Popen(["ffmpeg", "-hide_banner", "-nostdin", "-y", "-progress", "pipe:1", "-nostats", *arguments],
                                   stdout=subprocess.PIPE, stderr=log, text=True,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            lines = queue.Queue(maxsize=256)
            def drain():
                for line in process.stdout:
                    try:
                        lines.put(line, timeout=0.2)
                    except queue.Full:
                        pass
            reader = threading.Thread(target=drain, daemon=True)
            reader.start()
            while process.poll() is None or not lines.empty():
                if cancel():
                    raise InterruptedError("Cancelled; completed stages are retained")
                try:
                    line = lines.get(timeout=0.2)
                except queue.Empty:
                    continue
                if line.startswith("out_time_us="):
                    progress(min(1.0, max(0, int(line.split("=", 1)[1])) / 1e6 / max(duration, 1)))
            if process.wait() != 0:
                with log_path.open("rb") as failed_log:
                    failed_log.seek(max(0, log_path.stat().st_size-2000))
                    detail = failed_log.read(2000).decode("utf-8", errors="replace")
                raise RuntimeError(f"FFmpeg failed: {detail}")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def make_proxy(doc, directory, cancel, progress):
    validate_source(doc)
    output = Path(directory) / "review.mp4"
    partial = Path(directory) / "review.partial.mp4"
    filters = video_filters(doc["media"], 1280, 720)
    fps = 30
    if doc.get("models", {}).get("shuttle"):
        fps = int(json.loads(Path(doc["models"]["shuttle"]).read_text(encoding="utf-8")).get("fps", 30))
    if fps not in {25, 30, 50, 60}:
        raise ValueError("Unsupported analysis frame rate")
    filters.append(f"fps={fps}")
    try:
        run_ffmpeg(["-i", doc["media"]["path"], "-map", "0:v:0", "-map", "0:a?", "-vf", ",".join(filters),
                    "-af", f"asetpts=PTS-STARTPTS+{doc['media'].get('audio_offset',0)}/TB", "-c:v", "libx264", "-preset", "fast", "-crf", "21", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-movflags", "+faststart", str(partial)], cancel, progress, doc["media"]["duration"], Path(directory)/"proxy.log")
        partial.replace(output)
        (Path(directory)/"review.json").write_text(json.dumps({"fps": fps,
            "source": {key: doc["media"][key] for key in ("path", "size", "modified")}}), encoding="utf-8")
    finally:
        partial.unlink(missing_ok=True)
    return str(output)
