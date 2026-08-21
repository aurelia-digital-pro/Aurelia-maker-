---
*** Begin Patch
*** Update File: aurelia/providers_visual.py
@@
-class VisualGenerationError(RuntimeError):
-    pass
+class VisualGenerationError(RuntimeError):
+    pass
+
+
+def _read_config() -> dict:
+    try:
+        cfg_path = Path(__file__).resolve().parents[1] / "ai_config.json"
+        if not cfg_path.exists():
+            cfg_path = Path(__file__).resolve().parents[0] / "ai_config.json"
+        return json.loads(cfg_path.read_text(encoding="utf-8"))
+    except Exception:
+        return {}
+
+
+def generate_scene_image_with_provenance(
+    scene_index: int,
+    title: str,
+    text: str,
+    output: str | Path,
+    direction: dict | None = None,
+) -> tuple[Path, dict]:
+    """Compatibility wrapper: generate image and always write a .prov.json.
+
+    Returns (path, provenance)
+    """
+    cfg = _read_config()
+    image_cfg = cfg.get("image", {})
+    output_path = Path(output)
+    output_path.parent.mkdir(parents=True, exist_ok=True)
+
+    # Prefer the ai_visual public API if present
+    try:
+        generated = ai_visual.generate_scene_image(
+            scene_index=scene_index,
+            title=title,
+            description=text,
+            output=output_path,
+            direction=direction,
+            width=int(image_cfg.get("width", 512)),
+            height=int(image_cfg.get("height", 512)),
+        )
+        if isinstance(generated, Path):
+            generated_path = generated
+        else:
+            generated_path = Path(generated)
+        fallback = False
+        fallback_reason = ""
+    except Exception as exc:
+        # Last-resort: attempt to call pillow renderer explicitly if available
+        try:
+            from .ai_visual import _generate_with_pillow
+
+            ok = _generate_with_pillow(
+                scene_index,
+                title,
+                text,
+                output_path,
+                direction,
+                int(image_cfg.get("width", 512)),
+                int(image_cfg.get("height", 512)),
+                visual_note="",
+                run_id="",
+            )
+            if not ok:
+                raise RuntimeError("Pillow fallback returned False")
+            generated_path = output_path
+            fallback = True
+            fallback_reason = str(exc)
+        except Exception as exc2:
+            raise VisualGenerationError(f"visual generation failed: {exc} / fallback: {exc2}")
+
+    if not generated_path.exists() or generated_path.stat().st_size == 0:
+        raise VisualGenerationError(f"Generated asset missing or empty: {generated_path}")
+
+    # Compute canonical provenance
+    sha = hashlib.sha256(generated_path.read_bytes()).hexdigest()
+    prov_path = generated_path.with_suffix(generated_path.suffix + ".prov.json")
+    prov: dict = {}
+    if prov_path.exists():
+        try:
+            prov = json.loads(prov_path.read_text(encoding="utf-8"))
+        except Exception:
+            prov = {}
+
+    prov.setdefault("backend", (cfg.get("model", {}).get("source") or "stable-diffusion") if not fallback else "pillow")
+    prov.setdefault("model_id", cfg.get("model", {}).get("id"))
+    prov.setdefault("model_source", cfg.get("model", {}).get("source"))
+    prov.setdefault("model_revision", cfg.get("model", {}).get("recommended_revision"))
+    try:
+        prompt = ai_visual.build_scene_prompt(title, text, direction)
+    except Exception:
+        prompt = f"{title} -- {text}"
+    prov.setdefault("prompt", prompt)
+    prov.setdefault("negative_prompt", cfg.get("image", {}).get("negative_prompt"))
+    prov.setdefault("seed", prov.get("seed", None))
+    prov.setdefault("width", int(image_cfg.get("width", 512)))
+    prov.setdefault("height", int(image_cfg.get("height", 512)))
+    prov.setdefault("steps", int(image_cfg.get("steps", 20)))
+    prov.setdefault("guidance_scale", float(image_cfg.get("guidance_scale", 7.5)))
+    prov.setdefault("generated_at", datetime.utcnow().isoformat() + "Z")
+    prov.setdefault("sha256", sha)
+    prov.setdefault("path", str(generated_path.resolve()))
+    prov.setdefault("scene_index", scene_index)
+    prov.setdefault("fallback", bool(prov.get("fallback", False) or fallback))
+    prov.setdefault("fallback_reason", prov.get("fallback_reason", fallback_reason or ""))
+
+    prov_path.write_text(json.dumps(prov, ensure_ascii=False, indent=2), encoding="utf-8")
+    return generated_path, prov
+
+
+__all__ = ["VisualGenerationError", "generate_scene_image_with_provenance"]
*** End Patch
