from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from aurelia import ffmpeg_util


def test_run_ffmpeg_timeout_contains_stage_and_output(monkeypatch, tmp_path: Path):
    output = tmp_path / "edit_mixed.mp4"
    monkeypatch.setattr(ffmpeg_util, "ffmpeg_binary", lambda: "/usr/bin/ffmpeg")

    def timeout(command, **kwargs):
        assert kwargs["timeout"] == 3.0
        raise subprocess.TimeoutExpired(command, 3.0)

    monkeypatch.setattr(ffmpeg_util.subprocess, "run", timeout)
    with pytest.raises(RuntimeError, match=r"FFmpeg timeout: stage=EDIT/mix.*timeout_s=3.0.*edit_mixed\.mp4"):
        ffmpeg_util.run_ffmpeg(
            ["-i", "input.mp4", str(output)],
            timeout_seconds=3.0,
            stage="EDIT/mix",
            output_path=output,
        )
