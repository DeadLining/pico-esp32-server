"""Pico Server bridge for the OpenAI-compatible cascaded full-duplex service.

This module is deliberately independent of the legacy ASR/TTS pipeline. A
ConnectionHandler can opt into it after device authentication without changing
its existing provider lifecycle. Audio is PCM16 mono; the caller owns Opus
codec conversion at the Pico boundary.
"""
from __future__ import annotations

import asyncio
import base64
import json
import inspect
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

import websockets


class AecProcessor(Protocol):
    def feed_playback_reference(self, pcm: bytes) -> None: ...
    def process_capture(self, pcm: bytes) -> bytes: ...


class PassthroughAec:
    """Safe default until a real AEC3 adapter is configured."""

    def feed_playback_reference(self, pcm: bytes) -> None:
        return None

    def process_capture(self, pcm: bytes) -> bytes:
        return pcm


@dataclass(frozen=True)
class PlaybackAudio:
    pcm: bytes
    response_id: str | None
    generation: int


class FullDuplexSession:
    """One device session connected to the remote Realtime service."""

    def __init__(
        self,
        url: str,
        *,
        session_id: str | None = None,
        aec: AecProcessor | None = None,
        max_audio_frames: int = 64,
        websocket_factory: Callable[..., Awaitable[Any]] | None = None,
    ) -> None:
        if not url.startswith(("ws://", "wss://")):
            raise ValueError("full-duplex URL must use ws:// or wss://")
        if max_audio_frames < 1:
            raise ValueError("max_audio_frames must be positive")
        self.url = url
        self.session_id = session_id
        self.aec = aec or PassthroughAec()
        self.audio_queue: asyncio.Queue[PlaybackAudio] = asyncio.Queue(maxsize=max_audio_frames)
        self.websocket: Any | None = None
        self.websocket_factory = websocket_factory or websockets.connect
        self.generation = 0
        self.active_response_id: str | None = None
        self._closed = False

    async def connect(self) -> None:
        if self.websocket is not None:
            return
        connection = self.websocket_factory(self.url, ping_interval=20, ping_timeout=20)
        self.websocket = await connection if inspect.isawaitable(connection) else connection
        self._closed = False

    async def update(
        self,
        *,
        instructions: str | None = None,
        voice: str | None = None,
        interruption_route: str = "semantic",
    ) -> None:
        if interruption_route not in {"keyword", "semantic"}:
            raise ValueError("interruption_route must be keyword or semantic")
        session: dict[str, Any] = {
            "type": "realtime",
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": 24000},
                    "turn_detection": {
                        "type": "server_vad",
                        "interrupt_response": True,
                    },
                },
                "output": {"format": {"type": "audio/pcm", "rate": 24000}},
            },
        }
        if instructions is not None:
            session["instructions"] = instructions
        if voice is not None:
            session["audio"]["output"]["voice"] = voice
        await self._send({"type": "session.update", "session": session})

    async def feed_playback_reference(self, pcm: bytes) -> None:
        if pcm:
            self.aec.feed_playback_reference(pcm)

    async def send_pcm(self, pcm: bytes) -> None:
        if not pcm:
            return
        cleaned = self.aec.process_capture(pcm)
        if cleaned:
            await self._send({
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(cleaned).decode("ascii"),
            })

    async def cancel_response(self) -> None:
        self.generation += 1
        self.active_response_id = None
        self._clear_audio_queue()
        await self._send({"type": "response.cancel"})

    async def handle_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        if event_type == "response.created":
            response = event.get("response") or {}
            self.active_response_id = response.get("id")
            return
        if event_type == "response.output_audio.delta":
            response_id = event.get("response_id") or self.active_response_id
            # After cancel there is no active response; late frames from the
            # canceled response must never re-enter the playback queue.
            if not self.active_response_id or response_id != self.active_response_id:
                return
            try:
                pcm = base64.b64decode(event.get("delta", ""), validate=True)
            except (ValueError, TypeError):
                return
            if not pcm:
                return
            frame = PlaybackAudio(pcm, response_id, self.generation)
            if self.audio_queue.full():
                # Never let one slow hardware client grow memory without bound.
                self.audio_queue.get_nowait()
            self.audio_queue.put_nowait(frame)
            return
        if event_type == "response.done":
            response = event.get("response") or {}
            if response.get("id") == self.active_response_id:
                self.active_response_id = None

    async def next_audio(self) -> PlaybackAudio:
        return await self.audio_queue.get()

    async def receive_once(self) -> dict[str, Any]:
        if self.websocket is None:
            raise RuntimeError("full-duplex session is not connected")
        raw = await self.websocket.recv()
        event = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(event, dict):
            raise ValueError("upstream event must be a JSON object")
        await self.handle_event(event)
        return event

    async def close(self) -> None:
        self._closed = True
        self._clear_audio_queue()
        self.active_response_id = None
        if self.websocket is not None:
            await self.websocket.close()
            self.websocket = None

    async def _send(self, event: dict[str, Any]) -> None:
        if self.websocket is None or self._closed:
            raise RuntimeError("full-duplex session is not connected")
        await self.websocket.send(json.dumps(event, ensure_ascii=False))

    def _clear_audio_queue(self) -> None:
        while True:
            try:
                self.audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                return

