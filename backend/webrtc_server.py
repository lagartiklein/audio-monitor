"""
WebRTC Server - Versión MEJORADA (combina vieja + nueva)
"""

import asyncio
import json
import logging
import time
import struct
from typing import Dict, Optional, Set
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer
from aiortc import MediaStreamTrack
from aiortc.contrib.media import MediaBlackhole
import numpy as np
import av
from av import AudioFrame
import config
import threading
from collections import deque

logger = logging.getLogger(__name__)

class AudioStreamTrack(MediaStreamTrack):
    """
    Track de audio que genera frames desde los datos capturados
    """
    kind = "audio"
    
    def __init__(self, audio_capture, channel_manager, client_id):
        super().__init__()
        self.audio_capture = audio_capture
        self.channel_manager = channel_manager
        self.client_id = client_id
        self.sample_rate = config.SAMPLE_RATE
        self.channels = 2  # Estéreo para WebRTC
        self._queue = asyncio.Queue(maxsize=10)
        self._running = True
        self._timestamp = 0
        
        logger.info(f"AudioStreamTrack creado para {client_id[:8]}...")
    
    async def recv(self):
        """Genera frames de audio para WebRTC"""
        try:
            # Obtener audio de la cola con timeout
            audio_data = await asyncio.wait_for(
                self._queue.get(), 
                timeout=0.1
            )
            
            if audio_data is None or len(audio_data) == 0:
                # Generar silencio
                if config.VERBOSE:
                    print(f"[WebRTC Track] {self.client_id[:8]} recibiendo silencio (sin datos)")
                audio_data = np.zeros((config.BLOCKSIZE, 2), dtype=np.float32)
            
            # Asegurar que tengamos estéreo
            if audio_data.shape[1] == 1:
                # Mono -> Estéreo (duplicar canal)
                audio_data = np.repeat(audio_data, 2, axis=1)
            elif audio_data.shape[1] > 2:
                # Multi-canal -> Estéreo (mezclar)
                audio_data = audio_data[:, :2]
            
            # Crear frame de audio
            frame = AudioFrame.from_ndarray(
                audio_data.T,  # Transponer a (channels, samples)
                format='fltp',
                layout='stereo'
            )
            frame.sample_rate = self.sample_rate
            frame.pts = self._timestamp
            frame.time_base = f"1/{self.sample_rate}"
            
            # Incrementar timestamp
            self._timestamp += len(audio_data)
            
            return frame
            
        except asyncio.TimeoutError:
            # Timeout - enviar silencio
            if config.VERBOSE:
                print(f"[WebRTC Track] {self.client_id[:8]} timeout en recv()")
            silence = np.zeros((config.BLOCKSIZE, 2), dtype=np.float32)
            frame = AudioFrame.from_ndarray(
                silence.T,
                format='fltp',
                layout='stereo'
            )
            frame.sample_rate = self.sample_rate
            frame.pts = self._timestamp
            frame.time_base = f"1/{self.sample_rate}"
            
            self._timestamp += len(silence)
            return frame
    
    def put_audio(self, audio_data):
        """Pone datos de audio en la cola - VERSIÓN MEJORADA"""
        try:
            # Usar put_nowait para evitar bloqueos
            self._queue.put_nowait(audio_data)
            if config.VERBOSE and self._queue.qsize() % 50 == 0:
                print(f"[WebRTC Track] {self.client_id[:8]} queue size: {self._queue.qsize()}")
        except asyncio.QueueFull:
            # Descartar el buffer más viejo
            try:
                self._queue.get_nowait()
                if config.VERBOSE:
                    print(f"[WebRTC Track] {self.client_id[:8]} queue llena, descartando viejo")
                self._queue.put_nowait(audio_data)
            except asyncio.QueueEmpty:
                pass
        except Exception as e:
            if config.VERBOSE:
                print(f"[WebRTC Track] Error en put_audio: {e}")
    
    async def stop(self):
        """Detiene el track"""
        self._running = False
        logger.info(f"AudioStreamTrack detenido para {self.client_id[:8]}...")


