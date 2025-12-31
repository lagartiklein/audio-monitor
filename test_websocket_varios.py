import pytest
from audio_server import websocket_server

# Utilidad para simular request
class DummyRequest:
    sid = 'dummy_client_id'
    remote_addr = '127.0.0.1'
    headers = {'User-Agent': 'pytest-agent'}

def setup_manager():
    class DummyManager:
        num_channels = 2
        subscriptions = {}
        def set_socketio(self, sio):
            pass
        def subscribe_client(self, client_id, channels, gains=None, pans=None, client_type="web"):
            self.subscriptions[client_id] = {
                'channels': channels,
                'gains': gains or {},
                'pans': pans or {},
                'client_type': client_type
            }
        def unsubscribe_client(self, client_id):
            self.subscriptions.pop(client_id, None)
        def update_client_mix(self, *args, **kwargs):
            return True
    return DummyManager()

# Test conexión y desconexión

def test_connect_disconnect(monkeypatch):
    monkeypatch.setattr(websocket_server, 'request', DummyRequest)
    websocket_server.channel_manager = setup_manager()
    monkeypatch.setattr(websocket_server, 'emit', lambda *a, **kw: None)
    monkeypatch.setattr(websocket_server, 'disconnect', lambda *a, **kw: None)
    websocket_server.handle_connect()
    assert 'dummy_client_id' in websocket_server.web_clients
    websocket_server.handle_disconnect()
    assert 'dummy_client_id' not in websocket_server.web_clients

# Test suscripción

def test_subscribe(monkeypatch):
    monkeypatch.setattr(websocket_server, 'request', DummyRequest)
    websocket_server.channel_manager = setup_manager()
    monkeypatch.setattr(websocket_server, 'emit', lambda *a, **kw: None)
    websocket_server.handle_connect()
    data = {'channels': [0,1], 'gains': {'0': 1.0}, 'pans': {'0': 0.0}}
    websocket_server.handle_subscribe(data)
    subs = websocket_server.channel_manager.subscriptions['dummy_client_id']
    assert subs['channels'] == [0,1]
    assert subs['gains'][0] == 1.0
    assert subs['pans'][0] == 0.0
    websocket_server.handle_disconnect()

# Test error en subscribe sin channel_manager

def test_subscribe_error(monkeypatch):
    monkeypatch.setattr(websocket_server, 'request', DummyRequest)
    websocket_server.channel_manager = None
    monkeypatch.setattr(websocket_server, 'emit', lambda *a, **kw: None)
    websocket_server.handle_connect()
    data = {'channels': [0,1]}
    websocket_server.handle_subscribe(data)
    websocket_server.handle_disconnect()

# Test actualización de mezcla

def test_update_client_mix(monkeypatch):
    monkeypatch.setattr(websocket_server, 'request', DummyRequest)
    websocket_server.channel_manager = setup_manager()
    monkeypatch.setattr(websocket_server, 'emit', lambda *a, **kw: None)
    websocket_server.handle_connect()
    data = {'target_client_id': 'dummy_client_id', 'channels': [0], 'gains': {0: 1.0}, 'pans': {0: 0.0}, 'mutes': {}, 'solos': [], 'pre_listen': None, 'master_gain': 1.0}
    websocket_server.handle_update_client_mix(data)
    websocket_server.handle_disconnect()

# Test obtener lista de clientes

def test_get_clients(monkeypatch):
    monkeypatch.setattr(websocket_server, 'request', DummyRequest)
    websocket_server.channel_manager = setup_manager()
    monkeypatch.setattr(websocket_server, 'emit', lambda *a, **kw: None)
    websocket_server.handle_connect()
    websocket_server.handle_get_clients()
    websocket_server.handle_disconnect()
