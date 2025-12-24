# native_protocol.py - HEADER 20 BYTES CON ENTRELAZADO CORRECTO

import struct
import time
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Optional
import json
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import config

@dataclass
class NativePacket:
    """Paquete binario optimizado para APK"""
    magic: int = config.NATIVE_MAGIC_NUMBER
    version: int = config.NATIVE_PROTOCOL_VERSION
    msg_type: int = 0
    flags: int = 0
    timestamp: int = 0
    sequence: int = 0
    payload_length: int = 0
    payload: bytes = b''
    
    HEADER_FORMAT = '!IHBBIII'  # 20 bytes
    HEADER_SIZE = 20
    
    def encode_header(self) -> bytes:
        """Codificar header de 20 bytes CON payload_length"""
        return struct.pack(
            self.HEADER_FORMAT,
            self.magic,
            self.version,
            self.msg_type,
            self.flags,
            self.timestamp,
            self.sequence,
            self.payload_length
        )
    
    def encode_full(self) -> bytes:
        """Codificar paquete completo: header + payload"""
        header = self.encode_header()
        return header + self.payload
    
    @classmethod
    def decode_header(cls, data: bytes) -> tuple:
        """Decodificar header de 20 bytes"""
        if len(data) < cls.HEADER_SIZE:
            raise ValueError(f"Header muy pequeño: {len(data)} bytes")
        
        magic, version, msg_type, flags, timestamp, sequence, payload_length = struct.unpack(
            cls.HEADER_FORMAT, data[:cls.HEADER_SIZE]
        )
        
        if magic != config.NATIVE_MAGIC_NUMBER:
            raise ValueError(f"Magic number inválido: {hex(magic)}")
        
        return magic, version, msg_type, flags, timestamp, sequence, payload_length

class NativeAudioEncoder:
    """Codificador SIMPLIFICADO - solo extrae y transmite"""
    
    # Tipos de mensaje
    MSG_TYPE_AUDIO = 0x01
    MSG_TYPE_CONTROL = 0x02
    MSG_TYPE_PING = 0x03
    MSG_TYPE_CONFIG = 0x04
    
    def __init__(self, sample_rate: int = 48000):
        self.sample_rate = sample_rate
        self.sequence_counter = 0
        self.start_time = time.time()
        self.master_volume = 0.8  # Headroom del 20%
    
    def float32_to_int16(self, audio_data: np.ndarray) -> np.ndarray:
        """Convertir float32 a int16 con clipping seguro"""
        # Clipping duro a [-1, 1] por seguridad
        audio_clipped = np.clip(audio_data, -1.0, 1.0)
        # Aplicar volumen maestro
        audio_clipped = audio_clipped * self.master_volume
        # Convertir
        audio_int16 = (audio_clipped * 32767).astype(np.int16)
        return audio_int16
    
    def create_audio_packet(self, 
                           audio_data: np.ndarray, 
                           active_channels: List[int],
                           timestamp: int) -> bytes:
        """
        ✅ VERSIÓN SIMPLE: Extraer, convertir, entrelazar, enviar
        SIN procesamiento de ganancias
        """
        if not active_channels or audio_data.size == 0:
            return b''
        
        # 1. Extraer canales activos
        selected_data = audio_data[:, active_channels]
        
        # 2. Convertir a int16 (clipping seguro incluido)
        audio_int16 = self.float32_to_int16(selected_data)
        
        # 3. Entrelazar: sample0[ch0,ch1,ch2], sample1[ch0,ch1,ch2], ...
        flat_audio = audio_int16.flatten('C')
        
        # 4. Crear máscara de canales
        channel_mask = 0
        for ch in active_channels:
            if 0 <= ch < 32:
                channel_mask |= (1 << ch)
        
        # 5. Payload = máscara (4 bytes) + audio
        mask_bytes = struct.pack('!I', channel_mask)
        audio_bytes = flat_audio.tobytes()
        payload = mask_bytes + audio_bytes
        
        # 6. Header de 20 bytes
        header = struct.pack(
            '!IHBBIII',
            config.NATIVE_MAGIC_NUMBER,
            config.NATIVE_PROTOCOL_VERSION,
            self.MSG_TYPE_AUDIO,
            0,  # flags
            timestamp,
            self.sequence_counter,
            len(payload)
        )
        
        self.sequence_counter += 1
        return header + payload
    
    def create_control_packet(self, message_json: str) -> bytes:
        """Crear paquete de CONTROL con header de 20 bytes"""
        message_bytes = message_json.encode('utf-8')
        
        header = struct.pack(
            '!IHBBIII',
            config.NATIVE_MAGIC_NUMBER,
            config.NATIVE_PROTOCOL_VERSION,
            self.MSG_TYPE_CONTROL,
            0,
            int((time.time() - self.start_time) * 1000) % (2**31),
            0,
            len(message_bytes)
        )
        
        return header + message_bytes
    
    def create_config_packet(self, config_dict: Dict) -> bytes:
        """Crear paquete de CONFIG con header de 20 bytes"""
        config_json = json.dumps(config_dict, separators=(',', ':'))
        config_bytes = config_json.encode('utf-8')
        
        header = struct.pack(
            '!IHBBIII',
            config.NATIVE_MAGIC_NUMBER,
            config.NATIVE_PROTOCOL_VERSION,
            self.MSG_TYPE_CONFIG,
            0,
            int((time.time() - self.start_time) * 1000) % (2**31),
            0,
            len(config_bytes)
        )
        
        return header + config_bytes
    
    def create_ping_packet(self, counter: int = 0) -> bytes:
        """Crear paquete de PING con header de 20 bytes"""
        ping_data = struct.pack('!Q', counter)
        
        header = struct.pack(
            '!IHBBIII',
            config.NATIVE_MAGIC_NUMBER,
            config.NATIVE_PROTOCOL_VERSION,
            self.MSG_TYPE_PING,
            0,
            int((time.time() - self.start_time) * 1000) % (2**31),
            0,
            len(ping_data)
        )
        
        return header + ping_data

