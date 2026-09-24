# Pico full-duplex playback contract

## Direction and ownership

The Mac Pico Server bridge is the sole audio producer for a full-duplex device.
The 95 realtime service supplies PCM16 mono at 24 kHz. The board captures Opus
at 16 kHz; downstream Opus is encoded at the server-hello output rate (24 kHz by
default), not at the capture rate. Every Opus frame is 60 ms.

## Interruption

Semantic `yield`/`wait`, cancelled responses, and output-buffer clear invalidate
the playback generation. This remains true after upstream `response.done`, while
local audio is still queued. Speech-start alone does not cancel in semantic mode.
Old response IDs and every individual outgoing packet are checked. A new response
replaces old playback; it cannot inherit PCM or resampling residue.

`tts.start`, binary frames and `tts.stop` use one ordered playback worker and one
send lock. `tts.abort` bypasses queued audio after invalidation, using the same
lock. Normal stop flushes the final partial PCM frame and lets the board drain;
abort discards audio. Sending is paced against an absolute media clock, with one
frame of initial jitter reserve and bounded catchup, rather than whole-reply bursts.
Overflow fails the session instead of dropping arbitrary samples or preventing
receipt of cancellation. A fatal bridge failure closes the device transport so
the next connection does not keep using a dead bridge.

The firmware serializes incoming controls/audio on the application task, clears
queues on abort/disconnect and checks the generation under the decoder lock before
allowing an old task to mutate decoder state. Decoder and resampler resets are
serialized with decoding. The physical DAC may finish a fragment already written;
software cannot retract that fragment. MQTT/UDP has no shared ordering or packet
response ID and is not a validated transport for this full-duplex mode.

## Validation

Run from the server checkout (use an empty test configuration, not production
credentials):

```sh
PYTEST_CONFIG_FILE=/tmp/pico-test-config.yaml PYTHONPATH=main/pico-server \
  python3 -m pytest -q main/pico-server/tests/core/test_duplex_interruptions.py \
  main/pico-server/tests/core/test_full_duplex_session.py
```

The interruption tests restore real asyncio sleep because the legacy suite's
conftest replaces it with a no-op. They cover semantic cancellation, cancellation
after response completion, stale IDs, multi-frame chunks, PCM tails, queue overflow,
concurrent receive/playback, upstream disconnect and resampling continuity.

After flashing, physically verify a long reply, interrupt mid-sentence several
times, then request another reply; old content must not return. Verify microphone
capture continues during playback, disconnect/reconnect, and the final syllable
of normal replies. Software test success is not acoustic acceptance. The lightweight
reference echo suppressor is not WebRTC AEC3 and cannot guarantee echo-free physical
operation on every board.
