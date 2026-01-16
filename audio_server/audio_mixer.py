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
            # ✅ MONO OUTPUT: Crear buffer mono de salida
            output_mono = np.zeros(num_samples, dtype=np.float32)
            # Mezclar canales activos en MONO (ignorar panorama)
            for ch in channels:
                if ch >= audio_data.shape[1]:
                    continue
                channel_data = audio_data[:, ch]
                gain = gains.get(ch, 10**(-24/20)) * master_gain  # Default -24 dB
                np.add(output_mono, channel_data * gain, out=output_mono)
            np.clip(output_mono, -1.0, 1.0, out=output_mono)
            import config
            if getattr(config, 'USE_INT16_ENCODING', False):
                np.multiply(output_mono, 32767, out=output_mono)
                audio_int16 = output_mono.astype(np.int16)
                audio_bytes = audio_int16.tobytes()
            else:
                audio_bytes = output_mono.astype(np.float32).tobytes()
            
            # Debouncing: no enviar más de una vez cada 50ms
            current_time = time.time()
            if current_time - self.last_broadcast_time >= self.min_broadcast_interval:
                self.broadcast_callback(
                    audio_bytes,
                    self.sample_rate,
                    1,  # ✅ MONO (APK lo convertirá a estéreo)
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