class NativeControlProtocol:
    """Protocolo de control JSON para APK"""
    
    @staticmethod
    def encode_subscribe(channels: List[int]) -> str:  # ✅ SIN gains
        """Codificar mensaje de suscripción"""
        return json.dumps({
            'type': 'subscribe',
            'channels': channels,
            'timestamp': int(time.time() * 1000)
        })
    
    @staticmethod
    def encode_heartbeat(client_id: str) -> str:
        """Codificar heartbeat"""
        return json.dumps({
            'type': 'heartbeat',
            'client_id': client_id,
            'timestamp': int(time.time() * 1000)
        })
    
    @staticmethod
    def encode_error(error_msg: str) -> str:
        """Codificar error"""
        return json.dumps({
            'type': 'error',
            'message': error_msg,
            'timestamp': int(time.time() * 1000)
        })
    
    @staticmethod
    def decode_message(data: str) -> Dict:
        """Decodificar mensaje JSON"""
        return json.loads(data)

class NativeDecoder:
    """Decodificador de paquetes nativos"""
    
    @staticmethod
    def decode_audio_packet(header_tuple: tuple, payload: bytes) -> Dict:
        """Decodifica paquete de audio"""
        magic, version, msg_type, flags, timestamp, sequence, payload_length = header_tuple
        
        if len(payload) < 4:
            raise ValueError("Payload de audio muy pequeño")
        
        # Leer máscara de canales
        channel_mask = struct.unpack('!I', payload[:4])[0]
        audio_data = payload[4:]
        
        # Calcular número de canales activos
        active_channels = bin(channel_mask).count('1')
        
        # Decodificar audio int16
        if len(audio_data) % 2 != 0:
            raise ValueError("Audio data size inválido")
        
        audio_samples = np.frombuffer(audio_data, dtype=np.int16)
        
        return {
            'timestamp': timestamp,
            'sequence': sequence,
            'channel_mask': channel_mask,
            'active_channels': active_channels,
            'audio_data': audio_samples,
            'sample_count': len(audio_samples) // active_channels if active_channels > 0 else 0
        }
    
    @staticmethod
    def decode_control_packet(header_tuple: tuple, payload: bytes) -> Dict:
        """Decodifica paquete de control"""
        message = payload.decode('utf-8')
        return json.loads(message)
    
    @staticmethod
    def decode_ping_packet(header_tuple: tuple, payload: bytes) -> Dict:
        """Decodifica paquete de ping"""
        if len(payload) >= 8:
            counter = struct.unpack('!Q', payload[:8])[0]
        else:
            counter = 0
        
        return {
            'type': 'ping',
            'counter': counter,
            'timestamp': header_tuple[4]
        }