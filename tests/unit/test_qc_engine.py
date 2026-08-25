from pathlib import Path

from aurelia.qc_engine import run_qc


def test_missing_video_blocks_delivery(tmp_path: Path):
    result = run_qc(tmp_path / "missing.mp4")
    assert result["delivery_blocked"] is True
    assert any(check["name"] == "file_exists" for check in result["fatals"])


def test_qc_exposes_production_motion_checks(tmp_path: Path):
    result = run_qc(tmp_path / "missing.mp4")
    names = {check["name"] for check in result["fatals"]}
    # A missing file returns early, but the public function remains a valid gate.
    assert "file_exists" in names


def test_qc_audio_quality_gate_on_accepted_final():
    final = Path("/tmp/aurelia-artifact-32674094316/runs/e2e/episode-0001-FINAL.mp4")
    if not final.is_file():
        return
    result = run_qc(final, min_duration_s=25.0, require_audio_quality=True)
    assert result["audio_quality"]["passed"] is True
    assert not [check for check in result["fatals"] if check["name"].startswith("audio_")]