class WebRTCServer:
    """
    Servidor WebRTC MEJORADO - Combina estabilidad vieja + mejoras nuevas
    """
    
    def __init__(self, audio_capture, channel_manager):
        self.audio_capture = audio_capture
        self.channel_manager = channel_manager
        self.pcs: Dict[str, RTCPeerConnection] = {}
        self.audio_tracks: Dict[str, AudioStreamTrack] = {}
        
        # Configuración ICE
        self.rtc_config = RTCConfiguration(
            iceServers=[
                RTCIceServer(urls=server)
                for server in config.STUN_SERVERS
            ]
        )
        
        # Estado
        self.running = False
        self.audio_thread = None
        self.loop = None  # ← AÑADIDO: Para manejo de loops
        
        # Estadísticas
        self.stats = {
            'connections': 0,
            'total_packets_sent': 0,
            'total_bytes_sent': 0,
            'active_since': time.time(),
            'errors': 0
        }
        
        logger.info("WebRTC Server MEJORADO inicializado")
    
    def start(self):
        """Inicia el servidor WebRTC"""
        if self.running:
            return
        
        self.running = True
        
        # Obtener loop para operaciones asíncronas
        try:
            self.loop = asyncio.get_event_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
        
        self.audio_thread = threading.Thread(
            target=self._run_audio_distribution,
            daemon=True,
            name="WebRTC-Audio-Distribution"
        )
        self.audio_thread.start()
        
        logger.info("WebRTC Server iniciado")
    
    def stop(self):
        """Detiene el servidor WebRTC - MEJORADO"""
        self.running = False
        
        # Cerrar todas las conexiones usando el loop si está disponible
        if self.loop and self.loop.is_running():
            try:
                for client_id in list(self.pcs.keys()):
                    asyncio.run_coroutine_threadsafe(
                        self.close_connection(client_id),
                        self.loop
                    )
            except Exception as e:
                logger.error(f"Error cerrando conexiones: {e}")
        else:
            # Método de respaldo
            for client_id in list(self.pcs.keys()):
                try:
                    asyncio.run(self.close_connection(client_id))
                except Exception as e:
                    logger.error(f"Error cerrando conexión {client_id[:8]}: {e}")
        
        # Esperar thread de audio
        if self.audio_thread:
            self.audio_thread.join(timeout=2)
        
        logger.info("WebRTC Server detenido")
    
    # ============================================
    # MÉTODO _run_audio_distribution MODIFICADO CON LOGS
    # ============================================
    def _run_audio_distribution(self):
        """Distribuye audio a todos los tracks WebRTC - CON LOGS MEJORADOS"""
        print("[WebRTC] 🔄 Audio distribution iniciado")
        
        frame_duration = config.BLOCKSIZE / config.SAMPLE_RATE
        next_frame_time = time.time()
        
        # Variables para logs
        frame_counter = 0
        status_interval = 100  # Cada ~2 segundos
        
        while self.running:
            try:
                current_time = time.time()
                
                # Timing preciso
                if current_time < next_frame_time:
                    sleep_time = next_frame_time - current_time
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                
                # Obtener audio del capturador
                audio_data = self.audio_capture.get_audio_data(timeout=0.05)
                
                if audio_data is None:
                    continue
                
                frame_counter += 1
                
                # ✅ LOGS DE ESTADO PERIÓDICOS
                if frame_counter % status_interval == 0:
                    print(f"\n[WebRTC Dist] 📊 Frame {frame_counter}")
                    print(f"  Audio shape: {audio_data.shape}")
                    print(f"  Tracks activos: {len(self.audio_tracks)}")
                    print(f"  PC connections: {len(self.pcs)}")
                    print(f"  Subscripciones totales: {len(self.channel_manager.subscriptions)}")
                    
                    # Mostrar estado de cada cliente
                    for client_id in list(self.audio_tracks.keys()):
                        sub = self.channel_manager.subscriptions.get(client_id)
                        if sub:
                            channels = sub.get('channels', [])
                            print(f"    {client_id[:8]}: {len(channels)} canales")
                        else:
                            print(f"    {client_id[:8]}: ❌ SIN SUB")
                
                # Distribuir a cada track activo
                for client_id, track in list(self.audio_tracks.items()):
                    
                    # ✅ VERIFICAR SI EL CLIENTE TIENE SUSCRIPCIÓN
                    if client_id not in self.channel_manager.subscriptions:
                        # ⚠️ DEBUG importante
                        if frame_counter % 50 == 0:  # Cada ~1 segundo
                            print(f"[WebRTC Dist] ⚠️ {client_id[:8]} sin suscripción")
                            print(f"    Subscripciones disponibles: {list(self.channel_manager.subscriptions.keys())}")
                        continue
                    
                    subscription = self.channel_manager.subscriptions.get(client_id)
                    if not subscription:
                        if frame_counter % 50 == 0:
                            print(f"[WebRTC Dist] ❌ Subscription vacía para {client_id[:8]}")
                        continue
                    
                    channels = subscription.get('channels', [])
                    gains = subscription.get('gains', {})
                    
                    if not channels:
                        if frame_counter % status_interval == 0:
                            print(f"[WebRTC Dist] ⚠️ {client_id[:8]} sin canales activos")
                        continue
                    
                    try:
                        # Procesar canales y crear mezcla estéreo
                        mixed_audio = self._mix_channels(
                            audio_data, 
                            channels, 
                            gains
                        )
                        
                        # Enviar al track
                        track.put_audio(mixed_audio)
                        
                        # ✅ LOG DE ÉXITO (solo periódicamente)
                        if frame_counter % status_interval == 0:
                            print(f"[WebRTC Dist] ✅ {client_id[:8]}: {len(channels)} canales, {mixed_audio.nbytes} bytes")
                        
                        # Actualizar estadísticas
                        self.stats['total_packets_sent'] += 1
                        self.stats['total_bytes_sent'] += mixed_audio.nbytes
                        
                    except Exception as e:
                        logger.error(f"Error enviando audio a {client_id[:8]}: {e}")
                        self.stats['errors'] += 1
                
                # Calcular próximo frame time
                next_frame_time += frame_duration
                
                # Drift correction
                if current_time > next_frame_time + frame_duration:
                    next_frame_time = current_time
                
            except Exception as e:
                logger.error(f"Error en audio distribution: {e}")
                self.stats['errors'] += 1
                time.sleep(0.1)
        
        print("[WebRTC] Audio distribution detenido")
    
    def _mix_channels(self, audio_data, channels, gains):
        """Mezcla múltiples canales en estéreo"""
        if len(channels) == 0:
            return np.zeros((audio_data.shape[0], 2), dtype=np.float32)
        
        # Inicializar salida estéreo
        mixed = np.zeros((audio_data.shape[0], 2), dtype=np.float32)
        
        for i, channel_idx in enumerate(channels):
            if channel_idx >= audio_data.shape[1]:
                continue
            
            # Extraer canal
            channel_audio = audio_data[:, channel_idx]
            
            # Aplicar ganancia
            gain = gains.get(channel_idx, 1.0)
            if gain != 1.0:
                channel_audio = channel_audio * gain
            
            # Panorama simple: canales pares -> izquierda, impares -> derecha
            if i % 2 == 0:
                mixed[:, 0] += channel_audio * 0.7  # Izquierda
                mixed[:, 1] += channel_audio * 0.3  # Derecha (menos)
            else:
                mixed[:, 0] += channel_audio * 0.3  # Izquierda (menos)
                mixed[:, 1] += channel_audio * 0.7  # Derecha
        
        # Normalizar para evitar clipping
        max_val = np.abs(mixed).max()
        if max_val > 1.0:
            mixed = mixed / max_val
        
        # Soft clipping
        mixed = np.clip(mixed, -1.0, 1.0)
        
        return mixed.astype(np.float32)
    
    async def handle_offer(self, client_id: str, offer_sdp: str) -> str:
        """
        Procesa una oferta SDP del cliente y devuelve respuesta
        """
        try:
            # Crear PeerConnection
            pc = RTCPeerConnection(configuration=self.rtc_config)
            self.pcs[client_id] = pc
            
            # Crear y agregar audio track
            audio_track = AudioStreamTrack(
                self.audio_capture,
                self.channel_manager,
                client_id
            )
            self.audio_tracks[client_id] = audio_track
            
            # Agregar track a la PeerConnection
            pc.addTrack(audio_track)
            print(f"[WebRTC] ✅ Audio track agregado para {client_id[:8]}...")
            
            # Configurar event handlers
            @pc.on("connectionstatechange")
            async def on_connectionstatechange():
                state = pc.connectionState
                print(f"[WebRTC] Connection state {client_id[:8]}: {state}")
                
                if state in ["failed", "closed", "disconnected"]:
                    await self.close_connection(client_id)
            
            @pc.on("iceconnectionstatechange")
            async def on_iceconnectionstatechange():
                state = pc.iceConnectionState
                print(f"[WebRTC] ICE state {client_id[:8]}: {state}")
            
            # OPCIONAL: Configurar DataChannel para mensajes de control
            try:
                channel = pc.createDataChannel("audio-control")
                
                @channel.on("message")
                def on_message(message):
                    try:
                        data = json.loads(message)
                        print(f"[WebRTC DataChannel] {client_id[:8]}: {data.get('type')}")
                        
                        if data.get('type') == 'subscribe':
                            channels = data.get('channels', [])
                            gains = data.get('gains', {})
                            
                            # Registrar suscripción
                            self.channel_manager.subscribe_client(client_id, channels, gains)
                            print(f"[WebRTC DataChannel] ✅ Suscripción recibida via DataChannel")
                            
                    except Exception as e:
                        print(f"[WebRTC DataChannel] Error: {e}")
                
            except Exception as e:
                print(f"[WebRTC] DataChannel no creado: {e}")
            
            # Establecer oferta remota
            await pc.setRemoteDescription(
                RTCSessionDescription(sdp=offer_sdp, type="offer")
            )
            
            # Crear respuesta
            answer = await pc.createAnswer()
            
            await pc.setLocalDescription(answer)
            
            print(f"[WebRTC] ✅ Oferta WebRTC aceptada para {client_id[:8]}...")
            
            # Actualizar estadísticas
            self.stats['connections'] = len(self.pcs)
            
            return answer.sdp
            
        except Exception as e:
            print(f"[WebRTC] ❌ Error procesando oferta para {client_id[:8]}: {e}")
            await self.close_connection(client_id)
            raise
    
    async def add_ice_candidate(self, client_id: str, candidate_dict: dict):
        """Agrega un candidato ICE a la conexión - VERSIÓN QUE FUNCIONA"""
        if client_id not in self.pcs:
            print(f"[WebRTC] ⚠️ Cliente {client_id[:8]} no tiene PeerConnection activa")
            return
        
        pc = self.pcs[client_id]
        
        try:
            if config.VERBOSE:
                print(f"[WebRTC Server] Procesando ICE candidate para {client_id[:8]}")
            
            # Versión SIMPLE que SÍ funciona
            # Pasar el diccionario directamente como lo hacía la versión vieja
            await pc.addIceCandidate(candidate_dict)
            
            if config.VERBOSE:
                print(f"[WebRTC Server] ✅ ICE candidate agregado para {client_id[:8]}")
                
        except Exception as e:
            logger.error(f"Error agregando ICE candidate para {client_id[:8]}: {e}")
            if config.VERBOSE:
                print(f"[WebRTC Server] ❌ Error: {type(e).__name__}: {e}")
    
    async def close_connection(self, client_id: str):
        """Cierra una conexión WebRTC limpiamente"""
        try:
            # Detener track
            if client_id in self.audio_tracks:
                track = self.audio_tracks[client_id]
                await track.stop()
                del self.audio_tracks[client_id]
                print(f"[WebRTC] Track detenido para {client_id[:8]}")
            
            # Cerrar PeerConnection
            if client_id in self.pcs:
                pc = self.pcs[client_id]
                await pc.close()
                del self.pcs[client_id]
                print(f"[WebRTC] PeerConnection cerrada para {client_id[:8]}")
            
            # Desuscribir del channel manager
            self.channel_manager.unsubscribe_client(client_id)
            
            # Actualizar estadísticas
            self.stats['connections'] = len(self.pcs)
            
            print(f"[WebRTC] ✅ Conexión WebRTC cerrada para {client_id[:8]}...")
            
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
            'avg_packets_per_sec': self.stats['total_packets_sent'] / uptime if uptime > 0 else 0,
            'avg_bandwidth': self.stats['total_bytes_sent'] / uptime if uptime > 0 else 0,
            'errors': self.stats['errors']
        }