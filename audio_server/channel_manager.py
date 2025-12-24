"""
Channel Manager - Gestión de suscripciones para servidor dual
"""

import numpy as np
import struct
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
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
            print(f"[+] Cliente {client_id[:8]}... suscrito a {len(channels)} canales")
    
    def unsubscribe_client(self, client_id):
        """Cliente se desuscribe"""
        if client_id in self.subscriptions:
            del self.subscriptions[client_id]
            
            if config.VERBOSE:
                print(f"[-] Cliente {client_id[:8]}... desuscrito")
    
    def update_gain(self, client_id, channel, gain):
        """Actualiza ganancia de un canal para un cliente"""
        if client_id in self.subscriptions:
            # Limitar ganancia a rango seguro
            gain = max(0.0, min(gain, 4.0))  # 0 a +12dB
            self.subscriptions[client_id]['gains'][channel] = gain
    
    def get_audio_for_client(self, client_id, audio_data):
        """
        Procesa audio para un cliente específico
        Retorna: lista de paquetes binarios por canal
        """
        if client_id not in self.subscriptions:
            return []
        
        sub = self.subscriptions[client_id]
        client_audio = []
        
        for channel in sub['channels']:
            if channel >= self.num_channels:
                continue
            
            # Extraer canal específico
            channel_data = audio_data[:, channel].copy()
            
            # Aplicar ganancia
            gain = sub['gains'].get(channel, 1.0)
            if gain != 1.0:
                channel_data *= gain
                
                # Soft clipping para evitar distorsión
                channel_data = np.clip(channel_data, -1.0, 1.0)
            
            # Formato binario: [channel_id (uint32)][float32 array]
            binary_data = struct.pack('I', channel) + channel_data.astype(np.float32).tobytes()
            client_audio.append(binary_data)
        
        return client_audio
    
    def get_active_channels(self):
        """Devuelve set de todos los canales activos"""
        active = set()
        for sub in self.subscriptions.values():
            active.update(sub['channels'])
        return active
    
    def get_client_count(self):
        """Retorna número de clientes conectados"""
        return len(self.subscriptions)
    
    def get_total_channel_count(self):
        """Retorna total de canales activos entre todos los clientes"""
        total = 0
        for sub in self.subscriptions.values():
            total += len(sub['channels'])
        return total
    
    def get_subscribed_channels(self, client_id):
        """Obtiene canales suscritos por cliente"""
        if client_id in self.subscriptions:
            return self.subscriptions[client_id]['channels']
        return []
    
    def get_channel_gains(self, client_id):
        """Obtiene ganancias por canal para un cliente"""
        if client_id in self.subscriptions:
            return self.subscriptions[client_id]['gains']
        return {}