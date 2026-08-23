from pathlib import Path

import pytest
from PIL import Image, ImageDraw

import aurelia.visual_api as visual_api


class FakeResponse:
    def __init__(self, data: bytes, *, content_length: str | None = None):
        self._data = data
        self._offset = 0
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = content_length

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            result = self._data[self._offset:]
            self._offset = len(self._data)
            return result
        result = self._data[self._offset:self._offset + size]
        self._offset += len(result)
        return result


def _valid_png_bytes(tmp_path: Path) -> bytes:
    image = Image.effect_noise((512, 512), 24).convert("RGB")
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, 470, 470), outline=(240, 180, 80), width=12)
    draw.ellipse((140, 120, 380, 360), fill=(80, 180, 230))
    source = tmp_path / "provider.png"
    image.save(source, format="PNG")
    return source.read_bytes()


def test_pollinations_validates_and_atomically_publishes(monkeypatch, tmp_path: Path):
    data = _valid_png_bytes(tmp_path)
    monkeypatch.setattr(
        visual_api.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse(data, content_length=str(len(data))),
    )
    output = tmp_path / "nested" / "shot.png"
    assert visual_api._via_pollinations("space", 7, 512, 512, output) is True
    assert output.is_file() and output.stat().st_size > 5000
    assert not output.with_name(f".{output.name}.part").exists()
    with Image.open(output) as image:
        image.verify()


def test_provider_retries_timeout_then_succeeds(monkeypatch, tmp_path: Path):
    data = _valid_png_bytes(tmp_path)
    attempts = {"count": 0}

    def flaky_urlopen(request, timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise TimeoutError("read timed out")
        return FakeResponse(data, content_length=str(len(data)))

    monkeypatch.setattr(visual_api.urllib.request, "urlopen", flaky_urlopen)
    monkeypatch.setattr(visual_api.time, "sleep", lambda seconds: None)
    output = tmp_path / "retry.png"
    assert visual_api._via_pollinations("space", 7, 512, 512, output) is True
    assert attempts["count"] == 2


def test_provider_reports_incomplete_response_and_cleans_partial(monkeypatch, tmp_path: Path):
    data = _valid_png_bytes(tmp_path)
    monkeypatch.setattr(
        visual_api.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse(data, content_length=str(len(data) + 11)),
    )
    monkeypatch.setattr(visual_api.time, "sleep", lambda seconds: None)
    output = tmp_path / "incomplete.png"
    with pytest.raises(visual_api.ProviderRequestError, match="incomplete response"):
        visual_api._via_pollinations("space", 7, 512, 512, output)
    assert not output.exists()
    assert not output.with_name(f".{output.name}.part").exists()


def test_provider_retries_are_bounded_and_failure_is_actionable(monkeypatch, tmp_path: Path):
    attempts = {"count": 0}

    def canceled_urlopen(request, timeout):
        attempts["count"] += 1
        raise TimeoutError("operation canceled")

    monkeypatch.setattr(visual_api.urllib.request, "urlopen", canceled_urlopen)
    monkeypatch.setattr(visual_api.time, "sleep", lambda seconds: None)
    output = tmp_path / "canceled.png"
    with pytest.raises(visual_api.ProviderRequestError, match=r"failed after 3 attempts"):
        visual_api._via_pollinations("space", 7, 512, 512, output)
    assert attempts["count"] == 3
    assert not output.exists()
