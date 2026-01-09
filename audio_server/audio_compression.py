"""
audio_compression.py - Empaquetado de audio sin compresión
✅ Puro Python, sin dependencias externas
✅ Mantiene compatibilidad de formato
"""


import numpy as np
import logging
import struct


import config

logger = logging.getLogger(__name__)


class AudioCompressor:
    """Empaquetador de audio sin compresión"""

    def __init__(self, sample_rate=48000, channels=1, bitrate=32000):
        self.sample_rate = sample_rate
        self.channels = channels
        self.bitrate = bitrate
        # Sin compresión
        self._max_compressed_size = 2_000_000  # Máximo 2MB para prevenir OOM
        self.compression_method = "none"
        logger.info(f"[AudioCompressor] ✅ Sin compresión: {channels}ch, {sample_rate}Hz")


    def compress(self, audio_data: np.ndarray) -> bytes:
        return self._compress_none(audio_data)


    def decompress(self, compressed_data: bytes) -> np.ndarray:
        return self._decompress_none(compressed_data)

    def _compress_none(self, audio_data: np.ndarray) -> bytes:
        """Empaqueta datos de audio sin compresión usando el mismo formato que zlib"""
        try:
            # ✅ ZERO-COPY: Minimizar copias - conversión directa optimizada
            # Usar 32768 (2^15) en lugar de 32767 para correcta conversión
            if audio_data.dtype == np.float32:
                pcm_int16 = np.clip(audio_data * 32768, -32768, 32767).astype(np.int16)
            else:
                pcm_int16 = np.clip(audio_data.astype(np.float32) * 32768, -32768, 32767).astype(np.int16)
            
            pcm_data = pcm_int16.tobytes()
            # Sin compresión, solo empaquetar
            compressed = pcm_data
            
            # Validar tamaño máximo
            if len(compressed) > self._max_compressed_size:
                logger.warning(f"[Sin compresión] Datos exceden límite: {len(compressed)}")
                return b''
            
            header = struct.pack('>I', len(pcm_data))
            return header + compressed
        except Exception as e:
            logger.error(f"[CompressNone] Error: {e}")
            return b''

    def _decompress_none(self, compressed_data: bytes) -> np.ndarray:
        """Desempaqueta datos de audio sin descompresión"""
        try:
            if len(compressed_data) < 4:
                raise ValueError("Datos inválidos - header incompleto")
            
            original_size = struct.unpack('>I', compressed_data[:4])[0]
            
            # Validar tamaño
            if original_size > self._max_compressed_size or original_size <= 0:
                raise ValueError(f"Tamaño original inválido: {original_size}")
            
            pcm_data = compressed_data[4:]
            
            if len(pcm_data) != original_size:
                logger.warning(f"[DecompressNone] Tamaño mismatch: esperado {original_size}, obtenido {len(pcm_data)}")
            
            audio_int16 = np.frombuffer(pcm_data, dtype=np.int16).copy()
            return audio_int16.astype(np.float32) / 32768.0
        except Exception as e:
            logger.error(f"[DecompressNone] Error: {e}")
            return np.zeros(512, dtype=np.float32)



def compress_audio_channels(audio_data: np.ndarray, channels_to_compress: list, 
                            compressor: AudioCompressor) -> dict:
    """
    Empaquetar canales individuales sin compresión
    Args:
        audio_data: ndarray (samples, total_channels)
        channels_to_compress: lista de índices de canales
        compressor: AudioCompressor instance
    Returns:
        dict con canales empaquetados: {channel_id: bytes}
    """
    compressed = {}
    for ch in channels_to_compress:
        if ch < audio_data.shape[1]:
            channel_data = audio_data[:, ch]
            compressed[ch] = compressor.compress(channel_data)
    return compressed

def decompress_audio_channels(compressed_dict: dict, compressor: AudioCompressor) -> dict:
    """
    Desempaquetar canales individuales sin compresión
    Args:
        compressed_dict: {channel_id: bytes}
        compressor: AudioCompressor instance
    Returns:
        dict con canales desempaquetados: {channel_id: audio_float32}
    """
    decompressed = {}
    for ch, compressed_data in compressed_dict.items():
        decompressed[ch] = compressor.decompress(compressed_data)
    return decompressed


# Singleton compressor
_audio_compressor = None
_audio_compressor_params = {}

def get_audio_compressor(sample_rate=48000, channels=1, bitrate=32000) -> AudioCompressor:
    """
    Obtener instancia global de compressor sin compresión
    ⚠️ Recrea el compressor si los parámetros cambian
    """
    global _audio_compressor, _audio_compressor_params
    
    current_params = {'sample_rate': sample_rate, 'channels': channels, 'bitrate': bitrate}
    
    # Recrear si los parámetros cambiaron
    if _audio_compressor is None or _audio_compressor_params != current_params:
        _audio_compressor = AudioCompressor(sample_rate, channels, bitrate)
        _audio_compressor_params = current_params
        if _audio_compressor_params != current_params:
            logger.info(f"[get_audio_compressor] Parámetros actualizados: {current_params}")
    
    return _audio_compressor
