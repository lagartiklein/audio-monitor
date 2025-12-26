import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import config

class ChannelManager:
    def __init__(self, num_channels):
        self.num_channels = num_channels
        self.subscriptions = {}
        print(f"[ChannelManager] Inicializado con {num_channels} canales disponibles")
    
    def subscribe_client(self, client_id, channels, gains=None):
        if gains is None: 
            gains = {ch: 1.0 for ch in channels}
        
        self.subscriptions[client_id] = {'channels': channels, 'gains': gains}
        print(f"[ChannelManager] 📡 Cliente {client_id[:8]} suscrito a {len(channels)} canales: {channels}")
        if config.VERBOSE: 
            print(f"[ChannelManager] Cliente {client_id[:8]} suscrito a {len(channels)} canales")
    
    def unsubscribe_client(self, client_id):
        if client_id in self.subscriptions:
            del self.subscriptions[client_id]
            print(f"[ChannelManager] 📡 Cliente {client_id[:8]} desuscrito")
            if config.VERBOSE: 
                print(f"[ChannelManager] Cliente {client_id[:8]} desuscrito")