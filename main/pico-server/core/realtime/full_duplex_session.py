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
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

import websockets


class AecProcessor(Protocol):
    def feed_playback_reference(self, pcm: bytes) -> None: ...
    def process_capture(self, pcm: bytes) -> bytes: ...


class PassthroughAec:
    """Disable echo processing explicitly (useful for tests and diagnostics)."""

    def feed_playback_reference(self, pcm: bytes) -> None:
        return None

    def process_capture(self, pcm: bytes) -> bytes:
        return pcm


class ReferenceEchoSuppressor:
    """Lightweight adaptive acoustic echo suppressor for PCM16 mono audio.

    This is intentionally not marketed as WebRTC AEC3.  It uses the playback
    signal as a reference, searches a bounded delay window, estimates a
    normalized echo gain, and subtracts only a correlated component.  That is
    enough to suppress the speaker leakage produced by the small Pico boards
    without treating unrelated microphone speech as echo.
    """

    def __init__(
        self,
        *,
        sample_rate: int = 24_000,
        max_delay_ms: int = 300,
        reference_ms: int = 1_500,
        correlation_threshold: float = 0.55,
        max_gain: float = 0.95,
        search_decimation: int = 4,
    ) -> None:
        if sample_rate <= 0 or max_delay_ms < 0 or reference_ms <= 0:
            raise ValueError("invalid echo suppressor parameters")
        if not 0.0 < correlation_threshold < 1.0:
            raise ValueError("correlation_threshold must be between 0 and 1")
        if max_gain <= 0 or search_decimation <= 0:
            raise ValueError("max_gain and search_decimation must be positive")
        self.sample_rate = sample_rate
        self.max_delay_samples = sample_rate * max_delay_ms // 1000
        self.max_reference_samples = sample_rate * reference_ms // 1000
        self.correlation_threshold = correlation_threshold
        self.max_gain = max_gain
        self.search_decimation = search_decimation
        self._reference = bytearray()
        self._last_reference_at = 0.0

    def feed_playback_reference(self, pcm: bytes) -> None:
        if len(pcm) % 2:
            raise ValueError("PCM16 data must contain complete samples")
        if not pcm:
            return
        self._last_reference_at = time.monotonic()
        self._reference.extend(pcm)
        limit = self.max_reference_samples * 2
        if len(self._reference) > limit:
            del self._reference[:-limit]

    def process_capture(self, pcm: bytes) -> bytes:
        if len(pcm) % 2:
            raise ValueError("PCM16 data must contain complete samples")
        if not pcm or len(self._reference) < 4:
            return pcm
        # Do not compare speech against stale playback from a previous turn.
        # This is important after TTS stops: the next user utterance must pass
        # through even if it happens to resemble an old response.
        if time.monotonic() - self._last_reference_at > (self.max_delay_samples / self.sample_rate) + 0.15:
            return pcm

        import numpy as np

        capture = np.frombuffer(pcm, dtype=np.int16).astype(np.float64)
        reference = np.frombuffer(self._reference, dtype=np.int16).astype(np.float64)
        n = len(capture)
        if len(reference) < n:
            return pcm

        # Search only plausible speaker-to-mic delays.  Decimation keeps this
        # bounded at roughly a few hundred thousand multiply-adds per frame.
        step = self.search_decimation
        capture_search = capture[::step]
        capture_centered = capture_search - capture_search.mean()
        capture_norm = float(np.linalg.norm(capture_centered))
        if capture_norm < 80.0:
            return pcm

        best_corr = 0.0
        best_segment: np.ndarray | None = None
        max_lag = min(self.max_delay_samples, len(reference) - n)
        for lag in range(0, max_lag + 1, step):
            end = len(reference) - lag
            segment = reference[end - n:end:step]
            if len(segment) != len(capture_search):
                continue
            segment_centered = segment - segment.mean()
            ref_norm = float(np.linalg.norm(segment_centered))
            if ref_norm < 80.0:
                continue
            corr = float(np.dot(capture_centered, segment_centered) / (capture_norm * ref_norm))
            if corr > best_corr:
                best_corr = corr
                best_segment = reference[end - n:end]

        if best_segment is None or best_corr < self.correlation_threshold:
            return pcm

        # Estimate the echo gain on the raw waveforms.  Limit cancellation so
        # a false positive cannot erase a user's whole utterance.
        denominator = float(np.dot(best_segment, best_segment))
        if denominator <= 1.0:
            return pcm
        gain = float(np.dot(capture, best_segment) / denominator)
        gain = min(self.max_gain, max(0.0, gain))
        if gain <= 0.02:
            return pcm
        # Correlation is also used as a soft safety factor: weak matches get
        # partial suppression, strong matches get the full estimated gain.
        strength = min(1.0, max(0.0, (best_corr - self.correlation_threshold) / (1.0 - self.correlation_threshold)))
        cleaned = capture - best_segment * gain * (0.35 + 0.65 * strength)
        return np.clip(np.rint(cleaned), -32768, 32767).astype(np.int16).tobytes()


