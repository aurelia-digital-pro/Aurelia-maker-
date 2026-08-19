"""Planner module: scene planning, simple chat composer, optional local LLM hooks."""
import os
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]

def plan_scenes(script_text):
    # Simple paragraph splitter: each blank-line separates a scene.
    paras = [p.strip() for p in script_text.split('\n\n') if p.strip()]
    scenes = []
    for i,p in enumerate(paras):
        title = p.split('.')[0][:60]
        scenes.append({'id': i+1, 'title': title, 'text': p})
    return scenes

def chat_compose():
    print('Compose script in-line. End with a blank line.')
    lines = []
    while True:
        try:
            l = input()
        except EOFError:
            break
        if l.strip() == '':
            break
        lines.append(l)
    return '\n\n'.join(lines)

def chat(prompt):
    # Optional: if ollama or other local LLM is installed, call it.
    # Fallback: echo with guidance.
    try:
        # try ollama
        import subprocess
        proc = subprocess.run(['ollama','chat','--prompt', prompt], capture_output=True, text=True, timeout=30)
        if proc.returncode == 0:
            return proc.stdout.splitlines()
    except Exception:
        pass
    # Fallback heuristic reply
    return ["(local-agent) I received:", prompt, "-- use 'Create Episode <id>' in the chat REPL to generate."]
