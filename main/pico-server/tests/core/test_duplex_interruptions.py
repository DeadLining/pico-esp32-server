import asyncio
import base64
import json
import pytest
from core.realtime.full_duplex_session import FullDuplexSession, DeviceFullDuplexBridge, PassthroughAec

@pytest.fixture(autouse=True)
def real_sleep(monkeypatch):
    monkeypatch.setattr(asyncio, "sleep", asyncio.tasks.sleep)

class WS:
    async def send(self, data): pass
    async def close(self): pass

class Codec:
    sample_rate = 24000
    def encode(self, pcm): return pcm
    def decode(self, pcm, samples): return pcm

def delta(r, pcm):
    return dict(type='response.output_audio.delta', response_id=r, delta=base64.b64encode(pcm).decode())

@pytest.mark.parametrize('event', [
    {'type':'conversation.item.input_audio_transcription.completed','semantic_decision':'yield'},
    {'type':'conversation.item.input_audio_transcription.completed','semantic_decision':'wait'},
    {'type':'output_audio_buffer.cleared'},
    {'type':'response.done','response':{'id':'r1','status':'cancelled'}},
])
def test_remote_interrupt_invalidates_buffered_reply(event):
    async def run():
        s = FullDuplexSession('ws://test', aec=PassthroughAec())
        await s.handle_event({'type':'response.created','response':{'id':'r1'}})
        await s.handle_event(delta('r1', b'\x01\x00'*1440))
        g = s.generation
        await s.handle_event(event)
        assert s.generation > g
        assert s.audio_queue.empty()
        await s.handle_event(delta('r1', b'\x01\x00'*1440))
        assert s.audio_queue.empty()
    asyncio.run(run())

def test_cancel_during_large_delta_stops_remaining_packets():
    async def run():
        s = FullDuplexSession('ws://test', aec=PassthroughAec())
        s.websocket = WS()
        packets = []
        async def send(p):
            packets.append(p)
            if len(packets) == 1:
                await s.cancel_response()
        b = DeviceFullDuplexBridge(s, Codec(), send_opus=send)
        await s.handle_event({'type':'response.created','response':{'id':'r1'}})
        await s.handle_event(delta('r1', b'\x01\x00'*1440*6))
        t = asyncio.create_task(b._playback_loop())
        await asyncio.sleep(.4)
        t.cancel()
        await asyncio.gather(t, return_exceptions=True)
        assert len(packets) == 1
    asyncio.run(run())

def test_normal_finish_orders_start_audio_tail_stop():
    async def run():
        s = FullDuplexSession('ws://test', aec=PassthroughAec())
        events = []
        async def send(p): events.append(('audio', p))
        async def on_event(e): events.append((e['type'], e))
        b = DeviceFullDuplexBridge(s, Codec(), send_opus=send, on_event=on_event)
        await s.handle_event({'type':'response.created','response':{'id':'r1'}})
        await s.handle_event(delta('r1', b'\x01\x00'*1500))
        await s.handle_event({'type':'response.output_audio.done','response_id':'r1'})
        await s.handle_event({'type':'response.done','response':{'id':'r1','status':'completed'}})
        t = asyncio.create_task(b._playback_loop())
        await asyncio.sleep(.25)
        t.cancel()
        await asyncio.gather(t, return_exceptions=True)
        assert [e[0] for e in events] == ['response.created','audio','audio','response.output_audio.done']
        assert events[2][1][:120] == b'\x01\x00'*60
        assert events[2][1][120:] == bytes(2760)
    asyncio.run(run())

@pytest.mark.parametrize('source,target,n', [(16000,24000,960),(24000,16000,1440),(16000,24000,1)])
def test_resampler_flush_preserves_duration(source,target,n):
    from core.realtime.full_duplex_session import PcmResampler
    r=PcmResampler(source,target)
    out=r.convert(b'\x01\x00'*n)+r.flush()
    assert len(out)//2 == (n*target+source-1)//source

def test_stale_cancel_does_not_kill_replacement():
    async def run():
        s=FullDuplexSession('ws://test')
        for rid in ('old','new'):
            await s.handle_event({'type':'response.created','response':{'id':rid}})
        g=s.generation
        await s.handle_event({'type':'response.done','response':{'id':'old','status':'cancelled'}})
        await s.handle_event(delta('old',bytes(2880)))
        assert s.generation==g and s.playback_response_id=='new'
        assert s.audio_queue.qsize()==1
    asyncio.run(run())

