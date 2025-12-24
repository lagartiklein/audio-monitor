# native_protocol.py - ✅ VERSIÓN CORREGIDA CON SAMPLE RATE DINÁMICO
# Optimizado para máxima calidad de audio

import struct
import time
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
import json
import sys
import os
import logging

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import config

logger = logging.getLogger(__name__)

@dataclass
class NativePacket:
    """Paquete binario optimizado para APK V2.1"""
    magic: int = config.NATIVE_MAGIC_NUMBER
    version: int = config.NATIVE_PROTOCOL_VERSION
    msg_type: int = 0
    flags: int = 0
    timestamp: int = 0
    sequence: int = 0
    payload_length: int = 0
    payload: bytes = b''
    
    # ✅ HEADER DE 20 BYTES (V2.1)
    HEADER_FORMAT = '!IHBBIII'  # magic(4) + version(2) + type(1) + flags(1) + timestamp(4) + sequence(4) + length(4)
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
    """✅ Codificador OPTIMIZADO con sample rate DINÁMICO"""
    
    # Tipos de mensaje
    MSG_TYPE_AUDIO = 0x01
    MSG_TYPE_CONTROL = 0x02
    MSG_TYPE_PING = 0x03
    MSG_TYPE_CONFIG = 0x04
    
    def __init__(self, sample_rate: int = None):
        """
        ✅ Inicializa encoder con sample rate DINÁMICO
        
        Args:
            sample_rate: Si es None, usa el de config.py
                        Si se especifica, usa ese valor
        """
        # ✅ USAR EL SAMPLE RATE DE CONFIG POR DEFECTO
        if sample_rate is None:
            self.sample_rate = config.SAMPLE_RATE
        else:
            self.sample_rate = sample_rate
        
        self.sequence_counter = 0
        self.start_time = time.time()
        
        # ✅ LOG PARA CONFIRMAR
        logger.debug(f"🎚️ NativeAudioEncoder inicializado con {self.sample_rate}Hz")
        
        # ✅ SIN master_volume - audio sin atenuar
        # El limiter en el cliente maneja los picos
        
        # Estadísticas de conversión
        self.conversion_stats = {
            'total_samples': 0,
            'clipped_samples': 0,
            'max_peak': 0.0,
            'last_warning_time': 0
        }
    
    def float32_to_int16(self, audio_data: np.ndarray) -> np.ndarray:
        """
        ✅ Conversión OPTIMIZADA de float32 a int16
        
        PRINCIPIOS:
        1. Mantener dinámica original
        2. No aplicar normalización automática
        3. Solo hard clipping si absolutamente necesario
        4. Monitorear pero no corregir automáticamente
        
        Args:
            audio_data: Array numpy float32 en rango [-1.0, 1.0]
            
        Returns:
            Array numpy int16 listo para transmisión
        """
        
        # ✅ 1. VERIFICACIÓN DE SEGURIDAD
        if audio_data.size == 0:
            return np.array([], dtype=np.int16)
        
        # ✅ 2. DETECTAR PEAK ANTES DE CONVERSIÓN
        peak_before = np.max(np.abs(audio_data)) if audio_data.size > 0 else 0
        
        # Actualizar estadísticas
        self.conversion_stats['total_samples'] += audio_data.size
        self.conversion_stats['max_peak'] = max(self.conversion_stats['max_peak'], peak_before)
        
        # ✅ 3. CONVERSIÓN DIRECTA (sin normalización)
        # Multiplicar por 32767 (no 32768) para mantener simetría [-32767, 32767]
        audio_int16 = (audio_data * 32767.0).astype(np.int16)
        
        # ✅ 4. DETECTAR CLIPPING
        max_val = np.max(audio_int16) if audio_int16.size > 0 else 0
        min_val = np.min(audio_int16) if audio_int16.size > 0 else 0
        
        samples_clipped = 0
        if max_val > 32767 or min_val < -32767:
            over_samples = np.sum(audio_int16 > 32767)
            under_samples = np.sum(audio_int16 < -32767)
            samples_clipped = over_samples + under_samples
            self.conversion_stats['clipped_samples'] += samples_clipped
            
        # ✅ 5. APLICAR SOFT CLIPPING SOLO SI ES CRÍTICO
        # Por defecto está DESACTIVADO - mantener audio original
        apply_soft_clip = False
        
        if apply_soft_clip and samples_clipped > 0 and samples_clipped / audio_data.size > 0.01:
            # Solo si más del 1% de muestras están clipadas
            current_time = time.time()
            
            # No spammear warnings - máximo uno cada 10 segundos
            if current_time - self.conversion_stats['last_warning_time'] > 10:
                logger.warning(f"🔧 Aplicando soft-clip: {samples_clipped} muestras clipadas")
                self.conversion_stats['last_warning_time'] = current_time
            
            # Convertir a float para procesamiento
            audio_float = audio_int16.astype(np.float32) / 32767.0
            
            # Soft clipping: aproximación polinómica de tanh (más rápido)
            def soft_clip_batch(x):
                # Limitar rango de entrada
                x = np.clip(x, -1.5, 1.5)
                # Aproximación de tanh: x - x³/3 + 2x⁵/15 - ...
                return x - (x**3) / 3.0
            
            audio_float = soft_clip_batch(audio_float)
            
            # Convertir de vuelta a int16
            audio_int16 = (audio_float * 32767.0).astype(np.int16)
        
        # ✅ 6. GARANTIZAR LÍMITES (hard clip solo si absolutamente necesario)
        # Normalmente esto NO debería ser necesario si la entrada es válida
        if np.any(audio_int16 > 32767) or np.any(audio_int16 < -32767):
            audio_int16 = np.clip(audio_int16, -32767, 32767)
            
            # Solo loggear si es significativo
            if samples_clipped > audio_data.size * 0.05:  # Más del 5%
                logger.warning(f"🛡️ Hard clipping aplicado a {samples_clipped} muestras")
        
        # ✅ 7. LOGGING DIAGNÓSTICO (solo en verbose)
        if config.VERBOSE:
            # Solo mostrar cada 100 conversiones
            if self.conversion_stats['total_samples'] % (config.BLOCKSIZE * 100) == 0:
                clip_percent = (self.conversion_stats['clipped_samples'] / 
                              max(1, self.conversion_stats['total_samples'])) * 100
                
                logger.debug(
                    f"🎚️ Conversión stats: "
                    f"peak={peak_before:.3f}, "
                    f"clipped={self.conversion_stats['clipped_samples']} "
                    f"({clip_percent:.2f}%)"
                )
        
        return audio_int16
    
    def create_audio_packet(self, 
                           audio_data: np.ndarray, 
                           active_channels: List[int],
                           timestamp: int) -> bytes:
        """
        ✅ Crea paquete de audio OPTIMIZADO V2.1
        
        CARACTERÍSTICAS:
        - Sin atenuación de volumen
        - Entrelazado correcto
        - Tamaño exacto (256 samples)
        - Máscara de canales eficiente
        
        Args:
            audio_data: Array numpy float32 [samples, channels]
            active_channels: Lista de canales activos
            timestamp: Timestamp en ms
            
        Returns:
            Bytes del paquete completo (header + payload)
        """
        if not active_channels or audio_data.size == 0:
            return b''
        
        # ✅ 1. VERIFICAR DIMENSIONES
        samples, total_channels = audio_data.shape
        
        # ✅ 2. EXTRAER CANALES ACTIVOS
        # Asegurar que los canales solicitados existen
        valid_channels = [ch for ch in active_channels if ch < total_channels]
        
        if not valid_channels:
            logger.warning(f"❌ No hay canales válidos: solicitados {active_channels}, disponibles {total_channels}")
            return b''
        
        # Extraer datos de canales válidos
        selected_data = audio_data[:, valid_channels]
        
        # ✅ 3. CONVERTIR A INT16 (manteniendo dinámica original)
        audio_int16 = self.float32_to_int16(selected_data)
        
        # ✅ 4. ENTRELAZAR: sample0[ch0,ch1,...], sample1[ch0,ch1,...]
        flat_audio = audio_int16.flatten('C')  # Orden 'C' para entrelazado por fila
        
        # ✅ 5. CREAR MÁSCARA DE CANALES EFICIENTE
        channel_mask = 0
        for ch in valid_channels:
            if 0 <= ch < 32:  # Máximo 32 canales en máscara
                channel_mask |= (1 << ch)
        
        # ✅ 6. PAYLOAD: máscara (4 bytes) + audio entrelazado
        mask_bytes = struct.pack('!I', channel_mask)
        audio_bytes = flat_audio.tobytes()
        payload = mask_bytes + audio_bytes
        
        # ✅ 7. HEADER DE 20 BYTES (V2.1)
        header = struct.pack(
            '!IHBBIII',
            config.NATIVE_MAGIC_NUMBER,
            config.NATIVE_PROTOCOL_VERSION,
            self.MSG_TYPE_AUDIO,
            0,  # flags
            timestamp,
            self.sequence_counter,
            len(payload)  # ✅ Longitud del payload incluida en header
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
            0,  # flags
            int((time.time() - self.start_time) * 1000) % (2**31),
            0,  # sequence
            len(message_bytes)  # payload length
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
            0,  # flags
            int((time.time() - self.start_time) * 1000) % (2**31),
            0,  # sequence
            len(config_bytes)  # payload length
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
            0,  # flags
            int((time.time() - self.start_time) * 1000) % (2**31),
            0,  # sequence
            len(ping_data)  # payload length
        )
        
        return header + ping_data
    
    def get_conversion_stats(self) -> Dict:
        """Obtener estadísticas de conversión"""
        clip_percent = 0
        if self.conversion_stats['total_samples'] > 0:
            clip_percent = (self.conversion_stats['clipped_samples'] / 
                          self.conversion_stats['total_samples']) * 100
        
        return {
            'sample_rate': self.sample_rate,
            'total_samples': self.conversion_stats['total_samples'],
            'clipped_samples': self.conversion_stats['clipped_samples'],
            'clip_percent': clip_percent,
            'max_peak': self.conversion_stats['max_peak'],
            'sequence_counter': self.sequence_counter
        }
    
    def reset_stats(self):
        """Resetear estadísticas de conversión"""
        self.conversion_stats = {
            'total_samples': 0,
            'clipped_samples': 0,
            'max_peak': 0.0,
            'last_warning_time': 0
        }

