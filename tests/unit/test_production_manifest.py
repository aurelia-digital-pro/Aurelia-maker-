import json
from pathlib import Path
from types import SimpleNamespace

from aurelia.factory_runner import ProductionJob, _build_production_manifest


def test_production_manifest_preserves_qc_results_for_final_proof(tmp_path: Path):
    job = ProductionJob(job_id="job-123", episode_id="0001")
    production = SimpleNamespace(
        scenes=[
            SimpleNamespace(
                direction={"environment": "space"},
            )
        ]
    )
    qc = {
        "passed": True,
        "delivery_blocked": False,
        "fatals": [],
        "checks": [{"name": "has_audio", "passed": True}],
    }
    visual_qc = {
        "passed": True,
        "failed_checks": [],
        "check_details": {},
    }

    manifest = _build_production_manifest(
        job=job,
        title="Test episode",
        language="ar",
        profile="both",
        script_path=tmp_path / "script.txt",
        source_text_sha256="source-hash",
        final_outputs={"youtube": tmp_path / "youtube.mp4"},
        sound_design=tmp_path / "sound.wav",
        stage_artifacts_root=tmp_path / "stage_artifacts",
        delivery_validation={"passed": True},
        qc=qc,
        visual_qc=visual_qc,
        production=production,
    )

    assert manifest["qc"] == qc
    assert manifest["visual_qc"] == visual_qc
    assert manifest["delivery_validation"]["passed"] is True
    json.dumps(manifest)


def test_production_manifest_is_explicitly_chat_sourced():
    job = ProductionJob(job_id="job-456", episode_id="0002")
    production = SimpleNamespace(scenes=[])
    manifest = _build_production_manifest(
        job=job,
        title="Chat episode",
        language="en",
        profile="both",
        script_path=Path("script.txt"),
        source_text_sha256="hash",
        final_outputs={},
        sound_design=None,
        stage_artifacts_root=Path("stages"),
        delivery_validation={},
        qc={"passed": True},
        visual_qc={"passed": True},
        production=production,
    )

    assert manifest["source"] == "chat"
    assert manifest["job_id"] == "job-456"
    assert manifest["episode_id"] == "0002"
