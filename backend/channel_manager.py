import numpy as np
import struct
import config

class ChannelManager:
    def __init__(self, num_channels):
        self.num_channels = num_channels
        # Dict: client_id -> {channels: [list], gains: {ch: gain}}
        self.subscriptions = {}
        
    def subscribe_client(self, client_id, channels, gains=None):
        """Cliente se suscribe a canales específicos"""
        if gains is None:
            gains = {ch: 1.0 for ch in channels}
        
        self.subscriptions[client_id] = {
            'channels': channels,
            'gains': gains
        }
        
        if config.VERBOSE:
            print(f"[+] Cliente {client_id} suscrito a canales: {channels}")
    
    def unsubscribe_client(self, client_id):
        """Cliente se desuscribe"""
        if client_id in self.subscriptions:
            del self.subscriptions[client_id]
            if config.VERBOSE:
                print(f"[-] Cliente {client_id} desuscrito")
    
    def update_gain(self, client_id, channel, gain):
        """Actualiza ganancia de un canal para un cliente"""
        if client_id in self.subscriptions:
            self.subscriptions[client_id]['gains'][channel] = gain
    
    def process_audio(self, audio_data):
        """
        Procesa audio y devuelve dict por cliente
        audio_data: numpy array (frames, channels) en float32
        """
        processed = {}
        
        for client_id, sub in self.subscriptions.items():
            client_audio = []
            
            for channel in sub['channels']:
                if channel < self.num_channels:
                    # Extraer canal específico
                    channel_data = audio_data[:, channel]
                    
                    # Aplicar ganancia (vectorizado con NumPy)
                    gain = sub['gains'].get(channel, 1.0)
                    channel_data = channel_data * gain
                    
                    # Convertir float32 [-1, 1] a int16 [-32768, 32767]
                    channel_data = np.clip(channel_data * 32767, -32768, 32767)
                    channel_data = channel_data.astype(np.int16)
                    
                    # Empaquetar: [channel_id (1 byte)][audio_data]
                    binary_data = struct.pack('B', channel) + channel_data.tobytes()
                    client_audio.append(binary_data)
            
            processed[client_id] = client_audio
        
        return processed
    
    def get_active_channels(self):
        """Devuelve set de todos los canales activos"""
        active = set()
        for sub in self.subscriptions.values():
            active.update(sub['channels'])
        return active