# audio_mixer.py
# ✅ NUEVO: Audio Mixer para cliente maestro (streaming en tiempo real)

import numpy as np
import logging
import time
from threading import Lock

logger = logging.getLogger(__name__)

_audio_mixer_instance = None
_mixer_lock = Lock()


class AudioMixer:
    """
    ✅ NUEVO: Procesa audio de canales activos y lo envía al cliente maestro
    
    Responsabilidades:
    - Mezclar canales activos con ganancia/pan individual
    - Detectar cambios en la mezcla
    - Enviar audio a listeners (broadcast_callback)
    """
    
    def __init__(self, sample_rate=48000, buffer_size=2048):
        self.sample_rate = sample_rate
        self.buffer_size = buffer_size
        self.broadcast_callback = None
        self.last_broadcast_time = 0
        self.min_broadcast_interval = 0.05  # 50ms para debouncing
        
        logger.info(f"[AudioMixer] ✅ Inicializado: {sample_rate}Hz, {buffer_size} samples")
    
    def set_audio_callback(self, callback):
        """Registrar callback para envío de audio"""
        self.broadcast_callback = callback
        logger.debug("[AudioMixer] 📡 Callback de audio registrado")
    
    def process_and_broadcast(self, audio_data, channel_manager, master_client_id):
        """
        ✅ Procesar audio de canales activos y enviar al maestro
        
        Args:
            audio_data: ndarray de forma (samples, channels)
            channel_manager: ChannelManager instance
            master_client_id: ID del cliente maestro
        """
        try:
            if not self.broadcast_callback or not audio_data.size:
                return
            
            # Obtener suscripción del maestro
            subscription = channel_manager.get_client_subscription(master_client_id)
            if not subscription:
                return
            
            channels = subscription.get('channels', [])
            if not channels:
                return
            
            gains = subscription.get('gains', {})
            pans = subscription.get('pans', {})
            master_gain = subscription.get('master_gain', 1.0)
            
            # Convertir audio a float32 si es necesario
            if audio_data.dtype != np.float32:
                audio_data = audio_data.astype(np.float32)
            
            num_samples = audio_data.shape[0]
            
            # Crear buffer stereo de salida
            output_L = np.zeros(num_samples, dtype=np.float32)
            output_R = np.zeros(num_samples, dtype=np.float32)
            
            # Mezclar canales activos
            for ch in channels:
                if ch >= audio_data.shape[1]:
                    continue
                
                # ✅ ZERO-COPY: Sin .copy() - acceso directo con slice
                channel_data = audio_data[:, ch]
                
                # Aplicar ganancia individual + panorama
                gain = gains.get(ch, 1.0) * master_gain
                pan = pans.get(ch, 0.0)  # -1.0 = left, 1.0 = right
                pan_normalized = (pan + 1.0) / 2.0  # 0.0 a 1.0
                gain_L = np.cos(pan_normalized * np.pi / 2) * gain
                gain_R = np.sin(pan_normalized * np.pi / 2) * gain
                
                # ✅ ZERO-COPY: Operación directa sin buffers intermedios
                np.add(output_L, channel_data * gain_L, out=output_L)
                np.add(output_R, channel_data * gain_R, out=output_R)
            
            # Limitar para evitar clipping (in-place)
            np.clip(output_L, -1.0, 1.0, out=output_L)
            np.clip(output_R, -1.0, 1.0, out=output_R)
            
            # ✅ ZERO-COPY: Intercalar y convertir en un solo paso
            stereo_data = np.empty(num_samples * 2, dtype=np.float32)
            stereo_data[0::2] = output_L
            stereo_data[1::2] = output_R
            
            # ✅ ZERO-COPY: Operación in-place para conversión
            np.multiply(stereo_data, 32767, out=stereo_data)
            audio_int16 = stereo_data.astype(np.int16)  # Conversión directa
            audio_bytes = audio_int16.tobytes()
            
            # Debouncing: no enviar más de una vez cada 50ms
            current_time = time.time()
            if current_time - self.last_broadcast_time >= self.min_broadcast_interval:
                self.broadcast_callback(
                    audio_bytes,
                    self.sample_rate,
                    2,  # stereo
                    master_client_id
                )
                self.last_broadcast_time = current_time
        
        except Exception as e:
            logger.error(f"[AudioMixer] ❌ Error procesando audio: {e}")


def init_audio_mixer(sample_rate=48000, buffer_size=2048):
    """Inicializar instancia única del mixer"""
    global _audio_mixer_instance
    
    with _mixer_lock:
        if _audio_mixer_instance is None:
            _audio_mixer_instance = AudioMixer(sample_rate, buffer_size)
        return _audio_mixer_instance


def get_audio_mixer():
    """Obtener instancia del mixer"""
    global _audio_mixer_instance
    return _audio_mixer_instance