def test_semantic_interrupt_after_generation_done_clears_playback():
    async def run():
        s=FullDuplexSession('ws://test')
        await s.handle_event({'type':'response.created','response':{'id':'r'}})
        await s.handle_event(delta('r',bytes(2880)))
        await s.handle_event({'type':'response.done','response':{'id':'r','status':'completed'}})
        assert s.active_response_id is None
        await s.handle_event({'type':'conversation.item.input_audio_transcription.completed','semantic_decision':'yield'})
        assert s.audio_queue.empty() and s.playback_response_id is None
    asyncio.run(run())

def test_overflow_fails_instead_of_silently_dropping_audio():
    async def run():
        s=FullDuplexSession('ws://test',max_audio_frames=2)
        await s.handle_event({'type':'response.created','response':{'id':'r'}})
        await s.handle_event(delta('r',bytes(2880)))
        with pytest.raises(BufferError):
            await s.handle_event(delta('r',bytes(2880)))
        assert s.audio_queue.empty() and s.active_response_id is None
    asyncio.run(run())

class IncomingWS(WS):
    def __init__(self): self.incoming=asyncio.Queue(); self.closed=False
    async def recv(self): return json.dumps(await self.incoming.get())
    async def close(self): self.closed=True

def test_live_receive_cancels_large_playback_then_replaces_without_old_tail():
    async def run():
        ws=IncomingWS()
        s=FullDuplexSession('ws://test',aec=PassthroughAec(),websocket_factory=lambda *a,**k:ws)
        emitted=[]; first=asyncio.Event(); finished=asyncio.Event()
        async def send(p):
            emitted.append(('audio',p)); first.set()
        async def notify(e):
            emitted.append((e['type'],None))
            if e['type']=='response.output_audio.done': finished.set()
        b=DeviceFullDuplexBridge(s,Codec(),send_opus=send,on_event=notify)
        await b.start()
        await ws.incoming.put({'type':'response.created','response':{'id':'old'}})
        await ws.incoming.put(delta('old',b'\x01\x00'*1440*8))
        await asyncio.wait_for(first.wait(),1)
        await ws.incoming.put({'type':'conversation.item.input_audio_transcription.completed','semantic_decision':'yield'})
        await ws.incoming.put({'type':'response.done','response':{'id':'old','status':'cancelled'}})
        await ws.incoming.put(delta('old',b'\x01\x00'*1440))
        await ws.incoming.put({'type':'response.created','response':{'id':'new'}})
        await ws.incoming.put(delta('new',b'\x02\x00'*1440))
        await ws.incoming.put({'type':'response.done','response':{'id':'new','status':'completed'}})
        try:
            await asyncio.wait_for(finished.wait(),2)
            cut=next(i for i,e in enumerate(emitted) if e[0]=='pico.playback.abort')
            assert all(e[1]!=b'\x01\x00'*1440 for e in emitted[cut:] if e[0]=='audio')
            audio=[e[1] for e in emitted if e[0]=='audio']
            # One optional prebuffer frame may precede receipt of the interrupt.
            assert 1 <= audio.count(b'\x01\x00'*1440) <= 2
            assert audio[-1] == b'\x02\x00'*1440
            assert audio.count(b'\x02\x00'*1440) == 1
        finally: await b.stop()
    asyncio.run(run())

def test_upstream_disconnect_aborts_device_and_reports_fatal():
    async def run():
        class BrokenWS(WS):
            async def recv(self): raise ConnectionError('disconnected')
        s=FullDuplexSession('ws://test',websocket_factory=lambda *a,**k:BrokenWS())
        events=[]; failed=asyncio.Event()
        async def notify(e):
            events.append(e['type'])
            if e['type']=='pico.bridge.failed': failed.set()
        async def send(p): pass
        b=DeviceFullDuplexBridge(s,Codec(),send_opus=send,on_event=notify)
        await b.start()
        await asyncio.wait_for(failed.wait(),1)
        await b.stop()
        assert events==['pico.playback.abort','pico.bridge.failed']
    asyncio.run(run())
