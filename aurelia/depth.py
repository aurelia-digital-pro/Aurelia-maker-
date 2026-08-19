from pathlib import Path

def process_depth(data: dict) -> dict:
    output = data.get("output")
    source = (
        data.get("input")
        or data.get("asset")
        or data.get("visual")
        or data.get("camera")
    )

    if output is None:
        raise ValueError("DEPTH requires output path")
    if source is None:
        raise ValueError("DEPTH requires an input artifact")

    source_path = Path(source)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not source_path.exists():
        raise FileNotFoundError(source_path)

    output_path.write_bytes(source_path.read_bytes())

    return {
        "stage": "DEPTH",
        "artifact": str(output_path),
    }
