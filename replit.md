# AURELIA Maker

AURELIA Maker is a canonical Chat → Factory → cinematic production engine. Browser Chat is served by the Python canonical API and every accepted production request uses the same Factory/Pipeline implementation.

## Run & Operate

- `bash scripts/start-canonical.sh` — start the canonical Python Browser Chat server; it binds `PORT` (default `8765`) and enforces production-safe defaults.
- `bash scripts/start-api-with-canonical.sh` — start the stateless Node compatibility proxy together with one canonical Python backend.
- `bash scripts/build-production.sh` — install authoritative `requirements.txt`, then build the API artifact.
- `python3 -m pytest -q tests/` — run the repository regression suite.
- `pnpm run typecheck` — run TypeScript checks where the workspace policy permits.

`requirements.txt` is the authoritative Python runtime contract. Production narration requires `edge-tts==7.2.8`, and Arabic production narration uses `ar-SA-HamedNeural`. Production visual fallback is disabled by `AURELIA_FORCE_FALLBACK=0`; degraded TTS is disabled by `AURELIA_ALLOW_DEGRADED_TTS=0`.

## Canonical path

```text
Browser Chat → aurelia.server → chat_entry → FactoryRunner
→ ProductionPipeline → EpisodeProduction → Edge TTS / real visuals
→ editing → subtitles → master → QC → delivery → FINAL MP4
```

The Node API artifact is a compatibility proxy only. It does not own a process, job map, FactoryRunner, engine root, or independent production state machine. Its readiness endpoint checks the canonical Python `/api/health` endpoint.

## Runtime and deployment notes

Use the same Python 3.12 contract in the local Project, API artifact, and GitHub Actions. Do not start a second engine or use `aurelia-engine/`; that executable tree was removed. A service that exposes `/api` without starting or reaching the canonical Python backend is not production-ready, even if its HTTP health endpoint is reachable.

## Repository map

- `aurelia/server.py` — canonical FastAPI server and job/video API.
- `aurelia/chat_entry.py` — Browser Chat request binding.
- `aurelia/factory_runner.py` — canonical job lifecycle, idempotency, retry, completion, and failure propagation.
- `aurelia/production_pipeline.py` — ordered stage execution and contracts.
- `aurelia/episode_engine.py` — visual, narration, editing, subtitle, and master implementation.
- `aurelia/providers/audio.py` — strict Edge TTS provider and diagnostic provenance.
- `aurelia/production_contract.py` — stage input/output contracts.
- `artifacts/api-server/src/routes/productions.ts` — stateless compatibility proxy.
- `scripts/start-canonical.sh` — canonical Browser Chat launcher.
- `scripts/start-api-with-canonical.sh` — proxy plus canonical backend launcher.
- `scripts/build-production.sh` — authoritative runtime install and API build.

## Gotchas

A Factory `COMPLETED` state is local engine completion. External acceptance is represented separately by the GitHub-promoted production proof after artifact and QC verification. Never treat an MP4’s existence, a Node `/api/healthz` response, or an old E2E artifact alone as proof that the current Browser Chat runtime has passed acceptance.
