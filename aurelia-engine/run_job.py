"""Process boundary for the TypeScript API.

The API owns job identity and passes it into the original factory so the
manifest and final artifact remain cryptographically tied to this request.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from aurelia.factory_runner import FactoryRunner  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--episode-id", required=True)
    parser.add_argument("--profile", default="both")
    parser.add_argument("--request", required=True)
    args = parser.parse_args()

    runner = FactoryRunner(ROOT)
    input_dir = runner.output / ".chat_inputs"
    input_dir.mkdir(parents=True, exist_ok=True)
    request_path = input_dir / f"{args.job_id}.txt"
    request_path.write_text(args.request, encoding="utf-8")
    job = runner.create_job(args.episode_id, args.profile, request_path, job_id=args.job_id)
    job.status = "RUNNING"
    try:
        result = runner.run_episode_production(job, request_path, args.profile)
        job.metadata["result"] = result
        print(json.dumps({"status": "COMPLETED", "job": job.__dict__}, ensure_ascii=False), flush=True)
        return 0
    except Exception as exc:
        job.status = "FAILED"
        job.error = str(exc)
        print(json.dumps({"status": "FAILED", "error": str(exc), "job": job.__dict__}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())