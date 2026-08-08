"""Audio utilities: split narration into scene timings, generate SRT"""
from pydub import AudioSegment
from pathlib import Path
import math

def split_audio_proportional(narration_path: Path, scenes):
    audio = AudioSegment.from_file(narration_path)
    total_ms = len(audio)
    n = len(scenes)
    # simple proportional split by number of scenes
    per_ms = total_ms / n
    res = []
    cur = 0
    for i in range(n):
        dur = int(per_ms)
        res.append({'scene': i+1, 'start_ms': int(cur), 'duration': dur/1000.0})
        cur += dur
    return res

def ms_to_srt_time(ms):
    hours = ms // 3600000
    ms = ms % 3600000
    minutes = ms // 60000
    ms = ms % 60000
    seconds = ms // 1000
    milliseconds = ms % 1000
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

def generate_srt(script_text, narration_path: Path, out_srt: Path):
    audio = AudioSegment.from_file(narration_path)
    total_ms = len(audio)
    lines = [l.strip() for l in script_text.split('\n') if l.strip()]
    count = len(lines)
    per = total_ms // max(1,count)
    cur = 0
    with open(out_srt, 'w', encoding='utf-8') as f:
        idx = 1
        for line in lines:
            start = cur
            end = min(cur + per, total_ms-1)
            f.write(str(idx) + '\n')
            f.write(ms_to_srt_time(start) + ' --> ' + ms_to_srt_time(end) + '\n')
            f.write(line + '\n\n')
            cur += per
            idx += 1
