# native_server.py - Servidor optimizado V2.1 con soporte broadcaster



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

    """MÃ©tricas por cliente"""

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

        """Actualiza mÃ©tricas de latencia"""

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

    """Cliente optimizado V2.1"""

    

    def __init__(self, client_id: str, sock: socket.socket, address: Tuple[str, int], num_channels: int):

        self.id = client_id

        self.socket = sock

        self.address = address

        self.num_channels = num_channels

        

        # Estado

        self.status = ClientStatus.CONNECTING

        self.authenticated = False

        self.last_heartbeat = time.time()

        

        # Suscripciones

        self.subscribed_channels: Set[int] = set()

        self.channel_gains: Dict[int, float] = {}

        self.client_type = ""

        self.capabilities: List[str] = []

        

        # MÃ©tricas

        self.metrics = ClientMetrics()

        self.metrics.connection_time = time.time()

        

        # Encoder

        self.encoder = NativeAudioEncoder()

        

        # ConfiguraciÃ³n

        self.sample_rate = config.SAMPLE_RATE

        self.buffer_size = config.NATIVE_CHUNK_SIZE

        self.format = 'pcm_16bit'

        self.latency_target = config.NATIVE_LATENCY_TARGET

        

        # Optimizar socket

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

        self.last_heartbeat = time.time()

    

    def is_alive(self, timeout: float = 10.0) -> bool:

        return time.time() - self.last_heartbeat < timeout

    

    def send_bytes(self, data: bytes) -> bool:

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

        try:

            message_json = json.dumps(message, separators=(',', ':'))

            packet_bytes = self.encoder.create_control_packet(message_json)

            return self.send_bytes(packet_bytes)

            

        except Exception as e:

            logger.error(f"Error enviando control: {e}")

            return False

    

    def send_config(self) -> bool:

        config_dict = {

            'type': 'config',

            'sample_rate': self.sample_rate,

            'channels': self.num_channels,

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

            logger.error(f"Error en suscripciÃ³n: {e}")

            return False

    

    def close(self):

        try:

            if self.socket:

                self.socket.close()

        except Exception as e:

            logger.debug(f"Error cerrando socket: {e}")

        finally:

            self.status = ClientStatus.DISCONNECTED



class NativeAudioServer:

    """Servidor optimizado V2.1 con soporte broadcaster"""

    

    def __init__(self, audio_capture, channel_manager):

        self.audio_capture = audio_capture

        self.channel_manager = channel_manager

        

        # âœ… Soporte broadcaster

        self.audio_queue = None  # SerÃ¡ asignado por main.py si usa broadcaster

        self.use_broadcaster = False

        

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

        

        # EstadÃ­sticas

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

                name="NativeAccept"

            )

            

            self.audio_thread = threading.Thread(

                target=self._audio_distribution_loop,

                daemon=True,

                name="NativeAudio"

            )

            

            self.monitor_thread = threading.Thread(

                target=self._monitor_loop,

                daemon=True,

                name="NativeMonitor"

            )

            

            self.accept_thread.start()

            self.audio_thread.start()

            self.monitor_thread.start()

            

            mode = "Broadcaster" if self.use_broadcaster else "Direct"

            logger.info(f"âœ… Servidor Nativo iniciado ({mode}) en {config.NATIVE_HOST}:{config.NATIVE_PORT}")

            

        except Exception as e:

            logger.error(f"âŒ Error iniciando servidor: {e}")

            raise

    

    def stop(self):

        logger.info("Deteniendo servidor nativo...")

        

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

        

        logger.info("Servidor nativo detenido")

    

    def _accept_loop(self):

        logger.info("Escuchando conexiones nativas...")

        

        while self.running:

            try:

                readable, _, _ = select.select([self.server_socket], [], [], 0.1)

                

                for sock in readable:

                    if sock is self.server_socket:

                        client_socket, address = self.server_socket.accept()

                        

                        client_id = f"native_{address[0]}_{int(time.time() * 1000)}"

                        client = NativeClient(client_id, client_socket, address, self.channel_manager.num_channels)

                        

                        with self.client_lock:

                            self.clients[client_id] = client

                            self.stats['total_clients'] += 1

                            self.stats['active_clients'] += 1

                        

                        logger.info(f"âœ… Cliente nativo: {client_id[:15]} desde {address}")

                        

                        client.send_config()

                        

                        threading.Thread(

                            target=self._client_read_loop,

                            args=(client_id,),

                            daemon=True,

                            name=f"NativeRead_{client_id[:8]}"

                        ).start()

            

            except Exception as e:

                if self.running:

                    logger.error(f"Error en accept loop: {e}")

    

    def _client_read_loop(self, client_id: str):

        client = self.clients.get(client_id)

        if not client:

            return

        

        HEADER_SIZE = config.NATIVE_HEADER_SIZE

        consecutive_errors = 0

        MAX_ERRORS = 5

        

        while self.running and client.status != ClientStatus.DISCONNECTED:

            try:

                header_data = self._recv_exact(client.socket, HEADER_SIZE)

                if not header_data:

                    break

                

                client.metrics.bytes_received += len(header_data)

                

                try:

                    header_tuple = NativePacket.decode_header(header_data)

                    magic, version, msg_type, flags, timestamp, sequence, payload_length = header_tuple

                except Exception as e:

                    logger.error(f"âŒ Error decodificando header: {e}")

                    consecutive_errors += 1

                    if consecutive_errors >= MAX_ERRORS:

                        break

                    continue

                

                if magic != config.NATIVE_MAGIC_NUMBER:

                    consecutive_errors += 1

                    if consecutive_errors >= MAX_ERRORS:

                        break

                    continue

                

                consecutive_errors = 0

                

                if payload_length > 0:

                    payload = self._recv_exact(client.socket, payload_length)

                    if not payload:

                        break

                    client.metrics.bytes_received += len(payload)

                else:

                    payload = b''

                

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

                

        except Exception as e:

            logger.error(f"Error procesando mensaje: {e}")

    

    def _handle_control_message(self, client: NativeClient, message: Dict):

        msg_type = message.get('type', '')

        

        if msg_type == 'handshake':

            client.client_type = message.get('client_type', 'unknown')

            client.capabilities = message.get('capabilities', [])

            client.authenticated = True

            client.status = ClientStatus.CONNECTED

            

            logger.info(f"ðŸ¤ Handshake nativo: {client.id[:15]} ({client.client_type})")

            

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

            

            logger.info(f"ðŸ“¡ Nativo {client.id[:15]} suscrito a {len(channels)} canales")

        

        elif msg_type == 'update_gain':

            channel = int(message.get('channel', 0))

            gain = float(message.get('gain', 1.0))

            

            self.channel_manager.update_gain(client.id, channel, gain)

            client.channel_gains[channel] = gain

    

    def _audio_distribution_loop(self):

        """Loop de distribuciÃ³n con soporte broadcaster"""

        mode = "Broadcaster" if self.use_broadcaster else "Direct"

        logger.info(f"Iniciando distribuciÃ³n de audio nativa ({mode})...")

        

        if self.use_broadcaster:

            if self.audio_queue is None:

                logger.error("âŒ ERROR: use_broadcaster=True pero audio_queue=None!")

                return

            else:

                logger.info(f"âœ… Audio queue configurado correctamente")

        

        consecutive_errors = 0

        max_consecutive_errors = 10

        packets_sent = 0

        

        while self.running:

            try:

                # âœ… Obtener audio del broadcaster o directamente

                if self.use_broadcaster and self.audio_queue:

                    try:

                        audio_data = self.audio_queue.get(timeout=0.1)

                        

                        # Log periÃ³dico

                        if packets_sent % 100 == 0 and packets_sent > 0:

                            logger.debug(f"ðŸ“¦ Nativo recibiÃ³ {packets_sent} paquetes del broadcaster")

                        

                    except Exception as e:

                        # Timeout normal

                        continue

                else:

                    # Fallback: obtener directamente

                    block_time = config.BLOCKSIZE / config.SAMPLE_RATE

                    audio_data = self.audio_capture.get_audio_data(timeout=block_time * 2)

                

                if audio_data is None:

                    consecutive_errors += 1

                    if consecutive_errors > max_consecutive_errors:

                        logger.warning(f"âš ï¸  Muchos timeouts de audio ({consecutive_errors})")

                        time.sleep(0.01)

                    continue

                

                consecutive_errors = 0

                packets_sent += 1

                

                timestamp = int((time.time() - self.stats['start_time']) * 1000)

                

                # Distribuir a clientes

                with self.client_lock:

                    if not self.clients:

                        # Sin clientes, continuar

                        continue

                    

                    clients_to_remove = []

                    active_clients = 0

                    

                    for client_id, client in self.clients.items():

                        if client.status == ClientStatus.DISCONNECTED:

                            clients_to_remove.append(client_id)

                            continue

                        

                        if not client.is_alive():

                            logger.warning(f"âš ï¸  Cliente {client_id[:15]} timeout")

                            clients_to_remove.append(client_id)

                            continue

                        

                        if not client.subscribed_channels:

                            continue

                        

                        active_clients += 1

                        

                        try:

                            channels = list(client.subscribed_channels)

                            

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

                                processed_audio = audio_data

                            

                            success = client.send_audio(processed_audio, channels, timestamp)

                            

                            if success:

                                packet_time = time.time() * 1000 - timestamp

                                client.metrics.update_latency(packet_time)

                                

                                self.stats['total_packets_sent'] += 1

                                self.stats['total_bytes_sent'] += processed_audio.nbytes

                            else:

                                self.stats['audio_errors'] += 1

                                logger.debug(f"âŒ Error enviando a {client_id[:15]}")

                                

                        except Exception as e:

                            logger.error(f"Error procesando audio para {client_id[:8]}: {e}")

                            self.stats['audio_errors'] += 1

                            clients_to_remove.append(client_id)

                    

                    # Log periÃ³dico de actividad

                    if packets_sent % 100 == 0 and active_clients > 0:

                        logger.debug(f"ðŸ“Š Nativo: {active_clients} clientes activos, {self.stats['total_packets_sent']} paquetes enviados")

                    

                    for client_id in clients_to_remove:

                        self._disconnect_client(client_id)

                

            except Exception as e:

                logger.error(f"Error en audio distribution loop: {e}")

                consecutive_errors += 1

                

                if consecutive_errors >= max_consecutive_errors:

                    logger.error(f"âŒ Demasiados errores en loop nativo")

                    break

                

                time.sleep(0.01)

        

        logger.info("Loop de distribuciÃ³n nativa detenido")

    

    def _monitor_loop(self):

        while self.running:

            try:

                time.sleep(5)

                

                with self.client_lock:

                    active = sum(1 for c in self.clients.values() 

                               if c.status != ClientStatus.DISCONNECTED)

                    

                    if config.VERBOSE and active > 0:

                        logger.info(f"ðŸ“Š Clientes nativos: {active} | Paquetes: {self.stats['total_packets_sent']}")

            

            except Exception as e:

                logger.error(f"Error en monitor loop: {e}")

    

    def _disconnect_client(self, client_id: str):

        with self.client_lock:

            client = self.clients.pop(client_id, None)

            if client:

                client.close()

                self.channel_manager.unsubscribe_client(client_id)

                self.stats['active_clients'] -= 1

                logger.info(f"Cliente nativo desconectado: {client_id[:15]}")

    

    def get_stats(self) -> Dict:

        uptime = time.time() - self.stats['start_time']

        

        return {

            'uptime': round(uptime, 1),

            'active_clients': self.stats['active_clients'],

            'total_packets_sent': self.stats['total_packets_sent'],

            'audio_errors': self.stats['audio_errors']

        }