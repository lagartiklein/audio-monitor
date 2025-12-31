import pytest
from audio_server import websocket_server
from flask import Request

# Test básico de conexión/desconexión

def test_websocket_connect_disconnect(monkeypatch):
    # Simula un request de Flask
    class DummyRequest:
        sid = 'dummy_client_id'
        remote_addr = '127.0.0.1'
        headers = {'User-Agent': 'pytest-agent'}
    
    monkeypatch.setattr(websocket_server, 'request', DummyRequest)
    # Simula channel_manager
    class DummyManager:
        num_channels = 2
        def set_socketio(self, sio):
            pass
    websocket_server.channel_manager = DummyManager()
    
    # Conexión
    websocket_server.handle_connect()
    assert 'dummy_client_id' in websocket_server.web_clients
    # Desconexión
    websocket_server.handle_disconnect()
    assert 'dummy_client_id' not in websocket_server.web_clients
