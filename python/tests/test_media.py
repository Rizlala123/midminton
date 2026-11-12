import pytest
from midminton.media import validate_source, video_filters, video_duration


def test_changed_source_is_rejected_before_export(tmp_path):
    path = tmp_path/"match ü.mp4"
    path.write_bytes(b"original")
    stat = path.stat()
    doc = {"media": {"path": str(path), "size": stat.st_size, "modified": stat.st_mtime_ns}}
    validate_source(doc)
    path.write_bytes(b"different recording")
    with pytest.raises(ValueError, match="changed"):
        validate_source(doc)


def test_proxy_and_export_share_hdr_policy():
    proxy = video_filters({"transfer": "smpte2084"}, 1280, 720)
    export = video_filters({"transfer": "smpte2084"}, 1920, 1080)
    assert proxy[0] == export[0]
    assert "force_divisible_by=2" in export[-1]


def test_video_duration_does_not_include_longer_container_audio_tail():
    assert video_duration({"duration": "10", "start_time": "0"}) == 10
    assert video_duration({"start_time": "2", "tags": {"DURATION": "00:00:12.000"}}) == 10
    with pytest.raises(ValueError, match="Remux"):
        video_duration({})
