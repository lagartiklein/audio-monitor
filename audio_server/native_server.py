import socket, threading, time, json, struct, numpy as np, logging
from audio_server.native_protocol import NativeAndroidProtocol
import config

logging.basicConfig(level=logging.INFO, format='[RF] %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class NativeClient:
    def __init__(self, client_id: str, sock: socket.socket, address: tuple):
        self.id = client_id
        self.socket = sock
        self.address = address
        self.status = 1
        self.last_heartbeat = time.time()
        self.subscribed_channels = set()
        self.rf_mode = False
        self.write_lock = threading.Lock()
        self.packets_sent = 0
        self.packets_dropped = 0
        
        # ✅ Configurar socket optimizado
        try:
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 524288)  # 512KB
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
            self.socket.settimeout(10.0)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except Exception as e:
            logger.warning(f"⚠️ Socket options: {e}")
    
    def update_heartbeat(self): 
        self.last_heartbeat = time.time()
    
    def is_alive(self, timeout: float = 60.0) -> bool:
        return (time.time() - self.last_heartbeat < timeout) and (self.status == 1)
    
    def send_bytes_direct(self, data: bytes) -> bool:
        """✅ Envío DIRECTO sin queue"""
        if self.status == 0 or not data:
            return False
        
        try:
            with self.write_lock:
                self.socket.sendall(data)
            self.packets_sent += 1
            return True
        except (BrokenPipeError, ConnectionError, OSError):
            self.status = 0
            return False
        except Exception as e:
            logger.warning(f"⚠️ {self.id[:15]} - Error envío: {e}")
            self.packets_dropped += 1
            return False
    
    def send_audio_android(self, audio_data: np.ndarray, sample_position: int) -> bool:
        if not self.subscribed_channels or self.status == 0: 
            return True
        
        channels = sorted(list(self.subscribed_channels))
        max_channel = audio_data.shape[1] - 1
        valid_channels = [ch for ch in channels if ch <= max_channel]
        
        if not valid_channels:
            return True
        
        packet_bytes = NativeAndroidProtocol.create_audio_packet(
            audio_data, valid_channels, sample_position, 0, self.rf_mode
        )
        
        if packet_bytes:
            valid, error = NativeAndroidProtocol.validate_packet(packet_bytes)
            if not valid:
                logger.error(f"❌ {self.id[:15]} - Paquete inválido: {error}")
                return False
            return self.send_bytes_direct(packet_bytes)
        return False
    
    def close(self):
        logger.info(f"🔌 Cerrando {self.id[:15]} - Enviados: {self.packets_sent}, Perdidos: {self.packets_dropped}")
        self.status = 0
        try: 
            self.socket.close()
        except: 
            pass


