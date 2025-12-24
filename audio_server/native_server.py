# native_server.py - Servidor optimizado V2.1 con headers de 20 bytes

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
from dataclasses import dataclass
from enum import IntEnum

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import config
from audio_server.native_protocol import NativeAudioEncoder, NativeControlProtocol, NativePacket, NativeDecoder

logger = logging.getLogger(__name__)

# Enums
class MessageType(IntEnum):
    AUDIO = 0x01
    CONTROL = 0x02
    PING = 0x03
    CONFIG = 0x04

class ClientStatus(IntEnum):
    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2
    STREAMING = 3
    ERROR = 4

@dataclass
class ClientMetrics:
    """Métricas por cliente"""
    latency_avg: float = 0.0
    latency_min: float = 999.0
    latency_max: float = 0.0
    jitter: float = 0.0
    packet_loss: float = 0.0
    packets_sent: int = 0
    packets_received: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    connection_time: float = 0.0
    last_packet_time: float = 0.0
    
    def update_latency(self, latency: float):
        """Actualiza métricas de latencia"""
        self.latency_avg = (self.latency_avg * 0.9) + (latency * 0.1)
        self.latency_min = min(self.latency_min, latency)
        self.latency_max = max(self.latency_max, latency)
    
    def to_dict(self) -> Dict:
        """Convierte a diccionario"""
        return {
            'latency_avg': round(self.latency_avg, 1),
            'latency_min': round(self.latency_min, 1),
            'latency_max': round(self.latency_max, 1),
            'jitter': round(self.jitter, 1),
            'packet_loss': round(self.packet_loss, 1),
            'packets_sent': self.packets_sent,
            'bytes_sent': self.bytes_sent,
            'connection_time': round(self.connection_time, 1)
        }

