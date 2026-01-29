# audio_compression.py
# ✅ FIXED: Sin normalización extra que causaba saturación

import numpy as np
import logging
import struct
import config

logger = logging.getLogger(__name__)

try:
    import opuslib
    OPUS_AVAILABLE = True
    logger.info("[AudioCompressor] Opus library disponible")
except Exception:
    OPUS_AVAILABLE = False
    logger.warning("[AudioCompressor] Opus library no disponible")


class AudioCompressor:
    def __init__(self, sample_rate=48000, channels=1, bitrate=32000, use_opus=True):
        self.sample_rate = sample_rate
        self.channels = channels
        self.bitrate = bitrate
        self._max_compressed_size = 2_000_000
        
        self.headroom_factor = 1.0
        
        if use_opus and OPUS_AVAILABLE:
            try:
                self.opus_encoder = opuslib.Encoder(sample_rate, channels, 'voip')  # Cambiado a 'voip' para ultra baja latencia
                self.opus_decoder = opuslib.Decoder(sample_rate, channels)
                self.opus_encoder.bitrate = bitrate
                self.opus_encoder.ctl(opuslib.CTL_SET_COMPLEXITY, 0)  # Complexity mínima para menos latencia
                self.compression_method = "opus"
                logger.info(f"[AudioCompressor] Opus (VoIP mode): {channels}ch, {sample_rate}Hz, {bitrate}bps, complexity=0")
            except Exception as e:
                logger.error(f"[AudioCompressor] Error Opus: {e}")
                self.compression_method = "none"
        else:
            self.compression_method = "none"
            logger.info(f"[AudioCompressor] Sin compresión: {channels}ch")

    def compress(self, audio_data: np.ndarray) -> bytes:
        if self.compression_method == "opus":
            return self._compress_opus(audio_data)
        else:
            return self._compress_none(audio_data)

    def decompress(self, compressed_data: bytes) -> np.ndarray:
        if self.compression_method == "opus":
            return self._decompress_opus(compressed_data)
        else:
            return self._decompress_none(compressed_data)

    def _compress_none(self, audio_data: np.ndarray) -> bytes:
        """Sin compresión, solo normalización a int16 - OPTIMIZADO: evitar copia si posible"""
        try:
            # ✅ OPTIMIZACIÓN: Evitar copia si ya es float32
            if audio_data.dtype == np.float32:
                audio = audio_data  # No copiar
            else:
                audio = audio_data.astype(np.float32)  # Solo convertir tipo
            
            # Limitar sin normalización (in-place)
            np.clip(audio, -1.0, 1.0, out=audio)
            
            # Convertir a int16
            pcm_int16 = np.clip(audio * 32768.0, -32768, 32767).astype(np.int16)
            pcm_data = pcm_int16.tobytes()
            
            if len(pcm_data) > self._max_compressed_size:
                logger.warning(f"[CompressNone] Tamaño excede límite: {len(pcm_data)}")
                return b''
            
            header = struct.pack('>I', len(pcm_data))
            return header + pcm_data
            
        except Exception as e:
            logger.error(f"[CompressNone] Error: {e}")
            return b''

    def _decompress_none(self, compressed_data: bytes) -> np.ndarray:
        try:
            if len(compressed_data) < 4:
                raise ValueError("Header incompleto")
            
            original_size = struct.unpack('>I', compressed_data[:4])[0]
            
            if original_size > self._max_compressed_size or original_size <= 0:
                raise ValueError(f"Tamaño inválido: {original_size}")
            
            pcm_data = compressed_data[4:]
            
            if len(pcm_data) != original_size:
                logger.warning(f"Tamaño mismatch: {len(pcm_data)} vs {original_size}")
            
            audio_int16 = np.frombuffer(pcm_data, dtype=np.int16).copy()
            return audio_int16.astype(np.float32) / 32768.0
            
        except Exception as e:
            logger.error(f"[DecompressNone] Error: {e}")
            return np.zeros(512, dtype=np.float32)

    def _compress_opus(self, audio_data: np.ndarray) -> bytes:
        """Comprimir con Opus sin normalización extra - OPTIMIZADO: evitar copia si posible"""
        try:
            # ✅ OPTIMIZACIÓN: Evitar copia si ya es float32 y no necesita modificación
            if audio_data.dtype == np.float32:
                audio = audio_data  # No copiar
            else:
                audio = audio_data.astype(np.float32)  # Solo convertir tipo si necesario
            
            # Solo limitar (in-place si posible)
            np.clip(audio, -1.0, 1.0, out=audio)
            
            # Convertir a int16 para Opus
            pcm_int16 = np.clip(audio * 32768.0, -32768, 32767).astype(np.int16)
            
            frame_size = len(pcm_int16) // self.channels
            compressed = self.opus_encoder.encode(pcm_int16.tobytes(), frame_size)
            
            if len(compressed) > self._max_compressed_size:
                logger.warning(f"[Opus] Datos exceden límite: {len(compressed)}")
                return b''
            
            header = struct.pack('>I B H', len(compressed), 1, frame_size)
            return header + compressed
            
        except Exception as e:
            logger.error(f"[CompressOpus] Error: {e}")
            return b''

    def _decompress_opus(self, compressed_data: bytes) -> np.ndarray:
        try:
            if len(compressed_data) < 7:
                raise ValueError("Header incompleto")
            
            compressed_size, method, frame_size = struct.unpack('>I B H', compressed_data[:7])
            
            if method != 1:
                raise ValueError(f"Método no soportado: {method}")
            
            opus_data = compressed_data[7:]
            
            if len(opus_data) != compressed_size:
                logger.warning(f"Tamaño mismatch: {len(opus_data)} vs {compressed_size}")
            
            pcm_data = self.opus_decoder.decode(opus_data, frame_size)
            audio_int16 = np.frombuffer(pcm_data, dtype=np.int16).copy()
            
            return audio_int16.astype(np.float32) / 32768.0
            
        except Exception as e:
            logger.error(f"[DecompressOpus] Error: {e}")
            return np.zeros(960 * self.channels, dtype=np.float32)


_audio_compressor = None
_audio_compressor_params = {}


def get_audio_compressor(sample_rate=48000, channels=1, bitrate=32000, use_opus=True) -> AudioCompressor:
    global _audio_compressor, _audio_compressor_params
    
    current_params = {
        'sample_rate': sample_rate,
        'channels': channels,
        'bitrate': bitrate,
        'use_opus': use_opus
    }
    
    if _audio_compressor is None or _audio_compressor_params != current_params:
        _audio_compressor = AudioCompressor(sample_rate, channels, bitrate, use_opus)
        _audio_compressor_params = current_params
        logger.info(f"[get_audio_compressor] Parámetros: {current_params}")
    
    return _audio_compressor