class NativeControlProtocol:
    """Protocolo de control JSON optimizado para APK V2.1"""
    
    @staticmethod
    def encode_handshake(client_type: str = "android_v2", 
                        capabilities: List[str] = None) -> str:
        """Codificar mensaje de handshake"""
        if capabilities is None:
            capabilities = ["low_latency", "multi_channel", "auto_gain"]
        
        return json.dumps({
            'type': 'handshake',
            'client_type': client_type,
            'protocol_version': config.NATIVE_PROTOCOL_VERSION,
            'capabilities': capabilities,
            'timestamp': int(time.time() * 1000),
            'session_id': f"android_{int(time.time() * 1000)}"
        }, separators=(',', ':'))
    
    @staticmethod
    def encode_subscribe(channels: List[int], 
                        sample_rate: int = None,
                        format: str = "pcm_16bit") -> str:
        """
        ✅ Codificar mensaje de suscripción SIN ganancias
        Las ganancias se manejan LOCALMENTE en el cliente
        """
        if sample_rate is None:
            sample_rate = config.SAMPLE_RATE
        
        return json.dumps({
            'type': 'subscribe',
            'channels': channels,
            'sample_rate': sample_rate,
            'format': format,
            'timestamp': int(time.time() * 1000)
        }, separators=(',', ':'))
    
    @staticmethod
    def encode_update_gain_local(channel: int, gain_db: float) -> str:
        """
        ✅ Para uso LOCAL en cliente - NO se envía al servidor
        Solo para referencia si el cliente quiere sincronizar con otros
        """
        return json.dumps({
            'type': 'update_gain_local',
            'channel': channel,
            'gain_db': gain_db,
            'timestamp': int(time.time() * 1000)
        }, separators=(',', ':'))
    
    @staticmethod
    def encode_heartbeat(client_id: str) -> str:
        """Codificar heartbeat"""
        return json.dumps({
            'type': 'heartbeat',
            'client_id': client_id,
            'timestamp': int(time.time() * 1000)
        }, separators=(',', ':'))
    
    @staticmethod
    def encode_ping(counter: int = 0) -> str:
        """Codificar ping"""
        return json.dumps({
            'type': 'ping',
            'counter': counter,
            'timestamp': int(time.time() * 1000)
        }, separators=(',', ':'))
    
    @staticmethod
    def encode_error(error_msg: str, code: int = 0) -> str:
        """Codificar error"""
        return json.dumps({
            'type': 'error',
            'code': code,
            'message': error_msg,
            'timestamp': int(time.time() * 1000)
        }, separators=(',', ':'))
    
    @staticmethod
    def encode_get_stats(detailed: bool = False) -> str:
        """Solicitar estadísticas"""
        return json.dumps({
            'type': 'get_stats',
            'detailed': detailed,
            'timestamp': int(time.time() * 1000)
        }, separators=(',', ':'))
    
    @staticmethod
    def decode_message(data: str) -> Dict:
        """Decodificar mensaje JSON"""
        try:
            return json.loads(data)
        except json.JSONDecodeError as e:
            logger.error(f"❌ Error decodificando JSON: {e}")
            return {'type': 'error', 'message': f'JSON inválido: {str(e)}'}

