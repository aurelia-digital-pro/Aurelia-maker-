*** Begin Patch
*** Update File: aurelia/episode_engine.py
@@
     def generate_visual_assets(self) -> list[Path]:
         self._emit("Generating content-bound local AI visual assets...")
         assets: list[Path] = []
-        for scene in self.scenes:
-            path = self.dirs["visuals"] / f"scene_{scene.index + 1:02d}.png"
-            generate_scene_image(
-                scene.index,
-                scene.title,
-                scene.text,
-                path,
-                direction=scene.direction,
-                width=512,
-                height=512,
-            )
-            assets.append(path)
+        # Use canonical provider that writes provenance alongside images
+        from .providers_visual import generate_scene_image_with_provenance
+
+        for scene in self.scenes:
+            path = self.dirs["visuals"] / f"scene_{scene.index + 1:02d}.png"
+            generated_path, prov = generate_scene_image_with_provenance(
+                scene_index=scene.index,
+                title=scene.title,
+                text=scene.text,
+                output=path,
+                direction=scene.direction,
+            )
+            assets.append(generated_path)
@@
-        visual_manifest = {
-            "backend": "local-ai",
-            "episode_id": self.episode_id,
-            "title": self.title,
-            "scenes": [
-                {
-                    "index": scene.index,
-                    "title": scene.title,
-                    "text_sha256": hashlib.sha256(scene.text.encode("utf-8")).hexdigest(),
-                    "asset": str(asset),
-                    "asset_sha256": hashlib.sha256(asset.read_bytes()).hexdigest(),
-                    "direction": scene.direction,
-                }
-                for scene, asset in zip(self.scenes, assets)
-            ],
-        }
+        visual_manifest = {
+            "backend": "local-ai",
+            "episode_id": self.episode_id,
+            "title": self.title,
+            "scenes": [],
+        }
+        # Include provenance per-asset for reliable QC
+        for scene, asset in zip(self.scenes, assets):
+            prov_path = Path(asset).with_suffix(Path(asset).suffix + ".prov.json")
+            prov: dict = {}
+            if prov_path.exists():
+                try:
+                    prov = json.loads(prov_path.read_text(encoding="utf-8"))
+                except Exception:
+                    prov = {}
+            visual_manifest["scenes"].append(
+                {
+                    "index": scene.index,
+                    "title": scene.title,
+                    "text_sha256": hashlib.sha256(scene.text.encode("utf-8")).hexdigest(),
+                    "asset": str(asset),
+                    "asset_sha256": prov.get("sha256") or hashlib.sha256(Path(asset).read_bytes()).hexdigest(),
+                    "direction": scene.direction,
+                    "provenance": prov,
+                }
+            )
*** End Patch
