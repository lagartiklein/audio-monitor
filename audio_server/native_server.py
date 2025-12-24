# native_server.py - OPTIMIZADO Setup→Stream
# ✅ Sin race conditions
# ✅ Latencia mínima
# ✅ Stream puro de audio

import socket
import select
import threading
import time
import json
import struct
import numpy as np
from typing import Dict, List, Set, Tuple, Optional
import queue
import logging
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import config

from .native_protocol import NativeAudioEncoder, NativePacket, NativeControlProtocol

logger = logging.getLogger(__name__)

# Tipos de mensaje
MESSAGE_TYPE_AUDIO = 0x01
MESSAGE_TYPE_CONTROL = 0x02

class NativeClient:
    """Cliente nativo con estados SETUP y STREAMING"""
    
    # Estados del cliente
    STATE_SETUP = "setup"          # Fase inicial: acepta control
    STATE_STREAMING = "streaming"  # Fase streaming: solo audio
    
    def __init__(self, client_id: str, sock: socket.socket, address: Tuple[str, int]):
        self.id = client_id
        self.socket = sock
        self.address = address
        self.connected = True
        
        # ✅ ESTADO CRÍTICO
        self.state = self.STATE_SETUP  # Inicia en SETUP
        
        self.subscribed_channels: List[int] = []
        self.channel_gains: Dict[int, float] = {}
        self.last_heartbeat = time.time()
        self.sequence_expected = 0
        self.latency_samples = []
        self.stats = {
            'bytes_sent': 0,
            'packets_sent': 0,
            'bytes_received': 0,
            'packets_received': 0,
            'latency_avg': 0,
            'latency_min': 999,
            'latency_max': 0,
            'packet_loss': 0
        }
        
        logger.info(f"✅ Cliente creado en estado: {self.state}")
        
    def switch_to_streaming(self):
        """Cambiar a modo streaming puro"""
        self.state = self.STATE_STREAMING
        logger.info(f"🎵 Cliente {self.id[:12]} → MODO STREAMING PURO")
        
    def update_heartbeat(self):
        self.last_heartbeat = time.time()
    
    def is_alive(self, timeout: float = 10.0) -> bool:
        return time.time() - self.last_heartbeat < timeout
    
    def add_latency_sample(self, latency_ms: float):
        self.latency_samples.append(latency_ms)
        if len(self.latency_samples) > 100:
            self.latency_samples.pop(0)
        
        if self.latency_samples:
            self.stats['latency_avg'] = int(sum(self.latency_samples) / len(self.latency_samples))
            self.stats['latency_min'] = min(self.latency_samples)
            self.stats['latency_max'] = max(self.latency_samples)
    
    def send_packet(self, packet: NativePacket) -> bool:
        """Enviar paquete de AUDIO (solo en modo STREAMING)"""
        try:
            if self.state != self.STATE_STREAMING:
                logger.warning(f"⚠️ Intento de enviar audio en estado {self.state}")
                return False
            
            # Prefijo AUDIO + datos
            type_byte = struct.pack('B', MESSAGE_TYPE_AUDIO)
            data = type_byte + packet.encode_full()
            
            sent = self.socket.send(data)
            self.stats['bytes_sent'] += sent
            self.stats['packets_sent'] += 1
            return sent == len(data)
        except Exception as e:
            logger.error(f"❌ Error enviando audio: {e}")
            self.connected = False
            return False
    
    def send_control(self, message: str) -> bool:
        """Enviar mensaje de CONTROL (solo en modo SETUP)"""
        try:
            if self.state == self.STATE_STREAMING:
                logger.warning(f"⚠️ Intento de enviar control en STREAMING (ignorado)")
                return False
            
            msg_bytes = message.encode('utf-8')
            length = len(msg_bytes)
            
            # Prefijo CONTROL + longitud + datos
            type_byte = struct.pack('B', MESSAGE_TYPE_CONTROL)
            header = struct.pack('!I', length)
            
            data = type_byte + header + msg_bytes
            self.socket.send(data)
            self.stats['bytes_sent'] += len(data)
            
            if config.VERBOSE:
                logger.debug(f"📤 Control enviado: {message[:50]}...")
            
            return True
        except Exception as e:
            logger.error(f"❌ Error enviando control: {e}")
            return False