class NativeDecoder:
    """Decodificador de paquetes nativos V2.1"""
    
    @staticmethod
    def decode_audio_packet(header_tuple: tuple, payload: bytes) -> Dict:
        """
        Decodifica paquete de audio V2.1
        
        Estructura:
        - Header: 20 bytes
        - Payload: máscara(4) + audio_entrelazado
        
        Returns:
            Dict con datos decodificados
        """
        magic, version, msg_type, flags, timestamp, sequence, payload_length = header_tuple
        
        if len(payload) < 4:
            raise ValueError(f"Payload de audio muy pequeño: {len(payload)} bytes")
        
        # ✅ 1. LEER MÁSCARA DE CANALES
        channel_mask = struct.unpack('!I', payload[:4])[0]
        audio_bytes = payload[4:]
        
        # ✅ 2. CALCULAR CANALES ACTIVOS
        active_channels = []
        for i in range(32):  # Máximo 32 canales
            if channel_mask & (1 << i):
                active_channels.append(i)
        
        if not active_channels:
            logger.warning("⚠️ Paquete de audio sin canales activos")
            return {
                'timestamp': timestamp,
                'sequence': sequence,
                'channel_mask': channel_mask,
                'active_channels': [],
                'audio_data': np.array([], dtype=np.int16),
                'sample_count': 0
            }
        
        # ✅ 3. DECODIFICAR AUDIO INT16
        if len(audio_bytes) % 2 != 0:
            raise ValueError(f"Audio data size inválido: {len(audio_bytes)} bytes")
        
        # Convertir bytes a int16
        audio_samples = np.frombuffer(audio_bytes, dtype=np.int16)
        
        # ✅ 4. CALCULAR SAMPLES POR CANAL
        total_samples = len(audio_samples)
        samples_per_channel = total_samples // len(active_channels)
        
        if total_samples % len(active_channels) != 0:
            logger.warning(
                f"⚠️ Audio size inconsistente: "
                f"{total_samples} samples / {len(active_channels)} canales = "
                f"{samples_per_channel} samples por canal"
            )
        
        # ✅ 5. CALCULAR PEAK PARA LOGGING
        peak_level = 0
        if audio_samples.size > 0:
            peak_level = np.max(np.abs(audio_samples.astype(np.float32) / 32767.0))
        
        if config.VERBOSE and peak_level > 0.9:
            logger.debug(f"📶 Audio peak: {peak_level:.3f}, canales: {len(active_channels)}")
        
        return {
            'timestamp': timestamp,
            'sequence': sequence,
            'channel_mask': channel_mask,
            'active_channels': active_channels,
            'audio_data': audio_samples,
            'sample_count': samples_per_channel,
            'samples_total': total_samples,
            'peak_level': peak_level,
            'flags': flags
        }
    
    @staticmethod
    def decode_control_packet(header_tuple: tuple, payload: bytes) -> Dict:
        """Decodifica paquete de control"""
        try:
            message = payload.decode('utf-8')
            return json.loads(message)
        except UnicodeDecodeError as e:
            raise ValueError(f"Error decodificando UTF-8: {e}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Error decodificando JSON: {e}")
    
    @staticmethod
    def decode_ping_packet(header_tuple: tuple, payload: bytes) -> Dict:
        """Decodifica paquete de ping"""
        counter = 0
        if len(payload) >= 8:
            try:
                counter = struct.unpack('!Q', payload[:8])[0]
            except struct.error:
                pass
        
        return {
            'type': 'ping',
            'counter': counter,
            'timestamp': header_tuple[4],
            'flags': header_tuple[3]
        }
    
    @staticmethod
    def decode_config_packet(header_tuple: tuple, payload: bytes) -> Dict:
        """Decodifica paquete de configuración"""
        try:
            message = payload.decode('utf-8')
            config_data = json.loads(message)
            
            # ✅ Asegurar tipos de datos correctos
            if 'sample_rate' in config_data:
                config_data['sample_rate'] = int(config_data['sample_rate'])
            if 'channels' in config_data:
                config_data['channels'] = int(config_data['channels'])
            if 'buffer_size' in config_data:
                config_data['buffer_size'] = int(config_data['buffer_size'])
            
            return config_data
            
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            logger.error(f"❌ Error decodificando config: {e}")
            return {
                'type': 'config_error',
                'error': str(e),
                'timestamp': header_tuple[4]
            }

