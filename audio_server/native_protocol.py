import struct

import time

import numpy as np

import json

import logging



logger = logging.getLogger(__name__)



class NativeAndroidProtocol:

    HEADER_SIZE = 16  # ⭐ 

    MAGIC_NUMBER = 0xA1D10A7C

    PROTOCOL_VERSION = 2

    MSG_TYPE_AUDIO = 0x01

    MSG_TYPE_CONTROL = 0x02

    FLAG_FLOAT32 = 0x01

    # Agregar después de FLAG_FLOAT32

    FLAG_FLOAT32 = 0x01

    FLAG_RF_MODE = 0x80  # ⭐ NUEVA LÍNEA

  



    @staticmethod

    def create_audio_packet(audio_data, active_channels, sample_position, sequence=0, rf_mode=False):

        try:

            samples, total_channels = audio_data.shape

            

            # Calcular channel mask

            channel_mask = 0

            for ch in active_channels:

                if 0 <= ch < 48: 

                    channel_mask |= (1 << ch)

            

            # Verificar que los canales solicitados existen

            if max(active_channels) >= total_channels:

                logger.error(f"❌ Canal {max(active_channels)} no existe (total: {total_channels})")

                return None

            

            # Seleccionar solo los canales solicitados

            selected_data = audio_data[:, active_channels]

            

            # Intercalar datos

            interleaved = selected_data.flatten('C')

            audio_bytes = interleaved.astype('>f4').tobytes()

            

            # Payload: sample_position + channel_mask + audio_data

            payload = struct.pack('!QI', sample_position, channel_mask) + audio_bytes

            

            # ⭐ HEADER RF OPTIMIZADO

            flags = NativeAndroidProtocol.FLAG_FLOAT32

            if rf_mode:

                flags |= NativeAndroidProtocol.FLAG_RF_MODE

            

            # Header: magic(4) + type+flags(1+1) + timestamp(4) + payload_len(4) = 14

            # ⭐ REDUCIDO: magic(4) + flags_seq(2) + timestamp(4) + payload_len(4) = 14

            header = struct.pack('!IHHII', 

                NativeAndroidProtocol.MAGIC_NUMBER,

                NativeAndroidProtocol.PROTOCOL_VERSION,

                (NativeAndroidProtocol.MSG_TYPE_AUDIO << 8) | flags,

                int(time.time() * 1000) & 0xFFFFFFFF,

                len(payload))

            

            packet = header + payload

            

            logger.debug(f"📦 RF Paquete creado: {len(packet)} bytes, {len(active_channels)} canales, {samples} samples")

            return packet

            

        except Exception as e:

            logger.error(f"❌ Error creando paquete RF: {e}")

            import traceback

            traceback.print_exc()

            return None

    

    @staticmethod

    def create_control_packet(message_type, data=None, rf_mode=False):

        try:

            if data is None: 

                data = {}

            

            # ⭐ MENSAJES RF MÁS RÁPIDOS

            message = {

                'type': message_type, 

                'timestamp': int(time.time() * 1000), 

                'rf_mode': rf_mode,

                **data

            }

            

            message_bytes = json.dumps(message, separators=(',', ':')).encode('utf-8')

            

            flags = 0

            if rf_mode:

                flags |= NativeAndroidProtocol.FLAG_RF_MODE

            

            header = struct.pack('!IHHII', 

                NativeAndroidProtocol.MAGIC_NUMBER,

                NativeAndroidProtocol.PROTOCOL_VERSION,

                (NativeAndroidProtocol.MSG_TYPE_CONTROL << 8) | flags,

                int(time.time() * 1000) & 0xFFFFFFFF,

                len(message_bytes))

            

            packet = header + message_bytes

            

            return packet

            

        except Exception as e:

            logger.error(f"❌ Error creando paquete de control RF: {e}")

            return struct.pack('!IHHII', 

                NativeAndroidProtocol.MAGIC_NUMBER,

                NativeAndroidProtocol.PROTOCOL_VERSION,

                NativeAndroidProtocol.MSG_TYPE_CONTROL,

                0,

                0,

                0)