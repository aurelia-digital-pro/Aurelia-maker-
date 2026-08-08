"""Aurelia Maker — main CLI orchestrator (MVP)

Usage examples:

# Generate from script file
python aurelia/generate.py generate --script scripts/example.txt --episode 0012 --profile both

# Start chat REPL (basic local agent)
python aurelia/generate.py chat

This MVP is CLI-first. It will:
- Plan scenes (paragraph split or optional local LLM)
- Generate narration (pyttsx3)
- Produce per-scene cinematic PNGs (Pillow)
- Render per-scene video clips with zoom/pan using ffmpeg
- Concatenate with transitions, mix narration + music, and export MP4s
"""
import os
import sys
import json
import subprocess
import math
import uuid
from pathlib import Path
import click
from aurelia import planner, tts, visuals, audio_util, editor

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'output'
OUTPUT.mkdir(exist_ok=True)

@click.group()
def cli():
    pass

@cli.command()
@click.option('--script', required=False, help='Path to script text file. If omitted, opens chat to compose script.')
@click.option('--episode', default='0001', help='Episode id')
@click.option('--profile', default='both', type=click.Choice(['youtube','tiktok','both']), help='Target profile')
def generate(script, episode, profile):
    """Generate full episode end-to-end"""
    # 1. Load script
    if script:
        s = Path(script)
        if not s.exists():
            print('Script file not found:', script)
            sys.exit(1)
        text = s.read_text(encoding='utf-8')
    else:
        print('No script path provided. Launching chat planner...')
        text = planner.chat_compose()

    project_dir = OUTPUT / f'episode-{episode}'
    project_dir.mkdir(parents=True, exist_ok=True)

    # 2. Plan scenes
    print('-- planning scenes')
    scenes = planner.plan_scenes(text)
    (project_dir / 'scenes.json').write_text(json.dumps(scenes, indent=2, ensure_ascii=False), encoding='utf-8')

    # 3. Generate narration
    print('-- generating narration WAV')
    narration_path = project_dir / 'narration.wav'
    tts.synthesize_script(text, narration_path)

    # 4. Split narration by scene durations
    print('-- splitting narration timings per scene')
    scene_timings = audio_util.split_audio_proportional(narration_path, scenes)
    (project_dir / 'scene_timings.json').write_text(json.dumps(scene_timings, indent=2, ensure_ascii=False), encoding='utf-8')

    # 5. Generate subtitles (approximate)
    print('-- generating subtitles (SRT)')
    subs_path = project_dir / f'episode-{episode}.srt'
    audio_util.generate_srt(text, narration_path, subs_path)

    # 6. Generate visuals (PNGs) for each scene
    print('-- generating visuals for each scene')
    visuals_dir = project_dir / 'visuals'
    visuals_dir.mkdir(exist_ok=True)
    for idx, sc in enumerate(scenes):
        duration = scene_timings[idx]['duration']
        out_png = visuals_dir / f'scene-{idx+1}.png'
        visuals.render_scene_png(sc, out_png)

    # 7. Render scene clips (mp4) with pan/zoom via ffmpeg
    print('-- rendering scene clips')
    clips = []
    for idx, st in enumerate(scene_timings):
        png = visuals_dir / f'scene-{idx+1}.png'
        clip = project_dir / f'scene-{idx+1}.mp4'
        visuals.render_png_to_clip(png, clip, duration=st['duration'], profile=profile)
        clips.append(str(clip))

    # 8. Concatenate clips with transitions and mix audio + music
    print('-- assembling final video')
    final_base = project_dir / f'episode-{episode}'
    if profile in ('youtube','both'):
        final_y = str(final_base) + '-youtube.mp4'
        editor.assemble(clips, narration_path, subs_path, final_y, profile='youtube')
    if profile in ('tiktok','both'):
        final_t = str(final_base) + '-tiktok.mp4'
        editor.assemble(clips, narration_path, subs_path, final_t, profile='tiktok')

    print('Done. Outputs in', str(project_dir))

@cli.command()
def chat():
    """Simple chat REPL to control the agent (very lightweight)"""
    print('Aurelia Maker chat. Type commands or narrative. "exit" to quit.')
    while True:
        v = input('> ')
        if v.strip().lower() in ('exit','quit'):
            break
        # Simple commands supported
        if v.startswith('Create Episode') or v.lower().startswith('create episode'):
            # parse episode id and topic
            print('Received create command — invoking generate pipeline')
            # naive: ask for script file path
            script_file = input('Path to script txt (or leave empty to compose here): ').strip()
            episode = '0001'
            try:
                ep = v.split()[2]
                episode = ep
            except Exception:
                pass
            ctx = input('Profile (youtube/tiktok/both) [both]: ').strip() or 'both'
            if script_file:
                os.system(f'python "{__file__}" generate --script "{script_file}" --episode {episode} --profile {ctx}')
            else:
                print('Please provide script in the prompt — end with a blank line:')
                lines = []
                while True:
                    l = input()
                    if l.strip() == '':
                        break
                    lines.append(l)
                tmp = ROOT / 'tmp_script.txt'
                tmp.write_text('\n'.join(lines), encoding='utf-8')
                os.system(f'python "{__file__}" generate --script "{str(tmp)}" --episode {episode} --profile {ctx}')
        else:
            # pass to planner's chat for refinement
            reply = planner.chat(v)
            print('\n'.join(reply))

if __name__ == '__main__':
    cli()
