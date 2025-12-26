import socket, select, threading, time, json, struct, numpy as np, logging, sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import config
from audio_server.native_protocol import NativeAndroidProtocol

logger = logging.getLogger(__name__)

class NativeClient:
    def __init__(self, client_id: str, sock: socket.socket, address: tuple, num_channels: int):
        self.id = client_id
        self.socket = sock
        self.address = address
        self.num_channels = num_channels
        self.status = 1
        self.authenticated = False
        self.last_heartbeat = time.time()
        self.subscribed_channels = set()
        self.channel_gains = {}
        self.audio_sequence = 0
        try:
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.socket.settimeout(10.0)
        except: pass
    
    def update_heartbeat(self): self.last_heartbeat = time.time()
    def is_alive(self, timeout: float = 30.0) -> bool: return time.time() - self.last_heartbeat < timeout
    
    def send_bytes(self, data: bytes) -> bool:
        try:
            total_sent = 0
            while total_sent < len(data):
                sent = self.socket.send(data[total_sent:])
                if sent == 0: return False
                total_sent += sent
            return True
        except:
            self.status = 0
            return False
    
    def send_audio_android(self, audio_data: np.ndarray, sample_position: int) -> bool:
        if not self.subscribed_channels: return True
        channels = sorted(list(self.subscribed_channels))
        packet_bytes = NativeAndroidProtocol.create_audio_packet(audio_data, channels, sample_position, self.audio_sequence)
        success = self.send_bytes(packet_bytes)
        if success: self.audio_sequence += 1
        return success
    
    def send_handshake_response(self):
        response = NativeAndroidProtocol.create_control_packet('handshake_response', {
            'server_version': '2.1.0', 'protocol_version': NativeAndroidProtocol.PROTOCOL_VERSION,
            'sample_rate': 48000, 'max_channels': self.num_channels, 'session_id': self.id, 'status': 'ready'
        })
        return self.send_bytes(response)
    
    def send_subscribe_response(self, channels: list):
        response = NativeAndroidProtocol.create_control_packet('subscribed', {
            'channels': channels, 'timestamp': int(time.time() * 1000), 'status': 'success'
        })
        return self.send_bytes(response)
    
    def close(self):
        try:
            if self.socket: self.socket.close()
        except: pass
        self.status = 0

