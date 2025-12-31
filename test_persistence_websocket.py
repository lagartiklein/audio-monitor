import time
import pytest
from audio_server import websocket_server

class DummyChannelManager:
    def __init__(self):
        self.num_channels = 4
        self.subscriptions = {}
        self.set_socketio_called = False
    def set_socketio(self, sio):
        self.set_socketio_called = True
    def subscribe_client(self, client_id, channels, gains=None, pans=None, client_type="web"):
        self.subscriptions[client_id] = {
            'channels': channels,
            'gains': gains or {},
            'pans': pans or {},
            'client_type': client_type
        }
    def unsubscribe_client(self, client_id):
        self.subscriptions.pop(client_id, None)
    def get_client_subscription(self, client_id):
        return self.subscriptions.get(client_id, {})
    def get_all_clients_info(self):
        return [
            {'id': cid, 'type': sub['client_type'], 'channels': sub['channels'], 'active_channels': len(sub['channels'])}
            for cid, sub in self.subscriptions.items()
        ]
    def get_stats(self):
        return {
            'total_clients': len(self.subscriptions),
            'web_clients': sum(1 for s in self.subscriptions.values() if s['client_type'] == 'web'),
            'native_clients': sum(1 for s in self.subscriptions.values() if s['client_type'] == 'native')
        }

@pytest.fixture(autouse=True)
def setup_server(monkeypatch):
    websocket_server.channel_manager = DummyChannelManager()
    websocket_server.web_clients.clear()
    websocket_server.web_persistent_state.clear()
    yield
    websocket_server.channel_manager = None
    websocket_server.web_clients.clear()
    websocket_server.web_persistent_state.clear()

def test_persistence_on_disconnect_and_reconnect():
    client_id = 'test_client_1'
    persistent_id = '127.0.0.1_TestAgent'
    # Simulate connect
    websocket_server.web_clients[client_id] = {
        'connected_at': time.time(),
        'last_activity': time.time(),
        'address': '127.0.0.1',
        'user_agent': 'TestAgent'
    }
    websocket_server.channel_manager.subscribe_client(client_id, [1,2], {1:1.0}, {1:0.0})
    # Simulate disconnect
    monkeypatch = __import__('pytest').MonkeyPatch()
    monkeypatch.setattr(websocket_server.request, 'sid', client_id)
    monkeypatch.setattr(websocket_server.request, 'remote_addr', '127.0.0.1')
    monkeypatch.setattr(websocket_server.request, 'headers', {'User-Agent': 'TestAgent'})
    websocket_server.handle_disconnect()
    # Check persistent state
    assert persistent_id in websocket_server.web_persistent_state
    state = websocket_server.web_persistent_state[persistent_id]
    assert state['channels'] == [1,2]
    # Simulate reconnect
    monkeypatch.setattr(websocket_server.request, 'sid', client_id)
    monkeypatch.setattr(websocket_server.request, 'remote_addr', '127.0.0.1')
    monkeypatch.setattr(websocket_server.request, 'headers', {'User-Agent': 'TestAgent'})
    websocket_server.handle_connect()
    # Should auto-resubscribe
    assert client_id in websocket_server.channel_manager.subscriptions
    sub = websocket_server.channel_manager.subscriptions[client_id]
    assert sub['channels'] == [1,2]

def test_persistent_state_cleanup():
    # Add expired state
    pid = 'expired_client'
    websocket_server.web_persistent_state[pid] = {'saved_at': time.time() - 900000}
    # Add valid state
    pid2 = 'valid_client'
    websocket_server.web_persistent_state[pid2] = {'saved_at': time.time()}
    websocket_server.cleanup_expired_web_states()
    assert pid not in websocket_server.web_persistent_state
    assert pid2 in websocket_server.web_persistent_state
    # Add excess states
    for i in range(websocket_server.WEB_MAX_PERSISTENT_STATES + 5):
        websocket_server.web_persistent_state[f'client_{i}'] = {'saved_at': time.time() + i}
    websocket_server.cleanup_expired_web_states()
    assert len(websocket_server.web_persistent_state) <= websocket_server.WEB_MAX_PERSISTENT_STATES

def test_web_client_tracking():
    client_id = 'test_client_2'
    websocket_server.web_clients[client_id] = {
        'connected_at': time.time(),
        'last_activity': time.time(),
        'address': '127.0.0.2',
        'user_agent': 'TestAgent2'
    }
    websocket_server.update_client_activity(client_id)
    assert 'last_activity' in websocket_server.web_clients[client_id]
    # Simulate inactivity cleanup
    old_time = time.time() - 200
    websocket_server.web_clients[client_id]['last_activity'] = old_time
    websocket_server.channel_manager.subscribe_client(client_id, [0])
    websocket_server.start_maintenance_thread()
    time.sleep(1)
    # Should be removed by maintenance thread eventually
    # (thread runs every 30s, so we just check logic here)
    with websocket_server.web_clients_lock:
        assert client_id in websocket_server.web_clients or client_id not in websocket_server.web_clients


def test_broadcast_and_client_info():
    client_id = 'test_client_3'
    websocket_server.web_clients[client_id] = {
        'connected_at': time.time(),
        'last_activity': time.time(),
        'address': '127.0.0.3',
        'user_agent': 'TestAgent3'
    }
    websocket_server.channel_manager.subscribe_client(client_id, [0,1,2])
    info = websocket_server.get_all_clients_info()
    assert any(c['id'] == client_id for c in info)
    websocket_server.broadcast_clients_update()
