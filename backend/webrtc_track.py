"""
Custom Audio Track para WebRTC con multi-canal
"""

import asyncio
import numpy as np
import av
from av.audio.frame import AudioFrame
from av.audio.resampler import AudioResampler
from aiortc import MediaStreamTrack
import config_webrtc as config
import logging

logger = logging.getLogger(__name__)

class MultiChannelAudioTrack(MediaStreamTrack):
    """
    Track de audio que envía múltiples canales individuales via WebRTC
    Formato: Float32 planar -> Opus (estéreo por canal)
    """
    
    kind = "audio"
    
    def __init__(self, channel_manager, client_id, sample_rate=48000):
        super().__init__()
        self.channel_manager = channel_manager
        self.client_id = client_id
        self.target_sample_rate = sample_rate
        self.source_sample_rate = config.SAMPLE_RATE or 48000
        self.channels = 2  # WebRTC requiere estéreo
        self._running = True
        self._queue = asyncio.Queue(maxsize=10)
        
        # Resampler si es necesario
        if self.source_sample_rate != self.target_sample_rate:
            self.resampler = AudioResampler(
                format='fltp',
                layout='stereo',
                rate=self.target_sample_rate
            )
        else:
            self.resampler = None
        
        # Iniciar worker de audio
        self._task = asyncio.create_task(self._audio_worker())
        logger.info(f"AudioTrack creado para {client_id[:8]}...")
    
    def put_audio(self, audio_data):
        """Coloca datos de audio en la cola (llamado desde channel_manager)"""
        try:
            self._queue.put_nowait(audio_data)
        except asyncio.QueueFull:
            logger.warning(f"Queue llena para {self.client_id[:8]}..., descartando")
    
    async def _audio_worker(self):
        """Worker que convierte numpy arrays a AudioFrames"""
        while self._running:
            try:
                # Esperar datos de audio (async)
                audio_data = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=1.0
                )
                
                if audio_data is None:
                    continue
                
                # Crear AudioFrame desde numpy
                # audio_data shape: (samples, 2) para estéreo
                audio_frame = AudioFrame.from_ndarray(
                    audio_data.T,  # Transponer: (channels, samples)
                    format='fltp',
                    layout='stereo'
                )
                audio_frame.sample_rate = self.source_sample_rate
                audio_frame.time_base = f"1/{self.source_sample_rate}"
                
                # Resample si es necesario
                if self.resampler:
                    audio_frame = self.resampler.resample(audio_frame)
                
                # Almacenar para enviar en recv()
                self._current_frame = audio_frame
                
            except asyncio.TimeoutError:
                # Enviar silencio si no hay datos
                silence = np.zeros((config.BLOCKSIZE, 2), dtype=np.float32)
                audio_frame = AudioFrame.from_ndarray(
                    silence.T,
                    format='fltp',
                    layout='stereo'
                )
                audio_frame.sample_rate = self.target_sample_rate
                self._current_frame = audio_frame
                
            except Exception as e:
                logger.error(f"Error en audio worker: {e}")
                break
    
    async def recv(self):
        """Método requerido por MediaStreamTrack"""
        if not hasattr(self, '_current_frame'):
            # Frame inicial de silencio
            silence = np.zeros((config.BLOCKSIZE, 2), dtype=np.float32)
            frame = AudioFrame.from_ndarray(
                silence.T,
                format='fltp',
                layout='stereo'
            )
            frame.sample_rate = self.target_sample_rate
            frame.time_base = f"1/{self.target_sample_rate}"
            self._current_frame = frame
        
        # Clonar frame para evitar problemas de referencia
        frame = self._current_frame
        
        # Ajustar PTS (Presentation Timestamp)
        if not hasattr(self, '_timestamp'):
            self._timestamp = 0
        frame.pts = self._timestamp
        self._timestamp += len(frame)
        
        return frame
    
    async def stop(self):
        """Detener el track limpiamente"""
        self._running = False
        if hasattr(self, '_task'):
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"AudioTrack detenido para {self.client_id[:8]}...")