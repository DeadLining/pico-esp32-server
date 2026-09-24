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
        payload = base64.b64encode(b"old-audio").decode()
        await session.handle_event({"type": "response.created", "response": {"id": "r1"}})
        await session.handle_event({"type": "response.output_audio.delta", "delta": payload, "response_id": "r1"})
        first = await session.next_audio()
        assert first.pcm == b"old-audio"
        assert first.generation == 0
        await session.cancel_response()
        assert session.generation == 1
        assert ws.sent[-1] == {"type": "response.cancel"}
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