class NativeAudioServer:
    """Servidor OPTIMIZADO: Setup → Pure Streaming"""
    
    def __init__(self, audio_capture, channel_manager):
        self.audio_capture = audio_capture
        self.channel_manager = channel_manager
        self.running = False
        
        self.host = config.NATIVE_HOST
        self.port = config.NATIVE_PORT
        self.server_socket = None
        
        self.clients: Dict[str, NativeClient] = {}
        self.client_lock = threading.RLock()
        
        self.encoder = NativeAudioEncoder(
            sample_rate=config.SAMPLE_RATE,
            channels=min(config.CHANNELS_MAX, 8)
        )
        
        self.accept_thread = None
        self.audio_thread = None
        self.setup_thread = None
        
        self.stats = {
            'total_clients': 0,
            'active_clients': 0,
            'streaming_clients': 0,
            'total_packets_sent': 0,
            'total_bytes_sent': 0,
            'start_time': time.time(),
            'errors': 0
        }
        
        logger.info("🚀 Native Audio Server OPTIMIZADO inicializado")
    
    def start(self):
        """Iniciar servidor"""
        if self.running:
            return
        
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.server_socket.setblocking(False)
            
            self.running = True
            
            # Thread de aceptación
            self.accept_thread = threading.Thread(
                target=self._accept_connections,
                daemon=True,
                name="NativeAcceptThread"
            )
            
            # Thread de audio (solo clientes en STREAMING)
            self.audio_thread = threading.Thread(
                target=self._audio_distribution_loop,
                daemon=True,
                name="NativeAudioThread"
            )
            
            # Thread de setup (solo clientes en SETUP)
            self.setup_thread = threading.Thread(
                target=self._setup_loop,
                daemon=True,
                name="NativeSetupThread"
            )
            
            self.accept_thread.start()
            self.audio_thread.start()
            self.setup_thread.start()
            
            logger.info(f"✅ Native Server en {self.host}:{self.port}")
            logger.info(f"⚡ Arquitectura: Setup → Pure Streaming")
            logger.info(f"🎯 Latencia objetivo: {config.NATIVE_LATENCY_TARGET}ms")
            
        except Exception as e:
            logger.error(f"❌ Error iniciando servidor: {e}")
            raise
    
    def stop(self):
        """Detener servidor"""
        self.running = False
        
        with self.client_lock:
            for client_id in list(self.clients.keys()):
                self._disconnect_client(client_id)
        
        if self.server_socket:
            self.server_socket.close()
        
        logger.info("🛑 Native Server detenido")
    
    def _accept_connections(self):
        """Aceptar nuevas conexiones"""
        logger.info("👂 Escuchando conexiones...")
        
        while self.running:
            try:
                readable, _, _ = select.select([self.server_socket], [], [], 0.1)
                
                for sock in readable:
                    if sock is self.server_socket:
                        client_socket, address = self.server_socket.accept()
                        
                        client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                        client_socket.setblocking(False)
                        
                        client_id = f"native_{address[0]}_{int(time.time())}"
                        client = NativeClient(client_id, client_socket, address)
                        
                        with self.client_lock:
                            self.clients[client_id] = client
                            self.stats['total_clients'] += 1
                            self.stats['active_clients'] += 1
                        
                        logger.info(f"🔌 Nuevo cliente: {client_id[:16]} desde {address}")
                        logger.info(f"   Estado inicial: {client.state}")
                        
            except Exception as e:
                if self.running:
                    logger.error(f"❌ Error aceptando conexión: {e}")
    
    def _setup_loop(self):
        """
        ✅ Thread dedicado a clientes en FASE SETUP
        Solo procesa clientes que están en STATE_SETUP
        """
        logger.info("🤝 Setup loop iniciado")
        
        while self.running:
            try:
                with self.client_lock:
                    setup_clients = [
                        (cid, client) for cid, client in self.clients.items()
                        if client.state == NativeClient.STATE_SETUP and client.connected
                    ]
                
                for client_id, client in setup_clients:
                    try:
                        # Verificar si hay datos disponibles
                        ready = select.select([client.socket], [], [], 0.01)[0]
                        if not ready:
                            continue
                        
                        # Leer tipo de mensaje
                        type_byte = client.socket.recv(1, socket.MSG_PEEK)
                        if len(type_byte) != 1:
                            continue
                        
                        msg_type = struct.unpack('B', type_byte)[0]
                        
                        if msg_type == MESSAGE_TYPE_CONTROL:
                            # Consumir el byte de tipo
                            client.socket.recv(1)
                            
                            # Leer longitud
                            header = client.socket.recv(4)
                            if len(header) != 4:
                                continue
                            
                            msg_length = struct.unpack('!I', header)[0]
                            
                            if 0 < msg_length < 65536:
                                # Leer mensaje
                                msg_data = b''
                                while len(msg_data) < msg_length:
                                    chunk = client.socket.recv(
                                        min(4096, msg_length - len(msg_data))
                                    )
                                    if not chunk:
                                        break
                                    msg_data += chunk
                                
                                if len(msg_data) == msg_length:
                                    message = msg_data.decode('utf-8')
                                    self._handle_setup_message(client_id, client, message)
                                
                                client.update_heartbeat()
                        
                        else:
                            logger.warning(f"⚠️ Cliente en SETUP envió tipo {msg_type}")
                    
                    except (socket.error, ConnectionResetError):
                        self._disconnect_client(client_id)
                    except Exception as e:
                        logger.error(f"❌ Error en setup de {client_id}: {e}")
                
                time.sleep(0.05)  # 50ms - no crítico para latencia
                
            except Exception as e:
                logger.error(f"❌ Error en setup loop: {e}")
                time.sleep(0.5)
    
    def _handle_setup_message(self, client_id: str, client: NativeClient, message: str):
        """Procesar mensaje de control en fase SETUP"""
        try:
            data = json.loads(message)
            msg_type = data.get('type', '')
            
            if msg_type == 'handshake':
                logger.info(f"🤝 Handshake de {client_id[:12]}")
                
                # Enviar configuración
                config_msg = json.dumps({
                    'type': 'config',
                    'sample_rate': config.SAMPLE_RATE,
                    'channels': self.channel_manager.num_channels,
                    'chunk_size': config.NATIVE_CHUNK_SIZE,
                    'format': 'pcm_int16',
                    'protocol_version': config.NATIVE_PROTOCOL_VERSION
                })
                client.send_control(config_msg)
                logger.info(f"📤 Config enviada a {client_id[:12]}")
            
            elif msg_type == 'subscribe':
                channels = data.get('channels', [])
                gains = data.get('gains', {})
                gains = {int(k): float(v) for k, v in gains.items()}
                
                # Registrar suscripción
                self.channel_manager.subscribe_client(client_id, channels, gains)
                client.subscribed_channels = channels
                client.channel_gains = gains
                
                logger.info(f"✅ {client_id[:12]} suscrito a {len(channels)} canales")
                
                # Confirmar suscripción
                response = json.dumps({
                    'type': 'subscribed',
                    'channels': channels,
                    'timestamp': int(time.time() * 1000)
                })
                client.send_control(response)
                
                # ===== CAMBIAR A MODO STREAMING =====
                client.switch_to_streaming()
                
                with self.client_lock:
                    self.stats['streaming_clients'] += 1
                
                logger.info(f"🎵 {client_id[:12]} → STREAMING (solo audio)")
            
            else:
                logger.warning(f"⚠️ Mensaje setup desconocido: {msg_type}")
                
        except Exception as e:
            logger.error(f"❌ Error procesando setup: {e}")
    
    def _audio_distribution_loop(self):
        """
        ⚡ Loop CRÍTICO de audio
        Solo procesa clientes en STATE_STREAMING
        Path ultra-optimizado
        """
        logger.info("🎵 Audio distribution loop iniciado (STREAMING PURO)")
        
        frame_duration = config.NATIVE_CHUNK_SIZE / config.SAMPLE_RATE
        next_frame_time = time.time()
        packet_counter = 0
        
        while self.running:
            try:
                current_time = time.time()
                if current_time < next_frame_time:
                    sleep_time = next_frame_time - current_time
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                
                # Capturar audio
                audio_data = self.audio_capture.get_audio_data(timeout=0.01)
                if audio_data is None:
                    audio_data = np.zeros(
                        (config.NATIVE_CHUNK_SIZE, self.channel_manager.num_channels),
                        dtype=np.float32
                    )
                    continue
                
                # ===== PATH CRÍTICO: Solo clientes STREAMING =====
                with self.client_lock:
                    streaming_clients = [
                        (cid, client) for cid, client in self.clients.items()
                        if client.state == NativeClient.STATE_STREAMING 
                        and client.connected
                    ]
                
                clients_to_remove = []
                
                for client_id, client in streaming_clients:
                    # Obtener suscripción
                    if client_id not in self.channel_manager.subscriptions:
                        continue
                    
                    sub = self.channel_manager.subscriptions[client_id]
                    channels = sub.get('channels', [])
                    gains = sub.get('gains', {})
                    
                    if not channels:
                        continue
                    
                    try:
                        # Procesar audio
                        processed_audio = audio_data.copy()
                        for ch in channels:
                            if ch < processed_audio.shape[1]:
                                gain = gains.get(ch, 1.0)
                                if gain != 1.0:
                                    processed_audio[:, ch] *= gain
                        
                        # Crear paquete
                        packet = self.encoder.create_packet(
                            audio_data=processed_audio,
                            active_channels=channels,
                            timestamp=int((time.time() - self.encoder.start_time) * 1000)
                        )
                        
                        # Enviar (método ya incluye prefijo 0x01)
                        success = client.send_packet(packet)
                        
                        if success:
                            self.stats['total_packets_sent'] += 1
                            self.stats['total_bytes_sent'] += packet.get_size()
                            
                            latency = self.encoder.calculate_latency(packet)
                            client.add_latency_sample(latency)
                        else:
                            clients_to_remove.append(client_id)
                    
                    except Exception as e:
                        logger.error(f"❌ Error enviando a {client_id}: {e}")
                        clients_to_remove.append(client_id)
                        self.stats['errors'] += 1
                
                # Limpiar clientes desconectados
                for client_id in clients_to_remove:
                    self._disconnect_client(client_id)
                
                next_frame_time += frame_duration
                
                if current_time > next_frame_time + frame_duration:
                    next_frame_time = current_time
                
                # Stats periódicos
                packet_counter += 1
                if packet_counter % 500 == 0:
                    self._log_stats()
                
            except Exception as e:
                logger.error(f"❌ Error en audio loop: {e}")
                time.sleep(0.01)
    
    def _disconnect_client(self, client_id: str):
        """Desconectar cliente"""
        with self.client_lock:
            client = self.clients.pop(client_id, None)
            if client:
                try:
                    if client.state == NativeClient.STATE_STREAMING:
                        self.stats['streaming_clients'] -= 1
                    
                    client.socket.close()
                    self.channel_manager.unsubscribe_client(client_id)
                    self.stats['active_clients'] -= 1
                    
                    logger.info(f"🔌 Cliente desconectado: {client_id[:16]} (estado: {client.state})")
                except Exception as e:
                    logger.error(f"❌ Error desconectando: {e}")
    
    def _log_stats(self):
        """Estadísticas periódicas"""
        if not config.VERBOSE:
            return
        
        with self.client_lock:
            latencies = [
                c.stats['latency_avg'] for c in self.clients.values()
                if c.state == NativeClient.STATE_STREAMING and c.stats['latency_avg'] > 0
            ]
        
        if latencies:
            avg_lat = sum(latencies) / len(latencies)
            min_lat = min(latencies)
            max_lat = max(latencies)
            
            logger.info(
                f"📊 Clientes: {self.stats['streaming_clients']} streaming, "
                f"{self.stats['active_clients']} total | "
                f"Latencia: avg={avg_lat:.1f}ms min={min_lat:.1f}ms max={max_lat:.1f}ms | "
                f"Packets={self.stats['total_packets_sent']}"
            )
    
    def get_stats(self) -> Dict:
        """Estadísticas del servidor"""
        uptime = time.time() - self.stats['start_time']
        
        return {
            'uptime': uptime,
            'active_clients': self.stats['active_clients'],
            'streaming_clients': self.stats['streaming_clients'],
            'total_clients': self.stats['total_clients'],
            'total_packets_sent': self.stats['total_packets_sent'],
            'total_bytes_sent': self.stats['total_bytes_sent'],
            'errors': self.stats['errors']
        }