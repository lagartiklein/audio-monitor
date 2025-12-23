"""
WebRTC Server - Servidor principal para audio de ultra baja latencia
Latencia objetivo: 3-15ms
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Dict, Optional, List
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, MediaStreamTrack
from aiortc.rtcrtpsender import RTCRtpSender
import av
import numpy as np
import config_webrtc as config
import threading

logger = logging.getLogger(__name__)

class AudioStreamTrack(MediaStreamTrack):
    """
    Track de audio personalizado que envía múltiples canales
    Optimizado para ultra baja latencia
    """
    kind = "audio"
    
    def __init__(self, client_id, sample_rate=48000):
        super().__init__()
        self.client_id = client_id
        self.sample_rate = sample_rate
        self.channels = 2  # WebRTC requiere estéreo
        self._timestamp = 0
        self._running = True
        
        # Buffer para audio (thread-safe)
        self.audio_buffer = []
        self.buffer_lock = threading.Lock()
        self.buffer_max_size = 5  # ~100ms de buffer
        
        # Estadísticas
        self.frames_sent = 0
        self.start_time = time.time()
        self.last_audio_time = time.time()
        
        logger.info(f"AudioStreamTrack creado para {client_id[:8]}... @ {sample_rate}Hz")
    
    def put_audio(self, audio_data: np.ndarray):
        """Coloca datos de audio en el buffer (thread-safe)"""
        with self.buffer_lock:
            self.audio_buffer.append(audio_data)
            # Mantener buffer limitado para baja latencia
            if len(self.audio_buffer) > self.buffer_max_size:
                self.audio_buffer.pop(0)
            self.last_audio_time = time.time()
    
    async def recv(self):
        """Método requerido por MediaStreamTrack - envía audio al cliente"""
        try:
            # Obtener audio del buffer
            audio_data = None
            with self.buffer_lock:
                if self.audio_buffer:
                    audio_data = self.audio_buffer.pop(0)
            
            # Si no hay datos, enviar silencio
            if audio_data is None:
                # Verificar si ha pasado mucho tiempo sin audio
                if time.time() - self.last_audio_time > 1.0:
                    logger.warning(f"Sin audio para {self.client_id[:8]} por más de 1s")
                
                audio_data = np.zeros((config.BLOCKSIZE, 2), dtype=np.float32)
            
            # Convertir numpy array a AudioFrame
            # audio_data shape: (samples, 2) - estéreo
            audio_frame = av.AudioFrame.from_ndarray(
                audio_data.T,  # Transponer: (2, samples)
                format='fltp',
                layout='stereo'
            )
            audio_frame.sample_rate = self.sample_rate
            audio_frame.time_base = f"1/{self.sample_rate}"
            
            # Establecer timestamp
            audio_frame.pts = self._timestamp
            self._timestamp += len(audio_frame)
            
            self.frames_sent += 1
            
            # Log cada 100 frames (opcional)
            if config.VERBOSE and self.frames_sent % 100 == 0:
                elapsed = time.time() - self.start_time
                fps = self.frames_sent / elapsed
                logger.debug(f"Track {self.client_id[:8]}: {fps:.1f} fps")
            
            return audio_frame
            
        except Exception as e:
            logger.error(f"Error en recv() para {self.client_id[:8]}: {e}")
            # Frame de silencio como fallback
            silence = np.zeros((config.BLOCKSIZE, 2), dtype=np.float32)
            frame = av.AudioFrame.from_ndarray(
                silence.T,
                format='fltp',
                layout='stereo'
            )
            frame.sample_rate = self.sample_rate
            return frame
    
    def stop(self):
        """Detiene el track"""
        self._running = False
        logger.info(f"AudioStreamTrack detenido para {self.client_id[:8]}")

class WebRTCServer:
    """
    Servidor WebRTC que maneja conexiones P2P de audio
    """
    
    def __init__(self, audio_capture, channel_manager):
        self.audio_capture = audio_capture
        self.channel_manager = channel_manager
        self.pcs: Dict[str, RTCPeerConnection] = {}
        self.audio_tracks: Dict[str, AudioStreamTrack] = {}
        self.data_channels: Dict[str, any] = {}
        
        # Configuración ICE optimizada para audio
        self.rtc_config = RTCConfiguration(
            iceServers=[
                {'urls': server} for server in config.STUN_SERVERS
            ]
        )
        
        # Estado
        self.running = False
        self.audio_thread = None
        
        # Estadísticas
        self.stats = {
            'connections': 0,
            'total_frames_sent': 0,
            'active_since': time.time(),
            'errors': 0
        }
        
        # Buffer de audio compartido
        self.shared_audio_buffer = {}
        self.buffer_lock = threading.Lock()
        
        logger.info("WebRTC Server inicializado")
    
    def start(self):
        """Inicia el servidor WebRTC en un thread separado"""
        if self.running:
            return
        
        self.running = True
        self.audio_thread = threading.Thread(
            target=self._run_audio_distribution,
            daemon=True,
            name="WebRTC-Audio-Distributor"
        )
        self.audio_thread.start()
        
        logger.info("WebRTC Server iniciado")
    
    def stop(self):
        """Detiene el servidor WebRTC"""
        self.running = False
        
        # Detener todos los tracks
        for track in self.audio_tracks.values():
            track.stop()
        
        # Cerrar todas las conexiones
        for client_id in list(self.pcs.keys()):
            asyncio.run(self.close_connection(client_id))
        
        if self.audio_thread:
            self.audio_thread.join(timeout=2)
        
        logger.info("WebRTC Server detenido")
    
    def _run_audio_distribution(self):
        """Distribuye audio a todos los clientes WebRTC (en thread separado)"""
        logger.info("Audio distribution thread iniciado")
        
        while self.running:
            try:
                # Obtener audio del capturador
                audio_data = self.audio_capture.get_audio_data(timeout=0.05)
                
                if audio_data is None:
                    time.sleep(0.001)
                    continue
                
                # Distribuir a cada cliente WebRTC activo
                for client_id, track in list(self.audio_tracks.items()):
                    if client_id not in self.channel_manager.subscriptions:
                        continue
                    
                    # Obtener suscripción del cliente
                    subscription = self.channel_manager.subscriptions.get(client_id)
                    if not subscription:
                        continue
                    
                    channels = subscription.get('channels', [])
                    gains = subscription.get('gains', {})
                    
                    if not channels:
                        continue
                    
                    try:
                        # Mezclar canales a estéreo para WebRTC
                        stereo_audio = self._mix_to_stereo(audio_data, channels, gains)
                        
                        # Enviar al track del cliente
                        track.put_audio(stereo_audio)
                        
                        # Actualizar estadísticas
                        self.stats['total_frames_sent'] += 1
                        
                    except Exception as e:
                        logger.error(f"Error procesando audio para {client_id[:8]}: {e}")
                        self.stats['errors'] += 1
                
                # Pequeña pausa para no saturar la CPU
                time.sleep(0.001)
                
            except Exception as e:
                logger.error(f"Error en audio distribution: {e}")
                self.stats['errors'] += 1
                time.sleep(0.1)
        
        logger.info("Audio distribution thread detenido")
    
    def _mix_to_stereo(self, audio_data: np.ndarray, channels: List[int], gains: Dict[int, float]) -> np.ndarray:
        """Convierte múltiples canales mono a estéreo balanceado"""
        if audio_data.shape[0] == 0:
            return np.zeros((config.BLOCKSIZE, 2), dtype=np.float32)
        
        stereo = np.zeros((audio_data.shape[0], 2), dtype=np.float32)
        
        if not channels:
            return stereo
        
        # Distribuir canales en el campo estéreo
        for i, channel_idx in enumerate(channels):
            if channel_idx >= audio_data.shape[1]:
                continue
            
            # Obtener datos del canal
            channel_audio = audio_data[:, channel_idx].copy()
            
            # Aplicar ganancia
            gain = gains.get(channel_idx, 1.0)
            if gain != 1.0:
                channel_audio *= gain
            
            # Balancear en campo estéreo (panning automático)
            pan = i / max(len(channels) - 1, 1)  # 0 (izquierda) a 1 (derecha)
            
            # Izquierda
            stereo[:, 0] += channel_audio * (1.0 - pan) * 0.7
            # Derecha
            stereo[:, 1] += channel_audio * pan * 0.7
        
        # Normalizar para evitar clipping
        max_val = np.max(np.abs(stereo))
        if max_val > 1.0:
            stereo /= max_val
        
        return stereo
    
    async def handle_offer(self, client_id: str, offer_sdp: str) -> str:
        """Procesa una oferta SDP del cliente y devuelve respuesta"""
        try:
            # Crear PeerConnection
            pc = await self._create_peer_connection(client_id)
            
            # Establecer oferta remota
            await pc.setRemoteDescription(
                RTCSessionDescription(sdp=offer_sdp, type="offer")
            )
            
            # Crear respuesta
            answer = await pc.createAnswer()
            
            # Optimizar SDP para baja latencia de audio
            answer.sdp = self._optimize_sdp_for_low_latency(answer.sdp)
            
            await pc.setLocalDescription(answer)
            
            logger.info(f"Oferta WebRTC aceptada para {client_id[:8]}...")
            
            # Actualizar estadísticas
            self.stats['connections'] = len(self.pcs)
            
            return answer.sdp
            
        except Exception as e:
            logger.error(f"Error procesando oferta para {client_id[:8]}: {e}")
            await self.close_connection(client_id)
            raise
    
    def _optimize_sdp_for_low_latency(self, sdp: str) -> str:
        """Optimiza SDP para ultra baja latencia de audio"""
        lines = sdp.split('\n')
        optimized = []
        
        for line in lines:
            # Configurar Opus para baja latencia
            if 'opus/48000' in line:
                optimized.append(line)
                # Agregar parámetros de baja latencia
                optimized.append('a=ptime:20')      # 20ms packet time
                optimized.append('a=maxptime:60')   # Max 60ms
                optimized.append('a=minptime:10')   # Min 10ms
                if config.USE_FEC:
                    optimized.append('a=useinbandfec:1')
                if config.USE_DTX:
                    optimized.append('a=usedtx:1')
            
            # Deshabilitar video completamente
            elif 'm=video' in line:
                optimized.append('m=video 0 UDP/TLS/RTP/SAVPF 0\r')
            
            # Mantener otras líneas
            else:
                optimized.append(line)
        
        # Agregar atributos de baja latencia
        optimized.append('a=setup:actpass')
        optimized.append('a=mid:audio0')
        optimized.append('a=sendrecv')
        optimized.append('a=rtcp-mux')
        
        return '\n'.join(optimized)
    
    async def _create_peer_connection(self, client_id: str) -> RTCPeerConnection:
        """Crea una nueva PeerConnection para un cliente"""
        if client_id in self.pcs:
            await self.close_connection(client_id)
        
        # Crear PeerConnection
        pc = RTCPeerConnection(configuration=self.rtc_config)
        self.pcs[client_id] = pc
        
        # Forzar codec Opus para baja latencia
        self._force_opus_codec(pc)
        
        # Crear track de audio personalizado
        audio_track = AudioStreamTrack(client_id, sample_rate=48000)
        self.audio_tracks[client_id] = audio_track
        
        # Agregar track a la conexión
        pc.addTrack(audio_track)
        
        # Crear DataChannel para mensajes de control
        try:
            dc = pc.createDataChannel(config.DATA_CHANNEL_PROTOCOL, ordered=False, maxRetransmits=0)
            self.data_channels[client_id] = dc
            
            # Configurar DataChannel
            @dc.on("open")
            def on_open():
                logger.info(f"DataChannel abierto para {client_id[:8]}...")
                
                # Enviar configuración inicial
                config_msg = json.dumps({
                    'type': 'config',
                    'sampleRate': 48000,
                    'codec': 'opus',
                    'channels': self.channel_manager.num_channels,
                    'protocol': 'webrtc',
                    'clientId': client_id
                })
                dc.send(config_msg)
            
            @dc.on("message")
            def on_message(message):
                self._handle_data_message(client_id, message)
            
            @dc.on("close")
            def on_close():
                logger.info(f"DataChannel cerrado para {client_id[:8]}...")
            
            @dc.on("error")
            def on_error(error):
                logger.error(f"DataChannel error para {client_id[:8]}: {error}")
                
        except Exception as e:
            logger.warning(f"No se pudo crear DataChannel para {client_id[:8]}: {e}")
        
        # Configurar event handlers de la conexión
        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            state = pc.connectionState
            logger.info(f"Connection state {client_id[:8]}: {state}")
            
            if state in ["failed", "closed", "disconnected"]:
                await self.close_connection(client_id)
        
        @pc.on("iceconnectionstatechange")
        async def on_iceconnectionstatechange():
            state = pc.iceConnectionState
            logger.info(f"ICE state {client_id[:8]}: {state}")
        
        logger.info(f"PeerConnection creada para {client_id[:8]}...")
        return pc
    
    def _force_opus_codec(self, pc: RTCPeerConnection):
        """Fuerza el uso del codec Opus para baja latencia"""
        try:
            for transceiver in pc.getTransceivers():
                if transceiver.kind == "audio":
                    # Obtener capabilities y preferir Opus
                    codecs = RTCRtpSender.getCapabilities("audio").codecs
                    opus_codec = next(
                        (c for c in codecs if 'opus' in c.mimeType.lower()),
                        None
                    )
                    if opus_codec:
                        transceiver.setCodecPreferences([opus_codec])
        except Exception as e:
            logger.warning(f"No se pudo forzar codec Opus: {e}")
    
    def _handle_data_message(self, client_id: str, message: str):
        """Procesa mensajes del DataChannel"""
        try:
            data = json.loads(message)
            msg_type = data.get('type')
            
            if msg_type == 'subscribe':
                channels = data.get('channels', [])
                gains = data.get('gains', {})
                
                # Convertir gains keys a int
                gains = {int(k): float(v) for k, v in gains.items()}
                
                # Actualizar suscripción
                self.channel_manager.subscribe_client(client_id, channels, gains)
                logger.info(f"WebRTC cliente {client_id[:8]} suscrito a {len(channels)} canales")
                
            elif msg_type == 'update_gain':
                channel = int(data.get('channel'))
                gain = float(data.get('gain'))
                self.channel_manager.update_gain(client_id, channel, gain)
                
            elif msg_type == 'ping':
                # Responder ping para medir latencia
                dc = self.data_channels.get(client_id)
                if dc and dc.readyState == 'open':
                    response = json.dumps({
                        'type': 'pong',
                        'timestamp': data.get('timestamp'),
                        'server_time': time.time()
                    })
                    dc.send(response)
                    
        except json.JSONDecodeError:
            logger.warning(f"Mensaje no JSON de {client_id[:8]}: {message}")
        except Exception as e:
            logger.error(f"Error procesando mensaje DataChannel: {e}")
    
    async def add_ice_candidate(self, client_id: str, candidate_dict: dict):
        """Agrega un candidato ICE a la conexión"""
        if client_id in self.pcs:
            pc = self.pcs[client_id]
            try:
                await pc.addIceCandidate(candidate_dict)
            except Exception as e:
                logger.error(f"Error agregando ICE candidate para {client_id[:8]}: {e}")
    
    async def close_connection(self, client_id: str):
        """Cierra una conexión WebRTC limpiamente"""
        try:
            # Cerrar DataChannel
            if client_id in self.data_channels:
                dc = self.data_channels[client_id]
                if hasattr(dc, 'close'):
                    dc.close()
                del self.data_channels[client_id]
            
            # Detener y eliminar audio track
            if client_id in self.audio_tracks:
                self.audio_tracks[client_id].stop()
                del self.audio_tracks[client_id]
            
            # Cerrar PeerConnection
            if client_id in self.pcs:
                pc = self.pcs[client_id]
                await pc.close()
                del self.pcs[client_id]
            
            # Actualizar estadísticas
            self.stats['connections'] = len(self.pcs)
            
            logger.info(f"Conexión WebRTC cerrada para {client_id[:8]}...")
            
        except Exception as e:
            logger.error(f"Error cerrando conexión WebRTC para {client_id[:8]}: {e}")
    
    def get_stats(self) -> dict:
        """Devuelve estadísticas del servidor WebRTC"""
        uptime = time.time() - self.stats['active_since']
        
        return {
            **self.stats,
            'active_connections': len(self.pcs),
            'active_tracks': len(self.audio_tracks),
            'uptime': uptime,
            'avg_fps': self.stats['total_frames_sent'] / uptime if uptime > 0 else 0,
            'errors': self.stats['errors']
        }