class NativeAudioServer:
    def __init__(self, channel_manager):
        self.channel_manager = channel_manager
        self.running = False
        self.server_socket = None
        self.clients = {}
        self.client_lock = threading.RLock()
        self.accept_thread = None
        
        self.sample_position_lock = threading.Lock()
        self.sample_position = 0
        
        self.stats = {
            'packets_sent': 0,
            'packets_dropped': 0,
            'clients_disconnected': 0,
            'bytes_sent': 0
        }
        self.stats_lock = threading.Lock()
    
    def get_sample_position(self):
        with self.sample_position_lock:
            return self.sample_position
    
    def increment_sample_position(self, samples):
        with self.sample_position_lock:
            self.sample_position += samples
            return self.sample_position
    
    def update_stats(self, **kwargs):
        with self.stats_lock:
            for key, value in kwargs.items():
                if key in self.stats:
                    self.stats[key] += value
    
    def get_stats(self):
        with self.stats_lock:
            return self.stats.copy()
    
    def start(self):
        if self.running: 
            return
        
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((config.NATIVE_HOST, config.NATIVE_PORT))
        self.server_socket.listen(config.NATIVE_MAX_CLIENTS)
        self.server_socket.setblocking(False)
        self.running = True
        
        self.accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self.accept_thread.start()
        
        logger.info(f"🟢 SERVIDOR RF DIRECTO en {config.NATIVE_HOST}:{config.NATIVE_PORT}")
        logger.info(f"   📦 BLOCKSIZE: {config.BLOCKSIZE} samples (~{config.BLOCKSIZE/config.SAMPLE_RATE*1000:.1f}ms)")
        logger.info(f"   🎵 SAMPLE_RATE: {config.SAMPLE_RATE} Hz")
        logger.info(f"   🔒 Protocol: v{NativeAndroidProtocol.PROTOCOL_VERSION}")
    
    def stop(self):
        self.running = False
        with self.client_lock:
            for client in list(self.clients.values()):
                client.close()
            self.clients.clear()
        if self.server_socket:
            self.server_socket.close()
        
        stats = self.get_stats()
        logger.info("🛑 Servidor RF detenido")
        logger.info(f"📊 Stats - Enviados: {stats['packets_sent']}, Perdidos: {stats['packets_dropped']}")
    
    def _accept_loop(self):
        while self.running:
            try:
                client_socket, address = self.server_socket.accept()
                client_id = f"rf_{address[0]}_{int(time.time() * 1000)}"
                client = NativeClient(client_id, client_socket, address)
                
                with self.client_lock:
                    self.clients[client_id] = client
                
                logger.info(f"✅ Cliente conectado: {client_id[:15]} ({address[0]})")
                threading.Thread(target=self._client_read_loop, args=(client_id,), daemon=True).start()
                
            except BlockingIOError:
                time.sleep(0.01)
            except Exception as e:
                if self.running:
                    logger.error(f"Error aceptando: {e}")
    
    def _client_read_loop(self, client_id: str):
        client = self.clients.get(client_id)
        if not client: 
            return
        
        HEADER_SIZE = 16
        
        while self.running and client.status != 0:
            try:
                header_data = self._recv_exact(client.socket, HEADER_SIZE)
                if not header_data: 
                    break
                
                magic, version, typeAndFlags, timestamp, payloadLength = struct.unpack('!IHHII', header_data)
                msgType = (typeAndFlags >> 8) & 0xFF
                
                if magic != NativeAndroidProtocol.MAGIC_NUMBER:
                    logger.error(f"❌ {client_id[:15]} - Magic: 0x{magic:X}")
                    break
                
                max_payload = NativeAndroidProtocol.MAX_CONTROL_PAYLOAD
                if payloadLength < 0 or payloadLength > max_payload:
                    logger.error(f"❌ {client_id[:15]} - Payload: {payloadLength}")
                    break
                
                payload = b''
                if payloadLength > 0:
                    payload = self._recv_exact(client.socket, payloadLength)
                    if not payload or len(payload) != payloadLength: 
                        break
                
                if msgType == NativeAndroidProtocol.MSG_TYPE_CONTROL:
                    try:
                        message = json.loads(payload.decode('utf-8'))
                        self._handle_control_message(client, message)
                    except Exception as e:
                        logger.error(f"❌ Control: {e}")
                
                client.update_heartbeat()
                
            except socket.timeout:
                continue
            except (ConnectionError, BrokenPipeError, OSError):
                break
            except Exception as e:
                logger.error(f"❌ Read loop: {e}")
                break
        
        self._disconnect_client(client_id)
    
    def _recv_exact(self, sock: socket.socket, size: int):
        data = b''
        timeout = 10.0
        start = time.time()
        
        while len(data) < size and (time.time() - start) < timeout:
            try:
                chunk = sock.recv(min(size - len(data), 8192))
                if not chunk: 
                    return None
                data += chunk
            except socket.timeout: 
                continue
            except:
                return None
        
        return data if len(data) == size else None
    
    def _handle_control_message(self, client: NativeClient, message: dict):
        msg_type = message.get('type', '')
        
        if msg_type == 'handshake':
            client.rf_mode = message.get('rf_mode', False)
            logger.info(f"⭐ {client.id[:15]} - HANDSHAKE RF: {client.rf_mode}")
            
            response = NativeAndroidProtocol.create_control_packet(
                'handshake_response',
                {
                    'server_version': '2.0.3-DIRECT',
                    'protocol_version': NativeAndroidProtocol.PROTOCOL_VERSION,
                    'sample_rate': config.SAMPLE_RATE,
                    'max_channels': self.channel_manager.num_channels,
                    'status': 'ready',
                    'rf_mode': client.rf_mode,
                    'server_blocksize': config.BLOCKSIZE
                },
                client.rf_mode
            )
            
            if response:
                client.send_bytes_direct(response)
                logger.info(f"📤 Handshake enviado ({len(response)} bytes)")
        
        elif msg_type == 'subscribe':
            channels = message.get('channels', [])
            valid = [ch for ch in channels if 0 <= ch < self.channel_manager.num_channels]
            
            if valid:
                client.subscribed_channels = set(valid)
                logger.info(f"✅ {client.id[:15]} - Canales: {valid}")
                self.channel_manager.subscribe_client(client.id, valid)
                
                response = NativeAndroidProtocol.create_control_packet(
                    'subscription_confirmed',
                    {
                        'channels': valid,
                        'status': 'subscribed',
                        'blocksize': config.BLOCKSIZE,
                        'sample_position': self.get_sample_position()
                    },
                    client.rf_mode
                )
                
                if response:
                    client.send_bytes_direct(response)
        
        elif msg_type == 'heartbeat':
            response = NativeAndroidProtocol.create_control_packet(
                'heartbeat_response',
                {'timestamp': int(time.time() * 1000)},
                client.rf_mode
            )
            if response:
                client.send_bytes_direct(response)
    
    def on_audio_data(self, audio_data: np.ndarray):
        """
        ✅ Callback directo desde AudioCapture
        Se llama cada vez que hay un nuevo bloque de audio
        """
        if not self.running:
            return
        
        samples = audio_data.shape[0]
        current_position = self.increment_sample_position(samples)
        
        with self.client_lock:
            clients_to_remove = []
            active = 0
            sent = 0
            
            for client_id, client in list(self.clients.items()):
                if client.status == 0 or not client.is_alive():
                    clients_to_remove.append(client_id)
                    continue
                
                if not client.subscribed_channels:
                    continue
                
                active += 1
                
                try:
                    if client.send_audio_android(audio_data, current_position):
                        sent += 1
                    else:
                        self.update_stats(packets_dropped=1)
                except Exception as e:
                    logger.error(f"❌ Envío a {client_id[:15]}: {e}")
                    clients_to_remove.append(client_id)
            
            for client_id in clients_to_remove:
                self._disconnect_client(client_id)
            
            if sent > 0:
                self.update_stats(packets_sent=sent)
    
    def _disconnect_client(self, client_id: str):
        with self.client_lock:
            client = self.clients.pop(client_id, None)
            if client:
                self.update_stats(clients_disconnected=1)
                logger.info(f"❌ Desconectado: {client_id[:15]}")
                client.close()
                self.channel_manager.unsubscribe_client(client_id)
    
    def get_client_count(self):
        with self.client_lock:
            return len(self.clients)
    
    def get_active_client_count(self):
        with self.client_lock:
            return sum(1 for c in self.clients.values() if c.subscribed_channels)