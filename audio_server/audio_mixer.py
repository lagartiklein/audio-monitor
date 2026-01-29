import numpy as np
import logging
import time

from threading import Lock

# === WIDENING STEREO (Haas effect) ===


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
        if not self.broadcast_callback or not audio_data.size:
            return
        # Obtener suscripción del maestro
        subscription = channel_manager.get_client_subscription(master_client_id)
        try:
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
            # Mezclar canales activos en ESTÉREO
            output_stereo = np.zeros((num_samples, 2), dtype=np.float32)
            for ch in channels:
                if ch >= audio_data.shape[1]:
                    continue
                channel_data = audio_data[:, ch]
                gain = gains.get(ch, 1.0) * master_gain
                gain = min(gain, 1.0)  # Limitar a rango normal, sin amplificación
                pan = pans.get(ch, 0.0)
                # Pan law: -1.0 = L, 0.0 = center, 1.0 = R
                left = np.cos((pan + 1) * np.pi / 4)
                right = np.sin((pan + 1) * np.pi / 4)
                ch_l = channel_data * gain * left
                ch_r = channel_data * gain * right
                output_stereo[:, 0] += ch_l
                output_stereo[:, 1] += ch_r
            audio_bytes = output_stereo.astype(np.float32).tobytes()
            num_channels_out = 2
            # Debouncing: no enviar más de una vez cada 50ms
            current_time = time.time()
            if current_time - self.last_broadcast_time >= self.min_broadcast_interval:
                self.broadcast_callback(
                    audio_bytes,
                    self.sample_rate,
                    num_channels_out,
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