@dataclass(frozen=True)
class PlaybackAudio:
    pcm: bytes
    response_id: str | None
    generation: int
    event: dict[str, Any] | None = None


class FullDuplexSession:
    """One device session connected to the remote Realtime service."""

    def __init__(
        self,
        url: str,
        *,
        session_id: str | None = None,
        aec: AecProcessor | None = None,
        max_audio_frames: int = 64,
        interruption_route: str = "semantic",
        websocket_factory: Callable[..., Awaitable[Any]] | None = None,
    ) -> None:
        if not url.startswith(("ws://", "wss://")):
            raise ValueError("full-duplex URL must use ws:// or wss://")
        if max_audio_frames < 1:
            raise ValueError("max_audio_frames must be positive")
        if interruption_route not in {"keyword", "semantic"}:
            raise ValueError("interruption_route must be keyword or semantic")
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["interruption_route"] = interruption_route
        self.url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
        self.interruption_route = interruption_route
        self.session_id = session_id
        self.aec = aec or ReferenceEchoSuppressor()
        self.audio_queue: asyncio.Queue[PlaybackAudio] = asyncio.Queue(maxsize=max_audio_frames)
        self.websocket: Any | None = None
        self.websocket_factory = websocket_factory or websockets.connect
        self.generation = 0
        self.active_response_id: str | None = None
        self._closed = False
        self.playback_response_id: str | None = None
        self._audio_finished = False

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

    def invalidate_playback(self) -> None:
        self.generation += 1
        self.active_response_id = None
        self.playback_response_id = None
        self._audio_finished = True
        self._clear_audio_queue()

    async def cancel_response(self) -> None:
        response_id = self.active_response_id
        self.invalidate_playback()
        if response_id:
            await self._send({"type": "response.cancel", "response_id": response_id})

    def _enqueue(self, frame: PlaybackAudio) -> None:
        # Never block receipt of semantic cancellation behind playback. Fail
        # explicitly rather than dropping arbitrary audio when a client stalls.
        if self.audio_queue.full() or sum(len(item.pcm) for item in self.audio_queue._queue) + len(frame.pcm) > 24000 * 2 * 30:
            self.invalidate_playback()
            raise BufferError("full-duplex playback queue exceeded capacity")
        self.audio_queue.put_nowait(frame)

    def _finish_audio(self, response_id: str) -> None:
        if self._audio_finished:
            return
        self._audio_finished = True
        self._enqueue(PlaybackAudio(b"", response_id, self.generation,
                      {"type": "response.output_audio.done", "response_id": response_id}))

    async def handle_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        if (event_type == "output_audio_buffer.cleared" or
            (event_type == "input_audio_buffer.speech_started" and self.interruption_route != "semantic") or
            (event_type == "conversation.item.input_audio_transcription.completed" and
             self.interruption_route == "semantic" and event.get("semantic_decision") in {"yield", "wait"})):
            self.invalidate_playback()
            return
        if event_type == "response.created":
            response_id = (event.get("response") or {}).get("id")
            if not response_id or response_id == self.playback_response_id:
                return
            if self.playback_response_id is not None:
                self.invalidate_playback()
            self.active_response_id = self.playback_response_id = response_id
            self._audio_finished = False
            self._enqueue(PlaybackAudio(b"", response_id, self.generation, event))
            return
        if event_type == "response.output_audio.delta":
            response_id = event.get("response_id")
            if not response_id or response_id != self.active_response_id or self._audio_finished:
                return
            encoded = event.get("delta", "")
            if not isinstance(encoded, str) or len(encoded) > 24000 * 2 * 30 * 4 // 3:
                raise ValueError("invalid or oversized upstream audio delta")
            pcm = base64.b64decode(encoded, validate=True)
            if len(pcm) % 2:
                raise ValueError("upstream PCM16 contains an incomplete sample")
            if pcm:
                self._enqueue(PlaybackAudio(pcm, response_id, self.generation))
            return
        if event_type == "response.output_audio.done":
            response_id = event.get("response_id")
            if response_id and response_id == self.playback_response_id:
                self._finish_audio(response_id)
            return
        if event_type == "response.done":
            response = event.get("response") or {}
            response_id = response.get("id")
            if not response_id or response_id != self.playback_response_id:
                return
            if response.get("status") in {"cancelled", "failed", "incomplete"}:
                self.invalidate_playback()
            else:
                self._finish_audio(response_id)
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

    def flush(self) -> list[bytes]:
        if not self._buffer:
            return []
        frame = bytes(self._buffer).ljust(self.frame_bytes, b"\0")
        self._buffer.clear()
        return [frame]

    def clear(self) -> None:
        self._buffer.clear()


