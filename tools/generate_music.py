# small helper to generate an ambient music loop using pydub

from pydub import AudioSegment
from pydub.generators import Sine

seg = Sine(110).to_audio_segment(duration=30000).apply_gain(-18)
seg = seg.overlay(Sine(220).to_audio_segment(duration=30000).apply_gain(-24))
seg.export('assets/ambient_loop.wav', format='wav')
