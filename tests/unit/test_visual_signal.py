import json
from pathlib import Path

from PIL import Image, ImageDraw

from aurelia.media import validate_visual_manifest


def test_manifest_accepts_real_visual_signal(tmp_path: Path):
    image_path = tmp_path / "shot.png"
    image = Image.new("RGB", (512, 512), (12, 35, 80))
    draw = ImageDraw.Draw(image)
    draw.ellipse((120, 100, 400, 380), fill=(220, 160, 70))
    image.save(image_path)
    manifest = {
        "backend": "pillow-fallback",
        "source": "chat",
        "visual_processing": {"motion_renderer": "CinematicVisualEngine"},
        "scenes": [{
            "asset": str(image_path), "asset_sha256": __import__("hashlib").sha256(image_path.read_bytes()).hexdigest(),
            "text_sha256": "text", "backend": "pillow-fallback", "rendered_motion": True,
        }],
    }
    manifest_path = tmp_path / "visual_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    result = validate_visual_manifest(manifest_path, expected_asset_count=1)
    assert result["passed"] is True
