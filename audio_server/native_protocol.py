# native_protocol.py

import struct

import time

import numpy as np

import json

import logging

import config



logger = logging.getLogger(__name__)



class NativeAndroidProtocol:

    HEADER_SIZE = 16

    MAGIC_NUMBER = 0xA1D10A7C

    PROTOCOL_VERSION = 2

    MSG_TYPE_AUDIO = 0x01

    MSG_TYPE_CONTROL = 0x02

    FLAG_FLOAT32 = 0x01

    FLAG_INT16 = 0x02      # ✅ NUEVO: Flag para Int16

    FLAG_RF_MODE = 0x80

    

    MAX_CONTROL_PAYLOAD = 500_000

    MAX_AUDIO_PAYLOAD = 2_000_000

    

    # ✅ OPTIMIZACIÓN: Struct pre-compilado para headers

    _header_struct = struct.Struct('!IHHII')

    _payload_struct = struct.Struct('!QI')

    

    # ✅ OPTIMIZACIÓN: Buffers pre-alocados

    _header_buffer = bytearray(HEADER_SIZE)



    @staticmethod

    def create_audio_packet(audio_data, active_channels, sample_position, sequence=0, rf_mode=False):

        """

        ✅ OPTIMIZADO: Soporta Int16 para -50% reducción de datos

        """

        try:

            # ✅ Validación temprana

            if not active_channels or len(active_channels) == 0:

                return None

            

            # ✅ Convertir memoryview a ndarray si es necesario

            if isinstance(audio_data, memoryview):

                num_channels = len(active_channels)

                # Calcular samples basado en el tamaño del memoryview

                total_samples = len(audio_data) // 4  # float32 = 4 bytes

                if total_samples % num_channels != 0:

                    logger.warning(f"⚠️ Tamaño de audio inconsistente: {total_samples} samples, {num_channels} channels")

                    return None

                    

                audio_data = np.frombuffer(audio_data, dtype=np.float32, count=total_samples)

                audio_data = audio_data.reshape(-1, num_channels)

            

            if audio_data.size == 0 or audio_data.shape[1] == 0:

                return None

            

            samples, total_channels = audio_data.shape

            

            # ✅ Filtrar canales válidos

            valid_channels = [ch for ch in active_channels if 0 <= ch < total_channels]

            if not valid_channels:

                if config.DEBUG:

                    logger.debug(f"⚠️ No hay canales válidos para enviar: {active_channels} (max: {total_channels-1})")

                return None

            

            # ✅ Crear channel mask eficientemente

            channel_mask = 0

            for ch in valid_channels:

                if 0 <= ch < 48:  # Máximo 48 canales soportados

                    channel_mask |= (1 << ch)

            

            # ✅ Seleccionar y entrelazar datos (operación única)

            selected_data = audio_data[:, valid_channels]

            interleaved = selected_data.flatten('C')

            

            # ✅ DECISIÓN: Int16 o Float32 según config

            use_int16 = getattr(config, 'USE_INT16_ENCODING', True)

            

            if use_int16:

                # ✅ CODIFICACIÓN INT16 CON VALIDACIÓN

                # Clamping: asegurar que está en rango [-0.9999, 0.9999] para evitar overflow

                np.clip(interleaved, -0.9999, 0.9999, out=interleaved)

                

                # Convertir float [-0.9999, 0.9999] a int16 [-32767, 32767]

                interleaved_int16 = (interleaved * 32767.0).astype(np.int16)

                

                # Convertir a big-endian bytes

                audio_bytes = interleaved_int16.astype('>i2').tobytes()

                

                flags = NativeAndroidProtocol.FLAG_INT16

            else:

                # Float32 original

                audio_bytes = interleaved.astype('>f4').tobytes()

                flags = NativeAndroidProtocol.FLAG_FLOAT32

            

            # ✅ Validar tamaño del payload

            payload_size = 12 + len(audio_bytes)

            if payload_size > NativeAndroidProtocol.MAX_AUDIO_PAYLOAD:

                if config.DEBUG:

                    logger.warning(f"⚠️ Payload demasiado grande: {payload_size} bytes")

                return None

            

            # ✅ Construir payload eficientemente

            payload = bytearray(payload_size)

            NativeAndroidProtocol._payload_struct.pack_into(payload, 0, sample_position, channel_mask)

            payload[12:] = audio_bytes

            

            # ✅ Configurar flags RF

            if rf_mode:

                flags |= NativeAndroidProtocol.FLAG_RF_MODE

            

            # ✅ Construir header usando struct pre-compilado

            header = bytearray(16)

            NativeAndroidProtocol._header_struct.pack_into(

                header, 0,

                NativeAndroidProtocol.MAGIC_NUMBER,

                NativeAndroidProtocol.PROTOCOL_VERSION,

                (NativeAndroidProtocol.MSG_TYPE_AUDIO << 8) | flags,

                int(time.time() * 1000) & 0xFFFFFFFF,

                len(payload)

            )

            

            # ✅ Concatenar sin validación adicional en producción

            packet = bytes(header) + bytes(payload)

            

            # ✅ SOLO validar en DEBUG mode

            if config.DEBUG and config.VALIDATE_PACKETS:

                magic_check = struct.unpack('!I', packet[0:4])[0]

                if magic_check != NativeAndroidProtocol.MAGIC_NUMBER:

                    logger.error(f"❌ Magic number incorrecto: 0x{magic_check:X}")

                    return None

            

            return packet

            

        except Exception as e:

            logger.error(f"❌ Error creando paquete de audio: {e}")

            if config.DEBUG:

                import traceback

                traceback.print_exc()

            return None

    

    @staticmethod

    def create_control_packet(message_type, data=None, rf_mode=False):

        """

        ✅ OPTIMIZADO: Crear paquete de control con header binario

        """

        if data is None: 

            data = {}

        

        try:

            # Crear mensaje JSON compacto

            message = {

                'type': message_type, 

                'timestamp': int(time.time() * 1000),

                **data

            }

            

            if rf_mode:

                message['rf_mode'] = True

            

            # ✅ JSON compacto sin espacios

            message_bytes = json.dumps(message, separators=(',', ':')).encode('utf-8')

            

            # ✅ Validar tamaño (solo si está habilitado)

            if config.VALIDATE_PACKETS and len(message_bytes) > NativeAndroidProtocol.MAX_CONTROL_PAYLOAD:

                logger.error(f"❌ Mensaje control muy grande: {len(message_bytes)} bytes")

                return None

            

            # Configurar flags

            flags = NativeAndroidProtocol.FLAG_RF_MODE if rf_mode else 0

            

            # ✅ Construir header usando struct pre-compilado

            header = bytearray(16)

            NativeAndroidProtocol._header_struct.pack_into(

                header, 0,

                NativeAndroidProtocol.MAGIC_NUMBER,

                NativeAndroidProtocol.PROTOCOL_VERSION,

                (NativeAndroidProtocol.MSG_TYPE_CONTROL << 8) | flags,

                int(time.time() * 1000) & 0xFFFFFFFF,

                len(message_bytes)

            )

            

            packet = bytes(header) + message_bytes

            

            # ✅ SOLO validar en DEBUG mode

            if config.DEBUG and config.VALIDATE_PACKETS:

                magic_check = struct.unpack('!I', packet[0:4])[0]

                if magic_check != NativeAndroidProtocol.MAGIC_NUMBER:

                    logger.error(f"❌ Magic incorrecto en control: 0x{magic_check:X}")

                    return None

                

                if config.DEBUG:

                    logger.debug(f"✅ Control: type={message_type}, size={len(packet)} bytes")

            

            return packet

            

        except Exception as e:

            logger.error(f"❌ Error creando paquete control: {e}")

            if config.DEBUG:

                import traceback

                traceback.print_exc()

            return None



    @staticmethod

    def validate_packet(packet_bytes):

        """

        Validar que un paquete tiene el formato correcto (solo para DEBUG)

        """

        if not packet_bytes:

            return False, "Paquete None"

        

        if len(packet_bytes) < 16:

            return False, f"Paquete pequeño: {len(packet_bytes)} bytes"

        

        try:

            magic = struct.unpack('!I', packet_bytes[0:4])[0]

            if magic != NativeAndroidProtocol.MAGIC_NUMBER:

                return False, f"Magic inválido: 0x{magic:X}"

            

            version = struct.unpack('!H', packet_bytes[4:6])[0]

            if version != NativeAndroidProtocol.PROTOCOL_VERSION:

                return False, f"Versión inválida: {version}"

            

            typeAndFlags = struct.unpack('!H', packet_bytes[6:8])[0]

            msgType = (typeAndFlags >> 8) & 0xFF

            if msgType not in [NativeAndroidProtocol.MSG_TYPE_AUDIO, NativeAndroidProtocol.MSG_TYPE_CONTROL]:

                return False, f"Tipo inválido: {msgType}"

            

            payload_length = struct.unpack('!I', packet_bytes[12:16])[0]

            expected_total = 16 + payload_length

            

            if len(packet_bytes) != expected_total:

                return False, f"Tamaño incorrecto: {len(packet_bytes)} vs {expected_total}"

            

            max_payload = NativeAndroidProtocol.MAX_AUDIO_PAYLOAD if msgType == NativeAndroidProtocol.MSG_TYPE_AUDIO else NativeAndroidProtocol.MAX_CONTROL_PAYLOAD

            if payload_length < 0 or payload_length > max_payload:

                return False, f"Payload fuera de rango: {payload_length}"

            

            return True, "OK"

            

        except Exception as e:

            return False, f"Error validación: {e}"



    @staticmethod

    def decode_header(header_bytes):

        """

        ✅ ACTUALIZADO: Decodificar header de 16 bytes con soporte Int16

        """

        if len(header_bytes) != 16:

            return None

        

        try:

            magic, version, typeAndFlags, timestamp, payloadLength = NativeAndroidProtocol._header_struct.unpack(header_bytes)

            

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

                'float32': bool(flags & NativeAndroidProtocol.FLAG_FLOAT32),

                'int16': bool(flags & NativeAndroidProtocol.FLAG_INT16)  # ✅ NUEVO

            }

        except Exception as e:

            if config.DEBUG:

                logger.error(f"❌ Error decodificando header: {e}")

            return None



    @staticmethod

    def decode_audio_payload(payload_bytes):

        """

        Decodificar payload de audio (usado para debugging del servidor)

        NOTA: El cliente Android tiene su propio decoder optimizado

        """

        if len(payload_bytes) < 12:

            return None

        

        try:

            sample_position, channel_mask = NativeAndroidProtocol._payload_struct.unpack(payload_bytes[:12])

            

            active_channels = [i for i in range(48) if channel_mask & (1 << i)]

            

            audio_bytes = payload_bytes[12:]

            

            # Determinar formato basado en tamaño

            if len(audio_bytes) % 2 == 0 and len(audio_bytes) // 2 == len(active_channels) * (len(audio_bytes) // (len(active_channels) * 2)):

                # Probablemente Int16

                num_shorts = len(audio_bytes) // 2

                audio_array = np.frombuffer(audio_bytes, dtype='>i2', count=num_shorts)

                audio_array = audio_array.astype(np.float32) / 32767.0

            else:

                # Float32

                num_floats = len(audio_bytes) // 4

                audio_array = np.frombuffer(audio_bytes, dtype='>f4', count=num_floats)

            

            samples_per_channel = len(audio_array) // len(active_channels) if active_channels else 0

            

            return {

                'sample_position': sample_position,

                'channel_mask': channel_mask,

                'active_channels': active_channels,

                'audio_data': audio_array,

                'samples_per_channel': samples_per_channel

            }

        except Exception as e:

            if config.DEBUG:

                logger.error(f"❌ Error decodificando audio: {e}")

            return None



    @staticmethod

    def decode_control_payload(payload_bytes):

        """Decodificar payload de control (JSON)"""

        try:

            message = json.loads(payload_bytes.decode('utf-8'))

            return message

        except Exception as e:

            if config.DEBUG:

                logger.error(f"❌ Error decodificando control: {e}")

            return None