class NativeClient:
    """Cliente optimizado V2.1 con protocolo length-prefix"""
    
    def __init__(self, client_id: str, sock: socket.socket, address: Tuple[str, int], num_channels: int):
       
        self.id = client_id
        self.socket = sock
        self.address = address
        self.num_channels = num_channels  # ✅ Guardar
        
        # Estado
        self.status = ClientStatus.CONNECTING
        self.authenticated = False
        self.last_heartbeat = time.time()
        
        # Suscripciones
        self.subscribed_channels: Set[int] = set()
        self.channel_gains: Dict[int, float] = {}
        self.client_type = ""
        self.capabilities: List[str] = []
        
        # Métricas
        self.metrics = ClientMetrics()
        self.metrics.connection_time = time.time()
        
        # Encoder
        self.encoder = NativeAudioEncoder()
        
        # Configuración del cliente
        self.sample_rate = config.SAMPLE_RATE
        self.buffer_size = config.NATIVE_CHUNK_SIZE
        self.format = 'pcm_16bit'
        self.latency_target = config.NATIVE_LATENCY_TARGET
        
        # Configurar socket para baja latencia
        try:
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 1)
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 1)
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
            self.socket.settimeout(10.0)
        except Exception as e:
            logger.warning(f"No se pudo optimizar socket: {e}")
    
    def update_heartbeat(self):
        """Actualiza heartbeat"""
        self.last_heartbeat = time.time()
    
    def is_alive(self, timeout: float = 10.0) -> bool:
        """Verifica si el cliente está vivo"""
        return time.time() - self.last_heartbeat < timeout
    
    def send_bytes(self, data: bytes) -> bool:
        """Envía bytes directamente"""
        try:
            total_sent = 0
            while total_sent < len(data):
                sent = self.socket.send(data[total_sent:])
                if sent == 0:
                    raise ConnectionError("Socket connection broken")
                total_sent += sent
            
            self.metrics.bytes_sent += total_sent
            return True
            
        except (ConnectionError, BrokenPipeError, TimeoutError, OSError) as e:
            logger.debug(f"Cliente desconectado: {self.id[:8]} - {e}")
            self.status = ClientStatus.DISCONNECTED
            return False
            
        except Exception as e:
            logger.error(f"Error enviando a {self.id[:8]}: {e}")
            self.status = ClientStatus.ERROR
            return False
    
    def send_audio(self, audio_data: np.ndarray, channels: List[int], timestamp: int) -> bool:
        """Envía paquete de audio usando encoder"""
        try:
            packet_bytes = self.encoder.create_audio_packet(
                audio_data=audio_data,
                active_channels=channels,
                timestamp=timestamp
            )
            
            success = self.send_bytes(packet_bytes)
            
            if success:
                self.metrics.packets_sent += 1
            
            return success
            
        except Exception as e:
            logger.error(f"Error enviando audio: {e}")
            return False
    
    def send_control(self, message: Dict) -> bool:
        """Envía mensaje de control usando encoder"""
        try:
            message_json = json.dumps(message, separators=(',', ':'))
            packet_bytes = self.encoder.create_control_packet(message_json)
            return self.send_bytes(packet_bytes)
            
        except Exception as e:
            logger.error(f"Error enviando control: {e}")
            return False
    
    def send_config(self) -> bool:
        """Envía configuración al cliente"""
        config_dict = {
            'type': 'config',
            'sample_rate': self.sample_rate,
        'channels': self.num_channels,  # ✅ Dinámico
            'buffer_size': self.buffer_size,
            'format': self.format,
            'latency_target': self.latency_target,
            'protocol_version': config.NATIVE_PROTOCOL_VERSION,
            'server_version': '2.1.0'
        }
        
        try:
            packet_bytes = self.encoder.create_config_packet(config_dict)
            return self.send_bytes(packet_bytes)
        except Exception as e:
            logger.error(f"Error enviando config: {e}")
            return False
    
    def subscribe(self, channels: List[int], gains: Dict[int, float]) -> bool:
        """Suscribe cliente a canales"""
        try:
            self.subscribed_channels.clear()
            self.subscribed_channels.update(channels)
            
            self.channel_gains.clear()
            self.channel_gains.update(gains)
            
            response = {
                'type': 'subscribed',
                'channels': list(self.subscribed_channels),
                'timestamp': int(time.time() * 1000)
            }
            
            return self.send_control(response)
            
        except Exception as e:
            logger.error(f"Error en suscripción: {e}")
            return False
    
    def close(self):
        """Cierra conexión limpiamente"""
        try:
            if self.socket:
                self.socket.close()
        except Exception as e:
            logger.debug(f"Error cerrando socket: {e}")
        finally:
            self.status = ClientStatus.DISCONNECTED

