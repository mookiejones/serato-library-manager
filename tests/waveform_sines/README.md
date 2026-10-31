# Waveform decode fixtures

One-second 1 kHz mono sines. They are not Serato libraries and they contain
no user audio. `tests/test_waveform.py` copies one into a temp directory when
the macOS or Windows runner cannot generate the same file itself.

Regenerate with ffmpeg:

```bash
ffmpeg -y -f lavfi -i "sine=frequency=1000:duration=1:sample_rate=44100" -c:a aac -b:a 96k -ac 1 tests/waveform_sines/tone-aac.m4a
ffmpeg -y -f lavfi -i "sine=frequency=1000:duration=1:sample_rate=44100" -c:a alac -ac 1 tests/waveform_sines/tone-alac.m4a
ffmpeg -y -f lavfi -i "sine=frequency=1000:duration=1:sample_rate=44100" -f adts -c:a aac -b:a 96k -ac 1 tests/waveform_sines/tone.aac
```
