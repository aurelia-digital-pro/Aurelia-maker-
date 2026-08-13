from pathlib import Path

def process_motion(data: dict) -> dict:
    output = data.get("output")
    source = (
        data.get("input")
        or data.get("depth")
        or data.get("camera")
        or data.get("visual")
    )

    if output is None:
        raise ValueError("MOTION requires output path")
    if source is None:
        raise ValueError("MOTION requires an input artifact")

    source_path = Path(source)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not source_path.exists():
        raise FileNotFoundError(source_path)

    output_path.write_bytes(source_path.read_bytes())

    return {
        "stage": "MOTION",
        "artifact": str(output_path),
    }