class NativeAudioServer:
    """Servidor optimizado V2.1"""
    
    def __init__(self, audio_capture, channel_manager):
        self.audio_capture = audio_capture
        self.channel_manager = channel_manager
        
        # Estado
        self.running = False
        self.server_socket = None
        
        # Clientes
        self.clients: Dict[str, NativeClient] = {}
        self.client_lock = threading.RLock()
        
        # Threads
        self.accept_thread = None
        self.audio_thread = None
        self.monitor_thread = None
        
        # Estadísticas
        self.stats = {
            'start_time': time.time(),
            'total_clients': 0,
            'active_clients': 0,
            'total_packets_sent': 0,
            'total_bytes_sent': 0,
            'audio_errors': 0,
            'client_errors': 0
        }
        
        logger.info("Native Audio Server V2.1 inicializado")
    
    def start(self):
        """Inicia el servidor"""
        if self.running:
            return
        
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            
            self.server_socket.bind((config.NATIVE_HOST, config.NATIVE_PORT))
            self.server_socket.listen(config.NATIVE_MAX_CLIENTS)
            self.server_socket.setblocking(False)
            
            self.running = True
            
            # Iniciar threads
            self.accept_thread = threading.Thread(
                target=self._accept_loop,
                daemon=True,
                name="AcceptThread"
            )
            
            self.audio_thread = threading.Thread(
                target=self._audio_distribution_loop,
                daemon=True,
                name="AudioThread"
            )
            
            self.monitor_thread = threading.Thread(
                target=self._monitor_loop,
                daemon=True,
                name="MonitorThread"
            )
            
            self.accept_thread.start()
            self.audio_thread.start()
            self.monitor_thread.start()
            
            logger.info(f"✅ Servidor iniciado en {config.NATIVE_HOST}:{config.NATIVE_PORT}")
            logger.info(f"🎯 Protocolo V{config.NATIVE_PROTOCOL_VERSION} | Header: {config.NATIVE_HEADER_SIZE} bytes")
            logger.info(f"🎯 Latencia objetivo: {config.NATIVE_LATENCY_TARGET}ms")
            logger.info(f"📊 Chunk size: {config.NATIVE_CHUNK_SIZE} samples")
            
        except Exception as e:
            logger.error(f"❌ Error iniciando servidor: {e}")
            raise
    
    def stop(self):
        """Detiene el servidor"""
        logger.info("Deteniendo servidor...")
        
        self.running = False
        
        with self.client_lock:
            for client in list(self.clients.values()):
                client.close()
            self.clients.clear()
        
        if self.server_socket:
            self.server_socket.close()
        
        for thread in [self.accept_thread, self.audio_thread, self.monitor_thread]:
            if thread and thread.is_alive():
                thread.join(timeout=2)
        
        logger.info("Servidor detenido")
    
    def _accept_loop(self):
        """Loop de aceptación de conexiones"""
        logger.info("Escuchando conexiones...")
        
        while self.running:
            try:
                readable, _, _ = select.select([self.server_socket], [], [], 0.1)
                
                for sock in readable:
                    if sock is self.server_socket:
                        client_socket, address = self.server_socket.accept()
                        
                        client_id = f"{address[0]}_{int(time.time() * 1000)}"
                        client = NativeClient(client_id, client_socket, address, self.channel_manager.num_channels)
                        
                        with self.client_lock:
                            self.clients[client_id] = client
                            self.stats['total_clients'] += 1
                            self.stats['active_clients'] += 1
                        
                        logger.info(f"✅ Nuevo cliente: {client_id} desde {address}")
                        
                        client.send_config()
                        
                        threading.Thread(
                            target=self._client_read_loop,
                            args=(client_id,),
                            daemon=True,
                            name=f"ClientRead_{client_id[:8]}"
                        ).start()
            
            except Exception as e:
                if self.running:
                    logger.error(f"Error en accept loop: {e}")
    
    def _client_read_loop(self, client_id: str):
        """✅ Loop de lectura con headers de 20 bytes"""
        client = self.clients.get(client_id)
        if not client:
            return
        
        logger.debug(f"Iniciando read loop para {client_id[:8]}")
        
        HEADER_SIZE = config.NATIVE_HEADER_SIZE  # 20 bytes
        consecutive_errors = 0
        MAX_ERRORS = 5
        
        while self.running and client.status != ClientStatus.DISCONNECTED:
            try:
                # ✅ 1. Leer header completo (20 bytes)
                header_data = self._recv_exact(client.socket, HEADER_SIZE)
                if not header_data:
                    break
                
                client.metrics.bytes_received += len(header_data)
                
                # ✅ 2. Decodificar header
                try:
                    header_tuple = NativePacket.decode_header(header_data)
                    magic, version, msg_type, flags, timestamp, sequence, payload_length = header_tuple
                except Exception as e:
                    logger.error(f"❌ Error decodificando header: {e}")
                    consecutive_errors += 1
                    if consecutive_errors >= MAX_ERRORS:
                        break
                    continue
                
                # ✅ 3. Validar
                if magic != config.NATIVE_MAGIC_NUMBER:
                    logger.error(f"❌ Magic inválido: {hex(magic)}")
                    consecutive_errors += 1
                    if consecutive_errors >= MAX_ERRORS:
                        break
                    continue
                
                if version != config.NATIVE_PROTOCOL_VERSION:
                    logger.error(f"❌ Versión incorrecta: {version}")
                    consecutive_errors += 1
                    if consecutive_errors >= MAX_ERRORS:
                        break
                    continue
                
                consecutive_errors = 0
                
                # ✅ 4. Leer payload exacto según payload_length
                if payload_length > 0:
                    payload = self._recv_exact(client.socket, payload_length)
                    if not payload:
                        break
                    client.metrics.bytes_received += len(payload)
                else:
                    payload = b''
                
                # ✅ 5. Procesar según tipo
                self._process_message(client, MessageType(msg_type), header_tuple, payload)
                
                client.metrics.packets_received += 1
                client.update_heartbeat()
                
            except socket.timeout:
                continue
                
            except (ConnectionError, BrokenPipeError, OSError):
                break
                
            except Exception as e:
                logger.error(f"Error en read loop {client_id[:8]}: {e}")
                break
        
        self._disconnect_client(client_id)
    
    def _recv_exact(self, sock: socket.socket, size: int) -> Optional[bytes]:
        """Recibe exactamente 'size' bytes o None si falla"""
        data = b''
        while len(data) < size:
            try:
                chunk = sock.recv(size - len(data))
                if not chunk:
                    return None
                data += chunk
            except socket.timeout:
                continue
            except Exception:
                return None
        return data
    
    def _process_message(self, client: NativeClient, msg_type: MessageType, 
                        header_tuple: tuple, payload: bytes):
        """Procesa mensaje del cliente"""
        try:
            if msg_type == MessageType.CONTROL:
                message = NativeDecoder.decode_control_packet(header_tuple, payload)
                self._handle_control_message(client, message)
                
            elif msg_type == MessageType.PING:
                ping_data = NativeDecoder.decode_ping_packet(header_tuple, payload)
                
                pong_msg = {
                    'type': 'pong',
                    'timestamp': int(time.time() * 1000),
                    'counter': ping_data.get('counter', 0)
                }
                client.send_control(pong_msg)
                
            else:
                logger.debug(f"Mensaje tipo {msg_type} de {client.id[:8]}")
                
        except Exception as e:
            logger.error(f"Error procesando mensaje: {e}")
    
    def _handle_control_message(self, client: NativeClient, message: Dict):
        """Maneja mensaje de control"""
        msg_type = message.get('type', '')
        
        if msg_type == 'handshake':
            client.client_type = message.get('client_type', 'unknown')
            client.capabilities = message.get('capabilities', [])
            client.authenticated = True
            client.status = ClientStatus.CONNECTED
            
            logger.info(f"🤝 Handshake de {client.id[:8]} ({client.client_type})")
            
            response = {
                'type': 'handshake_ack',
                'server_version': '2.1.0',
                'protocol_version': config.NATIVE_PROTOCOL_VERSION,
                'timestamp': int(time.time() * 1000),
                'session_id': client.id
            }
            client.send_control(response)
        
        elif msg_type == 'subscribe':
            channels = message.get('channels', [])
            gains = message.get('gains', {})
            gains = {int(k): float(v) for k, v in gains.items()}
            
            self.channel_manager.subscribe_client(client.id, channels, gains)
            client.subscribe(channels, gains)
            
            logger.info(f"📡 {client.id[:8]} suscrito a {len(channels)} canales")
        
        elif msg_type == 'update_gain':
            channel = int(message.get('channel', 0))
            gain = float(message.get('gain', 1.0))
            
            self.channel_manager.update_gain(client.id, channel, gain)
            client.channel_gains[channel] = gain
        
        elif msg_type == 'get_stats':
            stats_msg = {
                'type': 'stats',
                'client_stats': client.metrics.to_dict(),
                'server_stats': self.get_stats(),
                'timestamp': int(time.time() * 1000)
            }
            client.send_control(stats_msg)
    


    def _audio_distribution_loop(self):
        """
        ✅ Loop de distribución MEJORADO con mejor sincronización
        """
        logger.info("Iniciando distribución de audio optimizada...")
        
        # ✅ NO intentar mantener timing artificial - dejarlo fluir naturalmente
        # El timing real lo dicta el audio_capture callback
        
        consecutive_errors = 0
        max_consecutive_errors = 10
        packets_sent_cycle = 0
        cycle_start_time = time.time()
        
        while self.running:
            try:
                # ✅ Obtener audio con timeout corto - NO bloqueante
                # El timeout debe ser menor que el tiempo de un bloque
                block_time = config.BLOCKSIZE / config.SAMPLE_RATE
                audio_data = self.audio_capture.get_audio_data(timeout=block_time * 2)
                
                if audio_data is None:
                    # No hay audio disponible - puede ser normal
                    consecutive_errors += 1
                    if consecutive_errors > max_consecutive_errors:
                        logger.error(f"⚠️ Demasiados timeouts consecutivos ({consecutive_errors})")
                        time.sleep(0.01)
                    continue
                
                # Reset error counter
                consecutive_errors = 0
                
                # Timestamp basado en tiempo real del servidor
                timestamp = int((time.time() - self.stats['start_time']) * 1000)
                
                # ✅ Distribuir a todos los clientes RÁPIDAMENTE
                with self.client_lock:
                    clients_to_remove = []
                    
                    for client_id, client in self.clients.items():
                        # Verificar estado del cliente
                        if client.status == ClientStatus.DISCONNECTED:
                            clients_to_remove.append(client_id)
                            continue
                        
                        # Verificar timeout
                        if not client.is_alive():
                            logger.warning(f"Cliente {client_id[:8]} timeout")
                            clients_to_remove.append(client_id)
                            continue
                        
                        # Solo enviar a clientes suscritos
                        if not client.subscribed_channels:
                            continue
                        
                        try:
                            channels = list(client.subscribed_channels)
                            
                            # ✅ Aplicar ganancias EFICIENTEMENTE
                            # Hacer copia solo si hay ganancias diferentes de 1.0
                            needs_processing = any(
                                client.channel_gains.get(ch, 1.0) != 1.0 
                                for ch in channels
                            )
                            
                            if needs_processing:
                                processed_audio = audio_data.copy()
                                for channel in channels:
                                    if channel < processed_audio.shape[1]:
                                        gain = client.channel_gains.get(channel, 1.0)
                                        if gain != 1.0:
                                            processed_audio[:, channel] *= gain
                            else:
                                # Sin ganancias especiales - usar original
                                processed_audio = audio_data
                            
                            # ✅ Enviar audio
                            success = client.send_audio(processed_audio, channels, timestamp)
                            
                            if success:
                                # Actualizar métricas
                                packet_time = time.time() * 1000 - timestamp
                                client.metrics.update_latency(packet_time)
                                
                                self.stats['total_packets_sent'] += 1
                                self.stats['total_bytes_sent'] += processed_audio.nbytes
                                packets_sent_cycle += 1
                            else:
                                self.stats['audio_errors'] += 1
                                logger.debug(f"Error enviando a {client_id[:8]}")
                                
                        except Exception as e:
                            logger.error(f"Error procesando audio para {client_id[:8]}: {e}")
                            self.stats['audio_errors'] += 1
                            clients_to_remove.append(client_id)
                    
                    # Limpiar clientes desconectados
                    for client_id in clients_to_remove:
                        self._disconnect_client(client_id)
                
                # ✅ Estadísticas periódicas
                if packets_sent_cycle >= 100:
                    cycle_duration = time.time() - cycle_start_time
                    packets_per_sec = packets_sent_cycle / cycle_duration if cycle_duration > 0 else 0
                    
                    if config.VERBOSE:
                        logger.debug(
                            f"📊 Audio: {packets_sent_cycle} paquetes en {cycle_duration:.1f}s "
                            f"({packets_per_sec:.0f} pkt/s) | "
                            f"Clientes activos: {len(self.clients)}"
                        )
                    
                    packets_sent_cycle = 0
                    cycle_start_time = time.time()
                
            except Exception as e:
                logger.error(f"Error en audio distribution loop: {e}")
                consecutive_errors += 1
                
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f"⚠️ Demasiados errores consecutivos ({consecutive_errors})")
                    break
                
                time.sleep(0.01)
        
        logger.info("Loop de distribución de audio detenido")

    def _monitor_loop(self):
        """
        ✅ Loop de monitoreo MEJORADO con más información
        """
        while self.running:
            try:
                time.sleep(5)
                
                with self.client_lock:
                    active_clients = sum(1 for c in self.clients.values() 
                                       if c.status != ClientStatus.DISCONNECTED)
                    
                    if config.VERBOSE and active_clients > 0:
                        # Recolectar métricas
                        avg_latencies = []
                        subscribed_channels_total = 0
                        
                        for client in self.clients.values():
                            if client.status != ClientStatus.DISCONNECTED:
                                avg_latencies.append(client.metrics.latency_avg)
                                subscribed_channels_total += len(client.subscribed_channels)
                        
                        if avg_latencies:
                            avg_latency = sum(avg_latencies) / len(avg_latencies)
                            min_latency = min(avg_latencies)
                            max_latency = max(avg_latencies)
                            
                            # ✅ Reporte más completo
                            logger.info(
                                f"\n📊 Estado del Servidor:"
                                f"\n  Clientes: {active_clients}"
                                f"\n  Canales suscritos: {subscribed_channels_total}"
                                f"\n  Latencia: avg={avg_latency:.1f}ms, "
                                f"min={min_latency:.1f}ms, max={max_latency:.1f}ms"
                                f"\n  Paquetes enviados: {self.stats['total_packets_sent']}"
                                f"\n  Errores de audio: {self.stats['audio_errors']}"
                            )
                            
                            # ⚠️ Advertencias
                            if avg_latency > config.NATIVE_LATENCY_TARGET * 2:
                                logger.warning(
                                    f"⚠️ Latencia alta: {avg_latency:.1f}ms "
                                    f"(objetivo: {config.NATIVE_LATENCY_TARGET}ms)"
                                )
                            
                            if self.stats['audio_errors'] > 100:
                                logger.warning(
                                    f"⚠️ Muchos errores de audio: {self.stats['audio_errors']}"
                                )
                    
                    # ✅ También monitorear el audio_capture si está disponible
                    if hasattr(self.audio_capture, 'get_stats'):
                        capture_stats = self.audio_capture.get_stats()
                        
                        if capture_stats['dropped_frames'] > 0:
                            drop_rate = (capture_stats['dropped_frames'] / 
                                       capture_stats['total_callbacks']) * 100
                            
                            if drop_rate > 1.0:
                                logger.warning(
                                    f"⚠️ Audio Capture descartando frames: {drop_rate:.1f}%"
                                )
                        
                        queue_fill = capture_stats['queue_fill_percent']
                        if queue_fill < 20:
                            logger.warning(
                                f"⚠️ Buffer de captura bajo: {queue_fill:.0f}%"
                            )
                        elif queue_fill > 90:
                            logger.warning(
                                f"⚠️ Buffer de captura alto: {queue_fill:.0f}%"
                            )
            
            except Exception as e:
                logger.error(f"Error en monitor loop: {e}")
    
    def _disconnect_client(self, client_id: str):
        """Desconecta cliente"""
        with self.client_lock:
            client = self.clients.pop(client_id, None)
            if client:
                client.close()
                self.channel_manager.unsubscribe_client(client_id)
                self.stats['active_clients'] -= 1
                logger.info(f"Cliente desconectado: {client_id}")
    
    def get_stats(self) -> Dict:
        """Obtiene estadísticas"""
        uptime = time.time() - self.stats['start_time']
        
        stats = {
            'uptime': round(uptime, 1),
            'active_clients': self.stats['active_clients'],
            'total_clients': self.stats['total_clients'],
            'total_packets_sent': self.stats['total_packets_sent'],
            'total_bytes_sent': self.stats['total_bytes_sent'],
            'audio_errors': self.stats['audio_errors'],
            'packets_per_second': round(self.stats['total_packets_sent'] / uptime, 1) if uptime > 0 else 0
        }
        
        with self.client_lock:
            latencies = [c.metrics.latency_avg for c in self.clients.values() 
                        if c.metrics.latency_avg > 0]
            
            if latencies:
                stats['avg_latency'] = round(sum(latencies) / len(latencies), 1)
                stats['min_latency'] = round(min(latencies), 1)
                stats['max_latency'] = round(max(latencies), 1)
        
        return stats