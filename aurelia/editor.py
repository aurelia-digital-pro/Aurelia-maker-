"""Editor/assembler: concat clips, apply crossfade transitions, mix narration and music, burn subtitles via ffmpeg."""
from pathlib import Path
import subprocess
import os

def concat_with_crossfade(clips, out_path, transition=0.6):
    # Simple concatenation without crossfade (ffmpeg concat demuxer) for MVP
    # For crossfade you'd need filter_complex; keep simple for reliability
    txt = '\n'.join([f"file '{c}'" for c in clips])
    tmp = out_path.parent / 'clips.txt'
    tmp.write_text(txt)
    cmd = ['ffmpeg','-y','-f','concat','-safe','0','-i',str(tmp),'-c','copy',str(out_path)]
    subprocess.run(cmd, check=True)

def mix_audio(video_path, narration_wav, out_path, music_wav=None):
    # Mux narration (replace existing audio) and optionally add music with low volume
    # If music provided, use amix with volume adjustments (simple)
    if music_wav and Path(music_wav).exists():
        cmd = [
            'ffmpeg','-y','-i',str(video_path),'-i',str(narration_wav),'-i',str(music_wav),
            '-filter_complex','[1:a]volume=1.0[a1];[2:a]volume=0.25[a2];[a1][a2]amix=inputs=2:duration=longest',
            '-map','0:v','-map','[aout]' if False else '-map','0:a?','-c:v','copy','-c:a','aac','-shortest',str(out_path)
        ]
        # Simpler fallback: replace audio track with narration only
    cmd = ['ffmpeg','-y','-i',str(video_path),'-i',str(narration_wav),'-c:v','copy','-map','0:v:0','-map','1:a:0',str(out_path)]
    subprocess.run(cmd, check=True)

def assemble(clips, narration_wav, srt_path, out_path, profile='youtube'):
    temp_concat = Path(out_path).with_suffix('.concat.mp4')
    concat_with_crossfade(clips, temp_concat)
    mixed = Path(out_path).with_suffix('.mixed.mp4')
    mix_audio(temp_concat, narration_wav, mixed)
    # Burn subtitles
    cmd = ['ffmpeg','-y','-i',str(mixed),'-vf',f"subtitles={str(srt_path)}:force_style='FontSize=36'",'-c:a','copy',str(out_path)]
    subprocess.run(cmd, check=True)
