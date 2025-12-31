import pytest
import numpy as np
from audio_server.audio_capture import AudioCapture

class DummyConfig:
    SAMPLE_RATE = 48000
    BLOCKSIZE = 128
    USE_MEMORYVIEW = True
    AUDIO_THREAD_PRIORITY = False
    CPU_AFFINITY = None
    VU_UPDATE_INTERVAL = 100
    DEBUG = True

# Patch config for test
import audio_server.audio_capture as ac_mod
ac_mod.config = DummyConfig

def test_audio_capture_start_stop(monkeypatch):
    # Mock sounddevice InputStream
    class DummyStream:
        def __init__(self, *a, **kw): pass
        def start(self): pass
        def stop(self): pass
        def close(self): pass
    monkeypatch.setattr(ac_mod, 'sd', type('sd', (), {'InputStream': DummyStream, 'query_devices': lambda: [{'max_input_channels': 8, 'name': 'Dummy'}], 'SAMPLE_RATE': 48000}))
    cap = AudioCapture()
    channels = cap.start_capture(device_id=0)
    assert channels == 8
    assert cap.running
    cap.stop_capture()
    assert not cap.running

def test_audio_callback_and_vu(monkeypatch):
    # Mock stream and config
    monkeypatch.setattr(ac_mod, 'sd', type('sd', (), {'InputStream': lambda *a, **kw: None, 'query_devices': lambda: [{'max_input_channels': 2, 'name': 'Dummy'}]}))
    cap = AudioCapture()
    cap.actual_channels = 2
    vu_levels = {}
    def vu_callback(levels):
        vu_levels.update(levels)
    cap.register_vu_callback(vu_callback)
    # Simula bloque de audio
    audio = np.ones((128, 2), dtype=np.float32)
    cap.calculate_vu_levels(audio)
    assert 0 in vu_levels and 1 in vu_levels
    assert 'rms' in vu_levels[0]

def test_register_and_unregister_callback():
    cap = AudioCapture()
    called = {'count': 0}
    def cb(audio):
        called['count'] += 1
    cap.register_callback(cb, name="testcb")
    assert len(cap.callbacks) == 1
    cap._audio_callback(np.ones((128, 2), dtype=np.float32), 128, None, None)
    assert called['count'] == 1
    cap.unregister_callback(cb)
    assert len(cap.callbacks) == 0
