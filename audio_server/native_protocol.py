import struct
import time
import numpy as np
import json
import logging

logger = logging.getLogger(__name__)

class NativeAndroidProtocol:
    HEADER_SIZE = 16
    MAGIC_NUMBER = 0xA1D10A7C
    PROTOCOL_VERSION = 2
    MSG_TYPE_AUDIO = 0x01
    MSG_TYPE_CONTROL = 0x02
    FLAG_FLOAT32 = 0x01
    FLAG_RF_MODE = 0x80
    
    # ✅ Límites consistentes con cliente Android
    MAX_CONTROL_PAYLOAD = 500_000  # 500KB
    MAX_AUDIO_PAYLOAD = 2_000_000  # 2MB

    @staticmethod
    def create_audio_packet(audio_data, active_channels, sample_position, sequence=0, rf_mode=False):
        """
        Crear paquete de audio con header binario
        
        Args:
            audio_data: numpy array con shape (samples, channels)
            active_channels: lista de índices de canales activos
            sample_position: posición actual de la muestra
            sequence: número de secuencia del paquete
            rf_mode: flag para modo RF
            
        Returns:
            bytes: Paquete completo con header + payload, o None si hay error
        """
        try:
            samples, total_channels = audio_data.shape
            
            # Validar entrada
            if samples == 0 or total_channels == 0:
                logger.warning("⚠️ Audio data vacío")
                return None
            
            # Crear channel mask
            channel_mask = 0
            for ch in active_channels:
                if 0 <= ch < 48:  # Máximo 48 canales soportados
                    channel_mask |= (1 << ch)
            
            # ✅ FIXED: Validar que los canales existen
            valid_channels = [ch for ch in active_channels if ch < total_channels]
            if not valid_channels:
                logger.warning(f"⚠️ No hay canales válidos: {active_channels} (max: {total_channels-1})")
                return None
            
            # Seleccionar y entrelazar datos de audio
            selected_data = audio_data[:, valid_channels]
            interleaved = selected_data.flatten('C')  # Row-major order
            
            # Convertir a big-endian float32
            audio_bytes = interleaved.astype('>f4').tobytes()
            
            # ✅ Payload: 8 bytes (sample_position) + 4 bytes (channel_mask) + audio_data
            payload = struct.pack('!QI', sample_position, channel_mask) + audio_bytes
            
            # ✅ Validar tamaño antes de crear paquete
            if len(payload) > NativeAndroidProtocol.MAX_AUDIO_PAYLOAD:
                logger.error(f"❌ Payload audio demasiado grande: {len(payload)} bytes (max: {NativeAndroidProtocol.MAX_AUDIO_PAYLOAD})")
                return None
            
            # Configurar flags
            flags = NativeAndroidProtocol.FLAG_FLOAT32
            if rf_mode:
                flags |= NativeAndroidProtocol.FLAG_RF_MODE
            
            # ✅ CRÍTICO: Header binario correcto (16 bytes)
            header = struct.pack('!IHHII', 
                NativeAndroidProtocol.MAGIC_NUMBER,      # 4 bytes - magic
                NativeAndroidProtocol.PROTOCOL_VERSION,  # 2 bytes - version
                (NativeAndroidProtocol.MSG_TYPE_AUDIO << 8) | flags,  # 2 bytes - type + flags
                int(time.time() * 1000) & 0xFFFFFFFF,   # 4 bytes - timestamp
                len(payload))                            # 4 bytes - payload length
            
            packet = header + payload
            
            # ✅ DEBUG: Validar que el paquete es correcto
            if len(packet) < 16:
                logger.error(f"❌ Paquete demasiado pequeño: {len(packet)} bytes")
                return None
            
            # Verificar magic number
            magic_check = struct.unpack('!I', packet[0:4])[0]
            if magic_check != NativeAndroidProtocol.MAGIC_NUMBER:
                logger.error(f"❌ Magic number incorrecto en paquete creado: 0x{magic_check:X}")
                return None
            
            return packet
            
        except Exception as e:
            logger.error(f"❌ Error creando paquete de audio: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    @staticmethod
    def create_control_packet(message_type, data=None, rf_mode=False):
        """
        ✅ CRÍTICO: Crear paquete de control SIEMPRE con header binario
        
        Args:
            message_type: tipo de mensaje (string)
            data: diccionario con datos adicionales
            rf_mode: flag para modo RF
            
        Returns:
            bytes: Paquete completo con header + payload JSON, o None si hay error
        """
        if data is None: 
            data = {}
        
        try:
            # Crear mensaje JSON
            message = {
                'type': message_type, 
                'timestamp': int(time.time() * 1000),
                **data
            }
            
            # Solo agregar rf_mode si es True
            if rf_mode:
                message['rf_mode'] = True
            
            # ✅ CRÍTICO: JSON compacto sin espacios (minimiza tamaño)
            message_bytes = json.dumps(message, separators=(',', ':')).encode('utf-8')
            
            # ✅ CRÍTICO: Validar tamaño con límite consistente
            if len(message_bytes) > NativeAndroidProtocol.MAX_CONTROL_PAYLOAD:
                logger.error(f"❌ Mensaje de control demasiado grande: {len(message_bytes)} bytes (max: {NativeAndroidProtocol.MAX_CONTROL_PAYLOAD})")
                return None
            
            # Configurar flags
            flags = 0
            if rf_mode:
                flags |= NativeAndroidProtocol.FLAG_RF_MODE
            
            # ✅ CRÍTICO: Header binario SIEMPRE (16 bytes)
            header = struct.pack('!IHHII', 
                NativeAndroidProtocol.MAGIC_NUMBER,      # 4 bytes - magic
                NativeAndroidProtocol.PROTOCOL_VERSION,  # 2 bytes - version
                (NativeAndroidProtocol.MSG_TYPE_CONTROL << 8) | flags,  # 2 bytes - type + flags
                int(time.time() * 1000) & 0xFFFFFFFF,   # 4 bytes - timestamp
                len(message_bytes))                      # 4 bytes - payload length
            
            packet = header + message_bytes
            
            # ✅ DEBUG: Validar paquete creado
            if len(packet) < 16:
                logger.error(f"❌ Paquete control demasiado pequeño: {len(packet)} bytes")
                return None
            
            # Verificar magic number
            magic_check = struct.unpack('!I', packet[0:4])[0]
            if magic_check != NativeAndroidProtocol.MAGIC_NUMBER:
                logger.error(f"❌ Magic number incorrecto en control: 0x{magic_check:X}")
                logger.error(f"   Esperado: 0x{NativeAndroidProtocol.MAGIC_NUMBER:X}")
                logger.error(f"   Primeros 20 bytes: {packet[:20].hex()}")
                return None
            
            logger.debug(f"✅ Paquete control creado: type={message_type}, size={len(packet)} bytes")
            logger.debug(f"   Header: magic=0x{NativeAndroidProtocol.MAGIC_NUMBER:X}, payload={len(message_bytes)}")
            
            return packet
            
        except Exception as e:
            logger.error(f"❌ Error creando paquete de control: {e}")
            import traceback
            traceback.print_exc()
            return None

    @staticmethod
    def validate_packet(packet_bytes):
        """
        ✅ NEW: Validar que un paquete tiene el formato correcto
        
        Args:
            packet_bytes: bytes del paquete a validar
            
        Returns:
            tuple: (bool: válido, str: mensaje de error/OK)
        """
        if not packet_bytes:
            return False, "Paquete None"
        
        if len(packet_bytes) < 16:
            return False, f"Paquete demasiado pequeño: {len(packet_bytes)} bytes (mínimo 16)"
        
        try:
            # Validar magic number
            magic = struct.unpack('!I', packet_bytes[0:4])[0]
            if magic != NativeAndroidProtocol.MAGIC_NUMBER:
                return False, f"Magic inválido: 0x{magic:X} (esperado: 0x{NativeAndroidProtocol.MAGIC_NUMBER:X})"
            
            # Validar version
            version = struct.unpack('!H', packet_bytes[4:6])[0]
            if version != NativeAndroidProtocol.PROTOCOL_VERSION:
                return False, f"Versión inválida: {version} (esperado: {NativeAndroidProtocol.PROTOCOL_VERSION})"
            
            # Validar type and flags
            typeAndFlags = struct.unpack('!H', packet_bytes[6:8])[0]
            msgType = (typeAndFlags >> 8) & 0xFF
            if msgType not in [NativeAndroidProtocol.MSG_TYPE_AUDIO, NativeAndroidProtocol.MSG_TYPE_CONTROL]:
                return False, f"Tipo de mensaje inválido: {msgType}"
            
            # Validar payload length
            payload_length = struct.unpack('!I', packet_bytes[12:16])[0]
            expected_total = 16 + payload_length
            
            if len(packet_bytes) != expected_total:
                return False, f"Tamaño incorrecto: {len(packet_bytes)} bytes (esperado: {expected_total})"
            
            # ✅ Validar que payload length está dentro de límites
            max_payload = NativeAndroidProtocol.MAX_AUDIO_PAYLOAD if msgType == NativeAndroidProtocol.MSG_TYPE_AUDIO else NativeAndroidProtocol.MAX_CONTROL_PAYLOAD
            if payload_length < 0 or payload_length > max_payload:
                return False, f"Payload length fuera de rango: {payload_length} (max: {max_payload})"
            
            return True, "OK"
            
        except struct.error as e:
            return False, f"Error struct unpack: {e}"
        except Exception as e:
            return False, f"Error validación: {e}"

    @staticmethod
    def decode_header(header_bytes):
        """
        Decodificar header de 16 bytes
        
        Args:
            header_bytes: bytes del header
            
        Returns:
            dict con campos del header, o None si hay error
        """
        if len(header_bytes) != 16:
            logger.error(f"❌ Header debe ser 16 bytes, recibido: {len(header_bytes)}")
            return None
        
        try:
            magic, version, typeAndFlags, timestamp, payloadLength = struct.unpack('!IHHII', header_bytes)
            
            msgType = (typeAndFlags >> 8) & 0xFF
            flags = typeAndFlags & 0xFF
            
            return {
                'magic': magic,
                'version': version,
                'msg_type': msgType,
                'flags': flags,
                'timestamp': timestamp,
                'payload_length': payloadLength,
                'rf_mode': bool(flags & NativeAndroidProtocol.FLAG_RF_MODE),
                'float32': bool(flags & NativeAndroidProtocol.FLAG_FLOAT32)
            }
        except Exception as e:
            logger.error(f"❌ Error decodificando header: {e}")
            return None

    @staticmethod
    def decode_audio_payload(payload_bytes):
        """
        Decodificar payload de audio
        
        Args:
            payload_bytes: bytes del payload
            
        Returns:
            dict con datos de audio, o None si hay error
        """
        if len(payload_bytes) < 12:  # Mínimo: 8 (sample_pos) + 4 (channel_mask)
            logger.error(f"❌ Payload de audio muy pequeño: {len(payload_bytes)} bytes")
            return None
        
        try:
            # Primeros 12 bytes: sample_position (8) + channel_mask (4)
            sample_position, channel_mask = struct.unpack('!QI', payload_bytes[:12])
            
            # Extraer canales activos del mask
            active_channels = []
            for i in range(48):
                if channel_mask & (1 << i):
                    active_channels.append(i)
            
            # Resto es audio data
            audio_bytes = payload_bytes[12:]
            
            # Convertir a float32 big-endian
            num_floats = len(audio_bytes) // 4
            audio_array = np.frombuffer(audio_bytes, dtype='>f4', count=num_floats)
            
            # Calcular samples por canal
            if len(active_channels) > 0:
                samples_per_channel = num_floats // len(active_channels)
            else:
                samples_per_channel = 0
            
            return {
                'sample_position': sample_position,
                'channel_mask': channel_mask,
                'active_channels': active_channels,
                'audio_data': audio_array,
                'samples_per_channel': samples_per_channel
            }
        except Exception as e:
            logger.error(f"❌ Error decodificando payload de audio: {e}")
            return None

    @staticmethod
    def decode_control_payload(payload_bytes):
        """
        Decodificar payload de control (JSON)
        
        Args:
            payload_bytes: bytes del payload
            
        Returns:
            dict con datos de control, o None si hay error
        """
        try:
            message = json.loads(payload_bytes.decode('utf-8'))
            return message
        except json.JSONDecodeError as e:
            logger.error(f"❌ Error decodificando JSON: {e}")
            logger.error(f"   Payload: {payload_bytes[:100]}")
            return None
        except Exception as e:
            logger.error(f"❌ Error decodificando payload de control: {e}")
            return None

    @staticmethod
    def get_packet_info(packet_bytes):
        """
        Obtener información de un paquete completo (debug)
        
        Args:
            packet_bytes: bytes del paquete
            
        Returns:
            dict con información del paquete
        """
        if not packet_bytes or len(packet_bytes) < 16:
            return {'error': 'Paquete inválido o muy pequeño'}
        
        header = NativeAndroidProtocol.decode_header(packet_bytes[:16])
        if not header:
            return {'error': 'Header inválido'}
        
        info = {
            'total_size': len(packet_bytes),
            'header': header,
            'valid': False,
            'error': None
        }
        
        # Validar paquete
        valid, error = NativeAndroidProtocol.validate_packet(packet_bytes)
        info['valid'] = valid
        info['error'] = error
        
        # Si es válido, decodificar payload según tipo
        if valid:
            payload = packet_bytes[16:]
            if header['msg_type'] == NativeAndroidProtocol.MSG_TYPE_AUDIO:
                audio_info = NativeAndroidProtocol.decode_audio_payload(payload)
                if audio_info:
                    info['audio'] = audio_info
            elif header['msg_type'] == NativeAndroidProtocol.MSG_TYPE_CONTROL:
                control_info = NativeAndroidProtocol.decode_control_payload(payload)
                if control_info:
                    info['control'] = control_info
        
        return info