class NativeAudioServer:
    def __init__(self, audio_capture, channel_manager):
        self.audio_capture = audio_capture
        self.channel_manager = channel_manager
        self.audio_queue = None
        self.use_broadcaster = False
        self.running = False
        self.server_socket = None
        self.clients = {}
        self.client_lock = threading.RLock()
        self.accept_thread = None
        self.audio_thread = None
        self.stats = {'start_time': time.time(), 'total_clients': 0, 'active_clients': 0, 'total_packets_sent': 0, 'audio_errors': 0}
    
    def start(self):
        if self.running: return
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((config.NATIVE_HOST, config.NATIVE_PORT))
            self.server_socket.listen(config.NATIVE_MAX_CLIENTS)
            self.server_socket.setblocking(False)
            self.running = True
            self.accept_thread = threading.Thread(target=self._accept_loop, daemon=True, name="NativeAccept")
            self.audio_thread = threading.Thread(target=self._audio_distribution_loop, daemon=True, name="NativeAudio")
            self.accept_thread.start()
            self.audio_thread.start()
            logger.info(f"🟢 Native server started on {config.NATIVE_HOST}:{config.NATIVE_PORT}")
        except Exception as e:
            logger.error(f"Start error: {e}")
            raise
    
    def stop(self):
        logger.info("Stopping native server...")
        self.running = False
        with self.client_lock:
            for client in list(self.clients.values()): client.close()
            self.clients.clear()
        if self.server_socket: self.server_socket.close()
        for thread in [self.accept_thread, self.audio_thread]:
            if thread and thread.is_alive(): thread.join(timeout=2)
        logger.info("Native server stopped")
    
    def _accept_loop(self):
        logger.info("Listening for native connections...")
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
                        logger.info(f"✅ Native client connected: {client_id[:15]} from {address}")
                        # NO enviar handshake_response inmediatamente, esperar handshake del cliente
            except Exception as e:
                if self.running: logger.error(f"Accept loop error: {e}")
    
    def _client_read_loop(self, client_id: str):
        client = self.clients.get(client_id)
        if not client: return
        HEADER_SIZE = 20
        consecutive_errors = 0
        logger.info(f"📖 Starting read loop for {client_id[:15]}")
        while self.running and client.status != 0:
            try:
                header_data = self._recv_exact(client.socket, HEADER_SIZE)
                if not header_data:
                    logger.warning(f"⚠️ Connection closed by {client_id[:15]}")
                    break
                try:
                    magic, version, msg_type, flags, timestamp, sequence, payload_length = struct.unpack('!IHBBIII', header_data)
                    logger.debug(f"📦 Header: magic=0x{magic:08x}, version={version}, type={msg_type}, payload={payload_length}")
                    
                    if magic != NativeAndroidProtocol.MAGIC_NUMBER:
                        logger.error(f"❌ Invalid magic: 0x{magic:08x}, expected: 0x{NativeAndroidProtocol.MAGIC_NUMBER:08x}")
                        consecutive_errors += 1
                        if consecutive_errors >= 5: break
                        continue
                    
                except struct.error as e:
                    logger.error(f"❌ Header unpack error: {e}")
                    consecutive_errors += 1
                    if consecutive_errors >= 5: break
                    continue
                consecutive_errors = 0
                payload = b''
                if payload_length > 0:
                    if payload_length > 1024 * 1024:
                        logger.error(f"❌ Payload too large: {payload_length}")
                        break
                    payload = self._recv_exact(client.socket, payload_length)
                    if not payload:
                        logger.error(f"❌ Failed to read payload")
                        break
                if msg_type == NativeAndroidProtocol.MSG_TYPE_CONTROL:
                    try:
                        message = json.loads(payload.decode('utf-8'))
                        logger.info(f"📨 Control: {message.get('type', 'unknown')}")
                        self._handle_control_message(client, message)
                    except Exception as e:
                        logger.error(f"❌ Control error: {e}")
                client.update_heartbeat()
            except socket.timeout: continue
            except (ConnectionError, BrokenPipeError, OSError) as e:
                logger.warning(f"⚠️ Connection error: {e}")
                break
            except Exception as e:
                logger.error(f"❌ Read error: {e}")
                break
        logger.info(f"📖 Read loop ended for {client_id[:15]}")
        self._disconnect_client(client_id)
    
    def _recv_exact(self, sock: socket.socket, size: int):
        data = b''
        while len(data) < size:
            try:
                chunk = sock.recv(size - len(data))
                if not chunk: return None
                data += chunk
            except socket.timeout: continue
            except: return None
        return data
    
    def _handle_control_message(self, client: NativeClient, message: dict):
        msg_type = message.get('type', '')
        logger.info(f"🔧 Handling: {msg_type}")
        if msg_type == 'handshake':
            # Verificar versión de protocolo
            client_version = message.get('protocol_version', 1)
            if client_version != NativeAndroidProtocol.PROTOCOL_VERSION:
                logger.error(f"❌ Versión incompatible: cliente={client_version}, servidor={NativeAndroidProtocol.PROTOCOL_VERSION}")
                client.close()
                return
            
            client.authenticated = True
            client.status = 2
            
            # Enviar respuesta detallada
            response_data = {
                'server_version': '2.1.0',
                'protocol_version': NativeAndroidProtocol.PROTOCOL_VERSION,
                'sample_rate': 48000,
                'max_channels': self.audio_capture.actual_channels,
                'session_id': client.id,
                'status': 'ready',
                'timestamp': int(time.time() * 1000),
                'block_size': config.BLOCKSIZE
            }
            
            # Crear y enviar respuesta
            response = NativeAndroidProtocol.create_control_packet('handshake_response', response_data)
            success = client.send_bytes(response)
            
            if success:
                logger.info(f"✅ Handshake completado: {client.id[:15]}")
            else:
                logger.error(f"❌ Error enviando handshake_response")
                client.close()
                
        elif msg_type == 'subscribe':
            channels = message.get('channels', [])
            logger.info(f"📡 Subscribe: {channels}")
            valid = [ch for ch in channels if 0 <= ch < self.audio_capture.actual_channels]
            if valid:
                client.subscribed_channels = set(valid)
                success = client.send_subscribe_response(valid)
                if success:
                    logger.info(f"✅ Subscribed: {valid}")
                else:
                    logger.error(f"❌ Failed subscribe response")
                self.channel_manager.subscribe_client(client.id, valid, {ch: 1.0 for ch in valid})
            else:
                logger.warning(f"⚠️ No valid channels")
        elif msg_type == 'heartbeat':
            client.update_heartbeat()
            logger.debug(f"💓 Heartbeat")
        else:
            logger.warning(f"⚠️ Unknown type: {msg_type}")
    
    def _audio_distribution_loop(self):
        logger.info("🎵 Audio distribution started")
        consecutive_errors = 0
        sample_position = 0
        while self.running:
            try:
                if self.use_broadcaster and self.audio_queue:
                    try: audio_data = self.audio_queue.get(timeout=0.1)
                    except: continue
                else:
                    audio_data = self.audio_capture.get_audio_data(timeout=(256/48000)*2)
                if audio_data is None:
                    consecutive_errors += 1
                    if consecutive_errors > 10: time.sleep(0.01)
                    continue
                consecutive_errors = 0
                sample_position += audio_data.shape[0]
                with self.client_lock:
                    if not self.clients: continue
                    clients_to_remove = []
                    for client_id, client in self.clients.items():
                        if client.status == 0:
                            clients_to_remove.append(client_id)
                            continue
                        if not client.is_alive():
                            logger.warning(f"⚠️ Timeout: {client_id[:15]}")
                            clients_to_remove.append(client_id)
                            continue
                        if not client.subscribed_channels: continue
                        try:
                            success = client.send_audio_android(audio_data, sample_position)
                            if success: self.stats['total_packets_sent'] += 1
                            else:
                                self.stats['audio_errors'] += 1
                                clients_to_remove.append(client_id)
                        except Exception as e:
                            logger.error(f"❌ Audio send error: {e}")
                            self.stats['audio_errors'] += 1
                            clients_to_remove.append(client_id)
                    for client_id in clients_to_remove:
                        self._disconnect_client(client_id)
            except Exception as e:
                logger.error(f"❌ Audio loop error: {e}")
                consecutive_errors += 1
                if consecutive_errors >= 10:
                    logger.error("❌ Too many errors")
                    break
                time.sleep(0.01)
        logger.info("🛑 Audio distribution stopped")
    
    def _disconnect_client(self, client_id: str):
        with self.client_lock:
            client = self.clients.pop(client_id, None)
            if client:
                client.close()
                self.channel_manager.unsubscribe_client(client_id)
                self.stats['active_clients'] -= 1
                logger.info(f"❌ Disconnected: {client_id[:15]}")