"""Run in the Pico runtime image: python -m unittest ... (no provider calls)."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from core.handle.helloHandle import handleHelloMessage

class DuplexHelloTest(unittest.IsolatedAsyncioTestCase):
    async def test_capture_rate_does_not_replace_playback_rate(self):
        conn=SimpleNamespace(
            logger=MagicMock(), websocket=SimpleNamespace(send=AsyncMock()),
            full_duplex_enabled=True, sample_rate=24000,
            config={'full_duplex':{}},
            welcome_msg={'type':'hello','audio_params':{'format':'opus','sample_rate':24000,'channels':1,'frame_duration':60}},
        )
        await handleHelloMessage(conn, {'audio_params':{'format':'opus','sample_rate':16000,'channels':1,'frame_duration':60}})
        reply=json.loads(conn.websocket.send.call_args.args[0])
        self.assertEqual(reply['audio_params']['sample_rate'],24000)
        self.assertEqual(reply['audio_params']['frame_duration'],60)

    async def test_incompatible_capture_is_rejected_before_audio(self):
        conn=SimpleNamespace(
            logger=MagicMock(), websocket=SimpleNamespace(send=AsyncMock(),close=AsyncMock()),
            full_duplex_enabled=True,sample_rate=24000, config={'full_duplex':{}},
            welcome_msg={'type':'hello','audio_params':{'sample_rate':24000}},
        )
        await handleHelloMessage(conn, {'audio_params':{'format':'opus','sample_rate':16000,'channels':2,'frame_duration':60}})
        conn.websocket.close.assert_awaited_once()
        conn.websocket.send.assert_not_awaited()

if __name__=='__main__': unittest.main()