class PcmResampler:
    """Streaming mono PCM16 linear resampler with continuous phase.

    The old implementation restarted ``linspace`` for every Opus packet. That
    creates a tiny discontinuity at every 60 ms packet boundary; after several
    packets the audible result can become crackle/static. This implementation
    keeps the interpolation phase and one-sample lookahead across calls.
    """

    def __init__(self, source_rate: int, target_rate: int):
        if source_rate <= 0 or target_rate <= 0:
            raise ValueError("sample rates must be positive")
        self.source_rate = source_rate
        self.target_rate = target_rate
        self._step = source_rate / target_rate
        self._samples = None
        self._buffer_start = 0
        self._next_position = 0.0

    def convert(self, pcm: bytes) -> bytes:
        if not pcm:
            return b""
        if len(pcm) % 2:
            raise ValueError("PCM16 data must contain complete samples")
        if self.source_rate == self.target_rate:
            return pcm

        import numpy as np

        incoming = np.frombuffer(pcm, dtype=np.int16).astype(np.float64)
        if self._samples is None:
            self._samples = incoming
        else:
            self._samples = np.concatenate((self._samples, incoming))

        global_end = self._buffer_start + len(self._samples)
        output: list[float] = []
        # Keep one source sample ahead so interpolation never has to guess the
        # next value at a packet boundary.
        while self._next_position + 1.0 < global_end:
            local = self._next_position - self._buffer_start
            index = int(np.floor(local))
            fraction = local - index
            output.append(float(self._samples[index] * (1.0 - fraction) + self._samples[index + 1] * fraction))
            self._next_position += self._step

        # Retain the sample before the next interpolation point, plus the
        # future samples. This bounds memory while preserving continuity.
        keep_from = max(0, int(np.floor(self._next_position)) - 1 - self._buffer_start)
        if keep_from:
            self._samples = self._samples[keep_from:]
            self._buffer_start += keep_from

        if not output:
            return b""
        return np.clip(np.rint(output), -32768, 32767).astype(np.int16).tobytes()

    def flush(self) -> bytes:
        """Emit the final sample(s) using endpoint clamping and reset state."""
        if self._samples is None or len(self._samples) == 0:
            return b""
        import numpy as np

        global_last = self._buffer_start + len(self._samples) - 1
        output: list[float] = []
        while self._next_position < global_last + 1.0 - 1e-8:
            local = min(max(0.0, self._next_position - self._buffer_start), len(self._samples) - 1)
            index = int(np.floor(local))
            fraction = local - index
            next_index = min(index + 1, len(self._samples) - 1)
            output.append(float(self._samples[index] * (1.0 - fraction) + self._samples[next_index] * fraction))
            self._next_position += self._step
        self.reset()
        if not output:
            return b""
        return np.clip(np.rint(output), -32768, 32767).astype(np.int16).tobytes()

    def reset(self) -> None:
        self._samples = None
        self._buffer_start = 0
        self._next_position = 0.0