class PcmFrameAccumulator:
    """Turns arbitrary PCM chunks into fixed-size PCM16 frames."""

    def __init__(self, samples_per_frame: int):
        if samples_per_frame <= 0:
            raise ValueError("samples_per_frame must be positive")
        self.frame_bytes = samples_per_frame * 2
        self._buffer = bytearray()

    def push(self, pcm: bytes) -> list[bytes]:
        if len(pcm) % 2:
            raise ValueError("PCM16 data must contain complete samples")
        self._buffer.extend(pcm)
        frames = []
        while len(self._buffer) >= self.frame_bytes:
            frames.append(bytes(self._buffer[:self.frame_bytes]))
            del self._buffer[:self.frame_bytes]
        return frames

    def clear(self) -> None:
        self._buffer.clear()


class OpusPcmCodec:
    """Per-device Opus codec at the negotiated Pico sample rate."""

    def __init__(self, sample_rate: int = 24000, channels: int = 1):
        import opuslib_next

        if channels != 1:
            raise ValueError("Pico full-duplex currently supports mono audio only")
        self.sample_rate = sample_rate
        self.decoder = opuslib_next.Decoder(sample_rate, channels)
        self.encoder = opuslib_next.Encoder(
            sample_rate, channels, opuslib_next.APPLICATION_AUDIO
        )

    def decode(self, packet: bytes, frame_samples: int) -> bytes:
        return bytes(self.decoder.decode(packet, frame_samples))

    def encode(self, pcm: bytes) -> bytes:
        return bytes(self.encoder.encode(pcm, len(pcm) // 2))

class DeviceFullDuplexBridge:
    """Connects a Pico Opus device to one FullDuplexSession.

    The callbacks are supplied by ConnectionHandler so this module does not
    know the Pico JSON control-message format. `send_opus` is the only path
    back to the device; `on_event` receives upstream transcripts/status.
    """

    def __init__(
        self,
        session: FullDuplexSession,
        codec: OpusPcmCodec,
        *,
        send_opus: Callable[[bytes], Awaitable[None]],
        on_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        frame_samples: int | None = None,
    ) -> None:
        self.session = session
        self.codec = codec
        self.send_opus = send_opus
        self.on_event = on_event
        self.frame_samples = frame_samples or codec.sample_rate * 60 // 1000
        self._output_frames = PcmFrameAccumulator(self.frame_samples)
        self._tasks: list[asyncio.Task] = []
        self._stopped = False

    async def start(self, *, instructions: str | None = None, voice: str | None = None) -> None:
        await self.session.connect()
        await self.session.update(instructions=instructions, voice=voice)
        self._stopped = False
        self._tasks = [
            asyncio.create_task(self._upstream_loop(), name="pico-full-duplex-upstream"),
            asyncio.create_task(self._playback_loop(), name="pico-full-duplex-playback"),
        ]

    async def ingest_opus(self, packet: bytes) -> None:
        if self._stopped or not packet:
            return
        pcm = self.codec.decode(packet, self.frame_samples)
        await self.session.send_pcm(pcm)

    async def cancel(self) -> None:
        if not self._stopped:
            await self.session.cancel_response()
            self._output_frames.clear()

    async def stop(self) -> None:
        self._stopped = True
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        await self.session.close()
        self._output_frames.clear()

    async def _upstream_loop(self) -> None:
        try:
            while not self._stopped:
                event = await self.session.receive_once()
                if self.on_event:
                    await self.on_event(event)
        except (asyncio.CancelledError, websockets.exceptions.ConnectionClosed):
            return

    async def _playback_loop(self) -> None:
        try:
            while not self._stopped:
                frame = await self.session.next_audio()
                if frame.generation != self.session.generation:
                    continue
                await self.session.feed_playback_reference(frame.pcm)
                for pcm_frame in self._output_frames.push(frame.pcm):
                    await self.send_opus(self.codec.encode(pcm_frame))
        except asyncio.CancelledError:
            return