# ✅ FUNCIONES DE UTILIDAD

def verify_protocol_compatibility() -> Tuple[bool, str]:
    """
    Verifica compatibilidad del protocolo
    
    Returns:
        Tuple (compatible, message)
    """
    try:
        # Verificar constantes
        required_magic = config.NATIVE_MAGIC_NUMBER
        required_version = config.NATIVE_PROTOCOL_VERSION
        required_header_size = 20
        
        if required_magic != 0xA1D10A7C:
            return False, f"Magic number incorrecto: {hex(required_magic)}"
        
        if required_version != 2:
            return False, f"Versión de protocolo incorrecta: {required_version}"
        
        # Verificar estructura del header
        test_header = struct.pack('!IHBBIII', 
                                 required_magic,
                                 required_version,
                                 0x01,  # audio
                                 0x00,  # flags
                                 123456,  # timestamp
                                 1,      # sequence
                                 256)    # payload length
        
        if len(test_header) != required_header_size:
            return False, f"Header size incorrecto: {len(test_header)} != {required_header_size}"
        
        # Decodificar para verificar
        decoded = struct.unpack('!IHBBIII', test_header)
        if decoded[0] != required_magic:
            return False, "Magic number no coincide al decodificar"
        
        return True, f"✅ Protocolo V{required_version} compatible (Magic: {hex(required_magic)})"
        
    except Exception as e:
        return False, f"Error verificando protocolo: {str(e)}"

