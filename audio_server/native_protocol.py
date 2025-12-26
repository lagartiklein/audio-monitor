import struct, time, numpy as np, json, logging
logger = logging.getLogger(__name__)

class NativeAndroidProtocol:
    HEADER_SIZE = 20
    MAGIC_NUMBER = 0xA1D10A7C
    PROTOCOL_VERSION = 2
    MSG_TYPE_AUDIO = 0x01
    MSG_TYPE_CONTROL = 0x02
    FLAG_FLOAT32 = 0x01

    @staticmethod
    def create_audio_packet(audio_data, active_channels, sample_position, sequence=0):
        samples, total_channels = audio_data.shape
        channel_mask = 0
        for ch in active_channels:
            if 0 <= ch < 32: channel_mask |= (1 << ch)
        
        selected_data = audio_data[:, active_channels]
        interleaved = selected_data.flatten('C')
        audio_bytes = interleaved.astype(np.float32).tobytes()
        payload = struct.pack('!QI', sample_position, channel_mask) + audio_bytes
        header = struct.pack('!IHBBIII', NativeAndroidProtocol.MAGIC_NUMBER,
                           NativeAndroidProtocol.PROTOCOL_VERSION,
                           NativeAndroidProtocol.MSG_TYPE_AUDIO,
                           NativeAndroidProtocol.FLAG_FLOAT32,
                           sample_position & 0xFFFFFFFF, sequence, len(payload))
        return header + payload
    
    @staticmethod
    def create_control_packet(message_type, data=None):
        if data is None: data = {}
        message = {'type': message_type, 'timestamp': int(time.time() * 1000), **data}
        message_bytes = json.dumps(message, separators=(',', ':')).encode('utf-8')
        header = struct.pack('!IHBBIII', NativeAndroidProtocol.MAGIC_NUMBER,
                           NativeAndroidProtocol.PROTOCOL_VERSION,  # CORREGIDO: era PROCOL_VERSION
                           NativeAndroidProtocol.MSG_TYPE_CONTROL, 0,
                           int(time.time() * 1000) & 0xFFFFFFFF, 0, len(message_bytes))
        return header + message_bytes