"""TTS utilities using pyttsx3 (offline)"""
import pyttsx3
from pathlib import Path
import time

def synthesize_script(text, out_wav: Path):
    engine = pyttsx3.init()
    # set some voice properties for a deeper, slower voice
    try:
        engine.setProperty('rate', 160)
        engine.setProperty('volume', 0.95)
    except Exception:
        pass
    engine.save_to_file(text, str(out_wav))
    engine.runAndWait()
    # give the file a moment
    time.sleep(0.5)