def create_test_audio_packet(sample_rate: int = None) -> bytes:
    """
    Crear paquete de audio de prueba
    
    Args:
        sample_rate: Sample rate para el encoder
        
    Returns:
        Bytes del paquete de prueba
    """
    if sample_rate is None:
        sample_rate = config.SAMPLE_RATE
    
    encoder = NativeAudioEncoder(sample_rate=sample_rate)
    
    # Crear audio de prueba (sinusoide de 440Hz)
    duration = 0.01  # 10ms
    samples = int(duration * sample_rate)
    t = np.linspace(0, duration, samples, endpoint=False)
    
    # Canal 0: sinusoide 440Hz
    channel0 = 0.5 * np.sin(2 * np.pi * 440 * t)
    # Canal 1: sinusoide 880Hz
    channel1 = 0.3 * np.sin(2 * np.pi * 880 * t)
    
    # Crear array 2D: [samples, channels]
    audio_data = np.column_stack([channel0, channel1])
    
    # Crear paquete
    packet = encoder.create_audio_packet(
        audio_data=audio_data,
        active_channels=[0, 1],
        timestamp=int(time.time() * 1000)
    )
    
    return packet

# ✅ INICIALIZACIÓN Y PRUEBAS
if __name__ == "__main__":
    print("🔍 Probando native_protocol.py...")
    print(f"Config SAMPLE_RATE: {config.SAMPLE_RATE}Hz")
    print(f"Config BLOCKSIZE: {config.BLOCKSIZE}")
    
    # Verificar compatibilidad
    compatible, message = verify_protocol_compatibility()
    print(message)
    
    if compatible:
        # Probar encoder
        encoder = NativeAudioEncoder()
        print(f"Encoder sample rate: {encoder.sample_rate}Hz")
        
        # Crear paquete de prueba
        test_packet = create_test_audio_packet()
        print(f"Paquete de prueba creado: {len(test_packet)} bytes")
        
        # Decodificar header
        try:
            header = NativePacket.decode_header(test_packet[:20])
            print(f"Header decodificado: magic={hex(header[0])}, type={header[2]}, length={header[6]}")
        except Exception as e:
            print(f"❌ Error decodificando: {e}")
    
    print("✅ native_protocol.py listo")