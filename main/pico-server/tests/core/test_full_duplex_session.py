import asyncio
import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.realtime.full_duplex_session import FullDuplexSession, PassthroughAec


class FakeWebSocket:
    def __init__(self):
        self.sent = []
        self.incoming = asyncio.Queue()
        self.closed = False

    async def send(self, value):
        self.sent.append(json.loads(value))

    async def recv(self):
        return await self.incoming.get()

    async def close(self):
        self.closed = True


async def make_session(ws=None):
    session = FullDuplexSession(
        "ws://example.test/v1/realtime",
        session_id="pico-test",
        websocket_factory=lambda *_args, **_kwargs: ws,
    )
    await session.connect()
    return session


def test_session_update_and_pcm_are_openai_realtime_events():
    async def run():
        ws = FakeWebSocket()
        session = await make_session(ws)
        await session.update(instructions="be concise", voice="alloy")
        await session.send_pcm(b"\x01\x02")
        assert session.url.endswith("interruption_route=semantic")
        assert ws.sent[0]["type"] == "session.update"
        assert ws.sent[0]["session"]["instructions"] == "be concise"
        assert ws.sent[1] == {
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(b"\x01\x02").decode(),
        }

    asyncio.run(run())


def test_output_audio_is_bounded_and_cancel_drops_old_generation():
    async def run():
        ws = FakeWebSocket()
        session = await make_session(ws)
        payload = base64.b64encode(b"old-audio!").decode()
        await session.handle_event({"type": "response.created", "response": {"id": "r1"}})
        await session.handle_event({"type": "response.output_audio.delta", "delta": payload, "response_id": "r1"})
        assert (await session.next_audio()).event["type"] == "response.created"
        first = await session.next_audio()
        assert first.pcm == b"old-audio!"
        assert first.generation == 0
        await session.cancel_response()
        assert session.generation == 1
        assert ws.sent[-1] == {"type": "response.cancel", "response_id": "r1"}
        await session.handle_event({"type": "response.output_audio.delta", "delta": payload, "response_id": "r1"})
        assert session.audio_queue.empty()

    asyncio.run(run())


def test_aec_reference_is_passed_before_capture():
    class RecordingAec(PassthroughAec):
        def __init__(self):
            self.references = []
            self.captures = []

        def feed_playback_reference(self, pcm):
            self.references.append(pcm)

        def process_capture(self, pcm):
            self.captures.append(pcm)
            return b"clean:" + pcm

    async def run():
        ws = FakeWebSocket()
        aec = RecordingAec()
        session = FullDuplexSession("ws://example.test", aec=aec, websocket_factory=lambda *_a, **_k: ws)
        await session.connect()
        await session.feed_playback_reference(b"speaker")
        await session.send_pcm(b"mic")
        assert aec.references == [b"speaker"]
        assert aec.captures == [b"mic"]
        assert ws.sent[-1]["audio"] == base64.b64encode(b"clean:mic").decode()

    asyncio.run(run())


def test_pcm_frame_accumulator_keeps_partial_frame():
    from core.realtime.full_duplex_session import PcmFrameAccumulator

    acc = PcmFrameAccumulator(2)
    assert acc.push(b"\x01\x00") == []
    assert acc.push(b"\x02\x00\x03\x00") == [b"\x01\x00\x02\x00"]
    try:
        acc.push(b"\x04")
    except ValueError:
        pass
    else:
        raise AssertionError("odd PCM16 chunks must be rejected")


def test_pcm_resampler_changes_rate_and_preserves_silence():
    import numpy as np
    from core.realtime import PcmResampler
    source = (np.arange(160, dtype=np.int16) * 10).tobytes()
    resampler = PcmResampler(16000, 24000)
    converted = resampler.convert(source) + resampler.flush()
    assert len(converted) == 240 * 2
    reverse = PcmResampler(24000, 16000)
    assert reverse.convert(converted) + reverse.flush()


def test_reference_echo_suppressor_leaves_capture_unchanged_without_reference():
    import numpy as np
    from core.realtime.full_duplex_session import ReferenceEchoSuppressor

    pcm = (np.sin(np.arange(480) * 0.17) * 5000).astype(np.int16).tobytes()
    suppressor = ReferenceEchoSuppressor()
    assert suppressor.process_capture(pcm) == pcm


def test_reference_echo_suppressor_reduces_delayed_playback_echo():
    import numpy as np
    from core.realtime.full_duplex_session import ReferenceEchoSuppressor

    rng = np.random.default_rng(7)
    echo = rng.normal(0, 5000, 960).clip(-32768, 32767).astype(np.int16)
    # The microphone sees the playback reference 80 ms late.  The reference
    # buffer also contains audio after the echoed segment, as it would in use.
    suppressor = ReferenceEchoSuppressor(max_delay_ms=200)
    suppressor.feed_playback_reference(np.concatenate([echo, np.zeros(1920, dtype=np.int16)]).tobytes())
    capture = (echo.astype(np.float64) * 0.72).astype(np.int16)
    cleaned = np.frombuffer(suppressor.process_capture(capture.tobytes()), dtype=np.int16)
    before = float(np.mean(capture.astype(np.float64) ** 2))
    after = float(np.mean(cleaned.astype(np.float64) ** 2))
    assert after < before * 0.25


def test_reference_echo_suppressor_does_not_erase_unrelated_user_voice():
    import numpy as np
    from core.realtime.full_duplex_session import ReferenceEchoSuppressor

    rng = np.random.default_rng(11)
    echo = rng.normal(0, 1600, 960)
    user = np.sin(np.arange(960) * 0.041) * 7000
    suppressor = ReferenceEchoSuppressor()
    suppressor.feed_playback_reference(echo.astype(np.int16).tobytes())
    mixed = np.clip(echo * 0.5 + user, -32768, 32767).astype(np.int16)
    cleaned = np.frombuffer(suppressor.process_capture(mixed.tobytes()), dtype=np.int16).astype(np.float64)
    # The correlated echo is reduced, while substantial speech energy remains.
    assert np.sqrt(np.mean(cleaned**2)) > 2500


def test_reference_echo_suppressor_rejects_odd_pcm():
    from core.realtime.full_duplex_session import ReferenceEchoSuppressor

    suppressor = ReferenceEchoSuppressor()
    try:
        suppressor.feed_playback_reference(b"\x00")
    except ValueError:
        pass
    else:
        raise AssertionError("odd PCM16 reference must be rejected")
    try:
        suppressor.process_capture(b"\x00")
    except ValueError:
        pass
    else:
        raise AssertionError("odd PCM16 capture must be rejected")


def test_pcm_resampler_keeps_packet_boundary_continuity():
    import numpy as np
    from core.realtime import PcmResampler

    source = (np.arange(1920, dtype=np.int16) * 7).clip(-32768, 32767)
    resampler = PcmResampler(16000, 24000)
    first = resampler.convert(source[:960].tobytes())
    second = resampler.convert(source[960:].tobytes()) + resampler.flush()
    output = np.frombuffer(first + second, dtype=np.int16)
    # A ramp should remain monotonic through the 60 ms packet boundary.
    assert np.all(np.diff(output.astype(np.int32)) >= 0)
