# native_protocol.py - Protocolo binario optimizado para APK

import struct
import time
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Optional
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import config

@dataclass
class NativePacket:
    """Paquete binario optimizado para APK"""
    magic: int = config.NATIVE_MAGIC_NUMBER
    version: int = config.NATIVE_PROTOCOL_VERSION
    channel_mask: int = 0          # 8 bits = 8 canales máximo
    flags: int = 0                 # Bits: 0=compressed, 1=stereo, 2=end_stream
    timestamp: int = 0             # ms desde inicio
    sequence: int = 0              # Número de secuencia
    audio_data: bytes = b''        # PCM 16-bit
    
    # Constantes
    HEADER_FORMAT = '!IHBBII'     # 12 bytes: magic(4), version(2), mask(1), flags(1), timestamp(4), seq(4)
    HEADER_SIZE = 12
    
    def encode_header(self) -> bytes:
        """Codificar header de 12 bytes"""
        return struct.pack(
            self.HEADER_FORMAT,
            self.magic,
            self.version,
            self.channel_mask,
            self.flags,
            self.timestamp,
            self.sequence
        )
    
    @classmethod
    def decode_header(cls, data: bytes) -> 'NativePacket':
        """Decodificar header de 12 bytes"""
        if len(data) < cls.HEADER_SIZE:
            raise ValueError(f"Header muy pequeño: {len(data)} bytes")
        
        magic, version, channel_mask, flags, timestamp, sequence = struct.unpack(
            cls.HEADER_FORMAT, data[:cls.HEADER_SIZE]
        )
        
        if magic != config.NATIVE_MAGIC_NUMBER:
            raise ValueError(f"Magic number inválido: {hex(magic)}")
        
        packet = cls()
        packet.magic = magic
        packet.version = version
        packet.channel_mask = channel_mask
        packet.flags = flags
        packet.timestamp = timestamp
        packet.sequence = sequence
        packet.audio_data = data[cls.HEADER_SIZE:]
        
        return packet
    
    def encode_full(self) -> bytes:
        """Codificar paquete completo"""
        return self.encode_header() + self.audio_data
    
    def get_size(self) -> int:
        """Tamaño total del paquete"""
        return self.HEADER_SIZE + len(self.audio_data)
    
    def is_valid(self) -> bool:
        """Verificar si el paquete es válido"""
        return (self.magic == config.NATIVE_MAGIC_NUMBER and
                self.version == config.NATIVE_PROTOCOL_VERSION and
                len(self.audio_data) > 0)
    
    def set_channels(self, channels: List[int]):
        """Establecer máscara de bits para canales activos"""
        mask = 0
        for ch in channels:
            if 0 <= ch < 8:  # Máximo 8 canales por eficiencia
                mask |= (1 << ch)
        self.channel_mask = mask
    
    def get_channels(self) -> List[int]:
        """Obtener lista de canales desde máscara"""
        channels = []
        mask = self.channel_mask
        for i in range(8):
            if mask & (1 << i):
                channels.append(i)
        return channels

class NativeAudioEncoder:
    """Codificador de audio a formato APK optimizado"""
    
    def __init__(self, sample_rate: int = 48000, channels: int = 8):
        self.sample_rate = sample_rate
        self.channels = channels
        self.sequence_counter = 0
        self.start_time = time.time()
        
    def float32_to_int16(self, audio_data: np.ndarray) -> np.ndarray:
        """Convertir float32 [-1, 1] a int16 [-32768, 32767]"""
        # Clip y escala
        audio_clipped = np.clip(audio_data, -1.0, 1.0)
        audio_int16 = (audio_clipped * 32767).astype(np.int16)
        return audio_int16
    
    def create_packet(self, 
                     audio_data: np.ndarray, 
                     active_channels: List[int],
                     timestamp: Optional[int] = None) -> NativePacket:
        """
        Crear paquete nativo desde audio float32
        audio_data shape: (samples, channels)
        """
        if timestamp is None:
            timestamp = int((time.time() - self.start_time) * 1000)
        
        # Seleccionar solo canales activos
        if len(active_channels) > 0:
            # Reordenar canales según máscara
            selected_data = audio_data[:, active_channels]
        else:
            selected_data = audio_data
        
        # Convertir a int16
        audio_int16 = self.float32_to_int16(selected_data)
        
        # Aplanar: (samples, channels) -> (samples*channels)
        flat_audio = audio_int16.flatten('C')
        
        # Crear paquete
        packet = NativePacket()
        packet.set_channels(active_channels)
        packet.timestamp = timestamp
        packet.sequence = self.sequence_counter
        packet.audio_data = flat_audio.tobytes()
        
        self.sequence_counter += 1
        return packet
    
    def calculate_latency(self, packet: NativePacket) -> float:
        """Calcular latencia actual en ms"""
        current_time = int((time.time() - self.start_time) * 1000)
        return current_time - packet.timestamp

class NativeControlProtocol:
    """Protocolo de control JSON para APK"""
    
    @staticmethod
    def encode_subscribe(channels: List[int], gains: Dict[int, float]) -> str:
        """Codificar mensaje de suscripción"""
        import json
        return json.dumps({
            'type': 'subscribe',
            'channels': channels,
            'gains': gains,
            'timestamp': int(time.time() * 1000)
        })
    
    @staticmethod
    def encode_heartbeat(client_id: str) -> str:
        """Codificar heartbeat"""
        import json
        return json.dumps({
            'type': 'heartbeat',
            'client_id': client_id,
            'timestamp': int(time.time() * 1000)
        })
    
    @staticmethod
    def encode_error(error_msg: str) -> str:
        """Codificar error"""
        import json
        return json.dumps({
            'type': 'error',
            'message': error_msg,
            'timestamp': int(time.time() * 1000)
        })
    
    @staticmethod
    def decode_message(data: str) -> Dict:
        """Decodificar mensaje JSON"""
        import json
        return json.loads(data)