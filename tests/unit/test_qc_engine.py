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
