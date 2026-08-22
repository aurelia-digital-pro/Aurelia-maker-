from pathlib import Path
from aurelia.media import generate_sound_design, probe_duration

out = Path('/tmp/aurelia-sound-design-smoke.wav')
generate_sound_design(12.0, [6.0], out)
assert out.is_file() and out.stat().st_size > 1000
assert probe_duration(out) >= 11.0
print(f'SOUND DESIGN PASS: {out} {out.stat().st_size} bytes {probe_duration(out):.2f}s')
