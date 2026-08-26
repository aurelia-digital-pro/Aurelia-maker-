# AURELIA Maker — CTO Recovery Record

## 1. Root causes confirmed

### A. Browser Chat runtime was stale

At investigation time, the live process on `127.0.0.1:8765` had started at `2026-08-26 15:16:28`, while the repository had since advanced to `0236d16`. Its `/api/status` returned `tts_backends=["espeak-ng","pyttsx3"]` and `primary="pillow-fallback"`. The current `HEAD` contains no `TTS: all dialogue segments failed` string. That message exists only in historical commit `c733393:aurelia/tts.py`, where dialogue-segment exceptions were swallowed and replaced by a generic error.

The observed Browser Chat failure therefore came from a stale runtime loaded before the canonical TTS changes, not from the current `EpisodeProduction → EdgeTTSProvider` implementation.

### B. Deployment wiring did not start the canonical backend

`artifacts/api-server/.replit-artifact/artifact.toml` previously launched only the Node API process. Its proxy defaulted to `http://127.0.0.1:8765`, but the descriptor did not start Python there. Its `/api/healthz` endpoint also returned `200` without checking the canonical backend. This allowed an API service to look healthy while Browser Chat was not guaranteed to reach the canonical Python engine.

### C. Status was misleading for explicit `0`

`aurelia.visual_backend.backend_status()` treated the non-empty string `AURELIA_FORCE_FALLBACK=0` as truthy and could report `pillow-fallback`. Its TTS probe did not report the installed `edge-tts` executable. This was a health/diagnostic defect, not permission to use a fallback in production.

## 2. Files affected

| File | Purpose of change |
|---|---|
| `.replit` | Project and deployment run/build commands now use the canonical launch/build scripts. |
| `scripts/start-canonical.sh` | Starts the Python canonical Browser Chat server with strict production defaults. |
| `scripts/start-api-with-canonical.sh` | Starts one Python canonical backend and the Node compatibility proxy; no second engine. |
| `scripts/build-production.sh` | Installs authoritative Python requirements before building the API artifact. |
| `artifacts/api-server/.replit-artifact/artifact.toml` | Production build/run now use the canonical scripts and strict environment flags. |
| `artifacts/api-server/src/routes/health.ts` | `/api/healthz` now returns `503` if canonical Python is unavailable/unhealthy. |
| `aurelia/visual_backend.py` | Corrects fallback flag parsing and reports `edge-tts` in status. |
| `tests/unit/test_runtime_wiring.py` | Regression coverage for runtime wiring and environment/status semantics. |

The canonical production TTS code itself was not replaced or bypassed: `EpisodeProduction.synthesize_narration()` still instantiates `EdgeTTSProvider`, uses `ar-SA-HamedNeural` for Arabic, validates the WAV artifact, and rejects degraded provenance.

## 3. Fixes actually applied

The runtime now has one explicit startup contract. The root Project/Deployment starts `scripts/start-canonical.sh`; the separate API artifact starts `scripts/start-api-with-canonical.sh`, which launches the same Python canonical server and then the stateless Node proxy. Both paths set `AURELIA_PRODUCTION_MODE=1`, `AURELIA_FORCE_FALLBACK=0`, and `AURELIA_ALLOW_DEGRADED_TTS=0` unless explicitly overridden by deployment configuration.

The Node health check now depends on `GET /api/health` from the canonical Python server and fails closed. The status endpoint now distinguishes `0` from `1` correctly and reports `edge-tts` when installed. No production fallback, QC bypass, or alternative engine was added.

The stale local process was terminated and restarted from the current checkout using the canonical launcher. This was a runtime restart and health/status smoke check only; no Chat POST, provider generation, production job, or E2E was run.

## 4. Validation actually performed

| Validation | Result |
|---|---:|
| Targeted runtime/TTS regression tests | `19 passed, 5 warnings` |
| Full repository test suite | `92 passed, 7 warnings` |
| Python compileall | PASS |
| Bash syntax checks for all launch/build scripts | PASS |
| TOML/YAML parsing | PASS |
| API Zod/DB TypeScript build | PASS |
| API-server TypeScript typecheck | PASS |
| `git diff --check` | PASS |
| Current Chat server `GET /api/health` | PASS |
| Current Chat server `GET /api/status` | `edge-tts`, `cloud-api/auto`, no Pillow primary |
| Current `HEAD` exact legacy error search | absent |

The prior GitHub run `32995131471` and its Episode 0003 artifact remain historical evidence of the canonical engine’s real production path, but are deliberately not used as evidence that the current Browser Chat runtime has completed a new production after this recovery.

## 5. Remaining blockers

**BLOCKER:** A new real production request from the current Browser Chat runtime was explicitly prohibited by `pasted_content_20.txt`, so the repaired runtime has not been granted a fresh Chat-to-FINAL-MP4 acceptance proof. The stale-runtime root cause is confirmed and the runtime wiring is corrected, but the completion gate requiring current Chat → Factory → real narration → real visuals → QC → FINAL MP4 cannot truthfully be marked complete without that separately authorized validation.

## 6. Final production status

`NOT READY — السبب المحدد هو أن المواصفة الحالية منعت تشغيل production/E2E جديد، ولذلك لا توجد بعدُ نتيجة قبول جديدة للمسار الحالي بعد إصلاح runtime wiring. لا توجد قرينة على استمرار رسالة TTS legacy في الكود أو في الخادم الذي أُعيد تشغيله من HEAD.`