class OpusPcmCodec:
    """Per-device Opus codec at the negotiated Pico sample rate."""

    def __init__(self, sample_rate: int = 24000, channels: int = 1, *, output_sample_rate: int | None = None):
        import opuslib_next

        if channels != 1:
            raise ValueError("Pico full-duplex currently supports mono audio only")
        self.sample_rate = sample_rate
        self.output_sample_rate = output_sample_rate or sample_rate
        self.decoder = opuslib_next.Decoder(sample_rate, channels)
        self.encoder = opuslib_next.Encoder(
            self.output_sample_rate, channels, opuslib_next.APPLICATION_AUDIO
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
        self.output_rate = getattr(codec, "output_sample_rate", codec.sample_rate)
        self.input_frame_samples = codec.sample_rate * 60 // 1000
        self.frame_samples = frame_samples or self.output_rate * 60 // 1000
        self.upstream_rate = 24000
        self._input_resampler = PcmResampler(codec.sample_rate, self.upstream_rate)
        self._output_resampler = PcmResampler(self.upstream_rate, self.output_rate)
        self._output_frames = PcmFrameAccumulator(self.frame_samples)
        self._tasks: list[asyncio.Task] = []
        self._stopped = False
        self._send_lock = asyncio.Lock()
        self._playback_generation = session.generation
        self._next_send_at = 0.0

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
        pcm = self.codec.decode(packet, self.input_frame_samples)
        await self.session.send_pcm(self._input_resampler.convert(pcm))

    async def _notify(self, event: dict[str, Any]) -> None:
        if self.on_event:
            await self.on_event(event)

    async def _clear_device_playback(self) -> None:
        async with self._send_lock:
            self._output_frames.clear()
            self._output_resampler.reset()
            self._playback_generation = self.session.generation
            self._next_send_at = 0.0
            await self._notify({"type": "pico.playback.abort", "generation": self.session.generation})

    async def cancel(self) -> None:
        if not self._stopped:
            # Invalidate before any network await; stop hardware even if the
            # upstream cancel request later fails.
            response_id = self.session.active_response_id
            self.session.invalidate_playback()
            await self._clear_device_playback()
            if response_id:
                await self.session._send({"type": "response.cancel", "response_id": response_id})

    async def stop(self) -> None:
        self._stopped = True
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        await self.session.close()
        self._output_frames.clear()

    async def _fail(self, error: Exception) -> None:
        self._stopped = True
        self.session.invalidate_playback()
        for task in self._tasks:
            if task is not asyncio.current_task():
                task.cancel()
        try:
            await self._clear_device_playback()
            await self._notify({"type": "pico.bridge.failed", "error": {"message": str(error)}})
        finally:
            await self.session.close()

    async def _upstream_loop(self) -> None:
        try:
            while not self._stopped:
                generation = self.session.generation
                event = await self.session.receive_once()
                if generation != self.session.generation:
                    await self._clear_device_playback()
                # Playback controls must use the same ordered queue as audio.
                if event.get("type") not in {"response.created", "response.output_audio.delta",
                                              "response.output_audio.done", "response.done"}:
                    await self._notify(event)
        except asyncio.CancelledError:
            return
        except Exception as error:
            await self._fail(error)

    async def _send_frame(self, pcm: bytes, generation: int) -> bool:
        loop = asyncio.get_running_loop()
        await asyncio.sleep(max(0.0, self._next_send_at - loop.time()))
        async with self._send_lock:
            if generation != self.session.generation or self._stopped:
                return False
            started_at = loop.time()
            await self.send_opus(self.codec.encode(pcm))
            # Keep an absolute media clock: encoding/network cost must not be
            # added to every 60 ms frame (that steadily starves the DAC).
            # Two initial packets provide one frame of jitter tolerance; catchup
            # after a stall is bounded, never an entire-response burst.
            duration = len(pcm) / (2 * self.output_rate)
            self._next_send_at = (started_at if self._next_send_at == 0.0 else
                                  max(self._next_send_at, started_at - 2 * duration) + duration)
            # Reference is fed at transmission time, not upstream generation time.
            reference = PcmResampler(self.output_rate, self.upstream_rate)
            await self.session.feed_playback_reference(reference.convert(pcm) + reference.flush())
            return True

    async def _playback_loop(self) -> None:
        try:
            while not self._stopped:
                frame = await self.session.next_audio()
                if frame.generation != self.session.generation:
                    continue
                if self._playback_generation != frame.generation:
                    await self._clear_device_playback()
                if frame.event:
                    if frame.event["type"] == "response.created":
                        async with self._send_lock:
                            if frame.generation == self.session.generation:
                                self._output_frames.clear()
                                self._output_resampler.reset()
                                await self._notify(frame.event)
                        continue
                    tail = self._output_frames.push(self._output_resampler.flush())
                    tail += self._output_frames.flush()
                    for pcm in tail:
                        if not await self._send_frame(pcm, frame.generation):
                            break
                    # Allow the last frame's media duration to elapse. Firmware
                    # drains its own queue on normal stop; only abort discards it.
                    await asyncio.sleep(max(0.0, self._next_send_at - asyncio.get_running_loop().time()))
                    async with self._send_lock:
                        if frame.generation == self.session.generation:
                            await self._notify(frame.event)
                    continue
                for pcm in self._output_frames.push(self._output_resampler.convert(frame.pcm)):
                    if not await self._send_frame(pcm, frame.generation):
                        break
        except asyncio.CancelledError:
            return
        except Exception as error:
            await self._fail(error)
