# native_server.py
import socket, threading, time, json, struct, numpy as np, logging
from audio_server.native_protocol import NativeAndroidProtocol
from collections import defaultdict
import config

logging.basicConfig(level=getattr(logging, config.LOG_LEVEL), format='[RF-SERVER] %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class NativeClient:
    def __init__(self, client_id: str, sock: socket.socket, address: tuple, persistent_id: str = None):
        self.id = client_id
        self.is_temp_id = True  # Flag para indicar que ID es temporal
        self.persistent_id = persistent_id or client_id
        self.socket = sock
        self.address = address
        self.status = 1  # 1=activo, 0=inactivo
        self.last_heartbeat = time.time()
        self.last_activity = time.time()
        self.subscribed_channels = set()  # ✅ Ahora manejado desde web
        self.rf_mode = False
        self.persistent = False
        self.auto_reconnect = False
        self.packets_sent = 0
        self.packets_dropped = 0
        self.connection_time = time.time()
        self.reconnection_count = 0
        self.reconnection_delay = 1000  # ms
        self.last_reconnect_attempt = 0
        
        # Socket optimizado
        try:
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, config.SOCKET_SNDBUF)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, config.SOCKET_RCVBUF)
            self.socket.settimeout(30.0)
            
            if config.TCP_KEEPALIVE:
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                if hasattr(socket, 'TCP_KEEPIDLE'):
                    self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 10)
                    self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 5)
                    self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
                    
        except Exception as e:
            logger.warning(f"⚠️ Socket options: {e}")
    
    def update_activity(self): 
        self.last_activity = time.time()
    
    def update_heartbeat(self): 
        self.last_heartbeat = time.time()
        self.update_activity()
    
    def is_alive(self, timeout: float = 120.0) -> bool:
        if self.auto_reconnect and self.status == 1:
            return True
        return (time.time() - self.last_heartbeat < timeout) and (self.status == 1)
    
    def send_bytes_direct(self, data: bytes) -> bool:
        if self.status == 0 or not data:
            return False
        
        try:
            self.socket.sendall(data)
            self.packets_sent += 1
            self.update_activity()
            return True
        except (BrokenPipeError, ConnectionError, OSError):
            self.status = 0
            return False
        except Exception as e:
            if config.DEBUG:
                logger.warning(f"⚠️ {self.id[:15]} - Error envío: {e}")
            self.packets_dropped += 1
            return False
    
    def send_audio_android(self, audio_data, sample_position: int) -> bool:
        if not self.subscribed_channels or self.status == 0: 
            return True
        
        if isinstance(audio_data, memoryview):
            num_channels = len(self.subscribed_channels)
            audio_data = np.frombuffer(audio_data, dtype=np.float32).reshape(-1, num_channels)
        
        channels = sorted(list(self.subscribed_channels))
        max_channel = audio_data.shape[1] - 1
        valid_channels = [ch for ch in channels if ch <= max_channel]
        
        if not valid_channels:
            return True
        
        packet_bytes = NativeAndroidProtocol.create_audio_packet(
            audio_data, valid_channels, sample_position, 0, self.rf_mode
        )
        
        if packet_bytes:
            if config.DEBUG and config.VALIDATE_PACKETS:
                valid, error = NativeAndroidProtocol.validate_packet(packet_bytes)
                if not valid:
                    logger.error(f"❌ {self.id[:15]} - Paquete inválido: {error}")
                    return False
            
            return self.send_bytes_direct(packet_bytes)
        return False
    
    def close(self):
        connection_duration = time.time() - self.connection_time
        logger.info(f"🔌 {self.id[:15]} - Duración: {connection_duration:.1f}s, "
                   f"Enviados: {self.packets_sent}, Perdidos: {self.packets_dropped}, "
                   f"Reconexiones: {self.reconnection_count}")
        self.status = 0
        try: 
            self.socket.shutdown(socket.SHUT_RDWR)
        except:
            pass
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
        self.maintenance_thread = None
        
        self.persistent_state = defaultdict(dict)
        self.persistent_lock = threading.Lock()
        self.STATE_CACHE_TIMEOUT = getattr(config, 'RF_STATE_CACHE_TIMEOUT', 300)
        
        self.sample_position_lock = threading.Lock()
        self.sample_position = 0
        
        self.stats = {
            'packets_sent': 0,
            'packets_dropped': 0,
            'clients_connected': 0,
            'clients_disconnected': 0,
            'clients_reconnected': 0,
            'bytes_sent': 0,
            'uptime': 0,
            'cached_states': 0
        }
        self.start_time = time.time()
        self.stats_lock = threading.Lock()
    
    def start(self):
        if self.running: 
            return
        
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        
        if config.SOCKET_NODELAY:
            self.server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        
        self.server_socket.bind((config.NATIVE_HOST, config.NATIVE_PORT))
        self.server_socket.listen(config.NATIVE_MAX_CLIENTS)
        self.server_socket.setblocking(False)
        self.running = True
        
        self.accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self.accept_thread.start()
        
        self.maintenance_thread = threading.Thread(target=self._maintenance_loop, daemon=True)
        self.maintenance_thread.start()
        
        logger.info(f"\n{'='*70}")
        logger.info(f"🟢 SERVIDOR RF MODO RECEPTOR PURO")
        logger.info(f"{'='*70}")
        logger.info(f"   🌐 Host: {config.NATIVE_HOST}:{config.NATIVE_PORT}")
        logger.info(f"   📦 BLOCKSIZE: {config.BLOCKSIZE} samples (~{config.BLOCKSIZE/config.SAMPLE_RATE*1000:.2f}ms)")
        logger.info(f"   🎵 SAMPLE_RATE: {config.SAMPLE_RATE} Hz")
        logger.info(f"   🔌 Socket TIMEOUT: 30s")
        logger.info(f"   🔄 Auto-reconexión: ENABLED")
        logger.info(f"   💾 Estado cache: {self.STATE_CACHE_TIMEOUT}s")
        logger.info(f"   ✅ Canales gestionados desde WEB")
        logger.info(f"{'='*70}\n")
    
    def _maintenance_loop(self):
        while self.running:
            time.sleep(30)
            
            try:
                current_time = time.time()
                
                # Limpiar estado persistente expirado
                with self.persistent_lock:
                    expired = [
                        pid for pid, state in self.persistent_state.items()
                        if current_time - state.get('last_seen', 0) > self.STATE_CACHE_TIMEOUT
                    ]
                    for pid in expired:
                        logger.info(f"🗑️ Limpiando estado expirado: {pid[:15]}")
                        del self.persistent_state[pid]
                
                # Verificar clientes inactivos
                with self.client_lock:
                    clients_to_remove = []
                    
                    for client_id, client in list(self.clients.items()):
                        if client.status == 0:
                            clients_to_remove.append(client_id)
                        elif not client.auto_reconnect and (current_time - client.last_activity > 60):
                            logger.warning(f"⚠️ Cliente sin auto-reconnect inactivo: {client_id[:15]}")
                            clients_to_remove.append(client_id)
                    
                    for client_id in clients_to_remove:
                        client = self.clients.get(client_id)
                        preserve = client.auto_reconnect if client else False
                        self._disconnect_client(client_id, preserve_state=preserve)
                
                # Actualizar estadísticas
                with self.stats_lock:
                    self.stats['uptime'] = int(time.time() - self.start_time)
                    self.stats['cached_states'] = len(self.persistent_state)
                    
            except Exception as e:
                if config.DEBUG:
                    logger.error(f"Error en maintenance: {e}")
    
    def stop(self):
        self.running = False
        with self.client_lock:
            for client in list(self.clients.values()):
                client.close()
            self.clients.clear()
        if self.server_socket:
            self.server_socket.close()
        
        stats = self.get_stats()
        uptime = time.time() - self.start_time
        logger.info("🛑 Servidor RF detenido")
        logger.info(f"📊 Stats - Uptime: {uptime:.1f}s")
        logger.info(f"   Clientes: {stats['clients_connected']} (Reconexiones: {stats['clients_reconnected']})")
        logger.info(f"   Paquetes: {stats['packets_sent']}")
    
    def _accept_loop(self):
        while self.running:
            try:
                client_socket, address = self.server_socket.accept()
                temp_id = f"temp_{address[0]}_{int(time.time() * 1000)}"
                
                client = NativeClient(temp_id, client_socket, address)
                
                with self.client_lock:
                    self.clients[temp_id] = client
                    self.stats['clients_connected'] += 1
                
                logger.info(f"✅ Cliente RF: {temp_id[:15]} ({address[0]})")
                threading.Thread(target=self._client_read_loop, args=(temp_id,), daemon=True).start()
                
            except BlockingIOError:
                time.sleep(0.01)
            except Exception as e:
                if self.running and config.DEBUG:
                    logger.error(f"Error accept: {e}")
    
    def _client_read_loop(self, client_id: str):
        client = self.clients.get(client_id)
        if not client: 
            return
        
        HEADER_SIZE = 16
        consecutive_errors = 0
        
        while self.running and client.status != 0:
            try:
                header_data = self._recv_exact(client.socket, HEADER_SIZE)
                if not header_data: 
                    time.sleep(1)
                    break
                
                magic, version, typeAndFlags, timestamp, payloadLength = struct.unpack('!IHHII', header_data)
                msgType = (typeAndFlags >> 8) & 0xFF
                
                if magic != NativeAndroidProtocol.MAGIC_NUMBER:
                    consecutive_errors += 1
                    if config.DEBUG:
                        logger.warning(f"⚠️ Magic inválido #{consecutive_errors} - {client_id[:15]}")

                    if consecutive_errors >= 5:
                        logger.warning(f"⚠️ Demasiados errores - {client_id[:15]}")
                        break

                    time.sleep(0.1)
                    continue
                
                consecutive_errors = 0
                
                max_payload = NativeAndroidProtocol.MAX_CONTROL_PAYLOAD
                if payloadLength < 0 or payloadLength > max_payload:
                    if config.DEBUG:
                        logger.error(f"❌ Payload inválido: {payloadLength}")
                    time.sleep(1)
                    continue
                
                payload = b''
                if payloadLength > 0:
                    payload = self._recv_exact(client.socket, payloadLength)
                    if not payload or len(payload) != payloadLength: 
                        time.sleep(1)
                        continue
                
                if msgType == NativeAndroidProtocol.MSG_TYPE_CONTROL:
                    try:
                        message = json.loads(payload.decode('utf-8'))
                        self._handle_control_message(client, message)
                    except Exception as e:
                        if config.DEBUG:
                            logger.error(f"❌ Control: {e}")
                
                client.update_heartbeat()
                
            except socket.timeout:
                client.update_activity()
                continue
            except (ConnectionError, BrokenPipeError, OSError):
                break
            except Exception as e:
                if config.DEBUG:
                    logger.error(f"❌ Read loop: {e}")
                time.sleep(1)
        
        self._disconnect_client(client_id, preserve_state=client.auto_reconnect)
    
    def _recv_exact(self, sock: socket.socket, size: int):
        data = b''
        timeout = 60.0
        start = time.time()
        
        while len(data) < size and (time.time() - start) < timeout:
            try:
                chunk = sock.recv(min(size - len(data), 65536))
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
            # ✅ AGREGAR al inicio del bloque handshake:
            persistent_id = message.get('client_id')

            # Validar que el cliente envió su UUID
            if not persistent_id:
                logger.error(f"❌ Handshake sin client_id UUID desde {client.address}")
                return

            # ✅ AGREGAR: Verificar si es reconexión
            is_reconnection = False
            old_temp_id = client.id

            with self.client_lock:
                # Si ya existe un cliente con este persistent_id, es reconexión
                if persistent_id in self.clients:
                    is_reconnection = True
                    logger.info(f"🔄 Reconexión detectada: {persistent_id[:15]}")

            # ✅ AGREGAR: Cambiar ID del cliente
            client.id = persistent_id
            client.persistent_id = persistent_id
            client.is_temp_id = False

            # ✅ AGREGAR: Actualizar diccionario de clientes
            with self.client_lock:
                # Remover entrada temporal
                if old_temp_id in self.clients:
                    del self.clients[old_temp_id]

                # Agregar con ID persistente
                self.clients[persistent_id] = client

            logger.info(f"✅ ID actualizado: {old_temp_id[:25]} → {persistent_id[:15]}")

            # ❌ ELIMINAR estas líneas (ya no son necesarias):
            # persistent_id = message.get('client_id', client.id)
            # client.persistent_id = persistent_id

            # CONTINUAR con el código existente...
            client.rf_mode = message.get('rf_mode', False)
            client.persistent = message.get('persistent', False)
            client.auto_reconnect = message.get('auto_reconnect', False)

            # ✅ MODIFICAR logging:
            logger.info(f"🤝 {client.id[:15]} - HANDSHAKE: "
                       f"reconnection={is_reconnection}, "
                       f"auto_reconnect={client.auto_reconnect}")

            # ✅ BUSCAR estado persistente (mantener código existente pero actualizar key)
            restored_state = None
            if client.auto_reconnect:
                with self.persistent_lock:
                    # ✅ USAR persistent_id (ahora es igual a client.id)
                    if persistent_id in self.persistent_state:
                        restored_state = self.persistent_state[persistent_id]
                        logger.info(f"💾 Estado restaurado para: {persistent_id[:15]}")
                        self.persistent_state[persistent_id]['last_seen'] = time.time()

                        # ✅ AGREGAR: Incrementar contador de reconexiones
                        if is_reconnection:
                            client.reconnection_count = restored_state.get('reconnection_count', 0) + 1
                            self.stats['clients_reconnected'] += 1

            # ✅ MODIFICAR: Registrar en channel_manager con ID persistente
            channels_to_subscribe = []
            if restored_state and 'channels' in restored_state:
                channels_to_subscribe = restored_state['channels']
                logger.info(f"📡 Canales restaurados: {len(channels_to_subscribe)} canales")

            # ❌ REEMPLAZAR:
            # self.channel_manager.subscribe_client(
            #     client.id, 
            #     channels_to_subscribe,
            #     client_type="native"
            # )

            # ✅ CON ESTO (usar persistent_id explícitamente):
            self.channel_manager.subscribe_client(
                persistent_id,  # ← Ahora es igual a client.id, pero explícito
                channels_to_subscribe,
                client_type="native"
            )

            # ✅ MODIFICAR: Aplicar estado restaurado
            if restored_state:
                # ❌ REEMPLAZAR:
                # self.channel_manager.update_client_mix(
                #     client.id,

                # ✅ CON ESTO:
                self.channel_manager.update_client_mix(
                    persistent_id,  # ← ID persistente
                    gains=restored_state.get('gains', {}),
                    pans=restored_state.get('pans', {}),
                    mutes=restored_state.get('mutes', {}),
                    solos=restored_state.get('solos', []),
                    pre_listen=restored_state.get('pre_listen'),
                    master_gain=restored_state.get('master_gain', 1.0)
                )

            # ✅ RESTO DEL CÓDIGO: handshake_response (mantener igual)
            response = NativeAndroidProtocol.create_control_packet(
                'handshake_response',
                {
                    'server_version': '2.4.0-RF-WEB-CONTROL',
                    'protocol_version': NativeAndroidProtocol.PROTOCOL_VERSION,
                    'sample_rate': config.SAMPLE_RATE,
                    'max_channels': self.channel_manager.num_channels,
                    'status': 'ready_rf',
                    'rf_mode': client.rf_mode,
                    'persistent': True,
                    'auto_reconnect_supported': True,
                    'server_blocksize': config.BLOCKSIZE,
                    'latency_ms': config.BLOCKSIZE / config.SAMPLE_RATE * 1000,
                    'web_controlled': True,
                    'state_restored': restored_state is not None,
                    # ✅ AGREGAR: Informar al cliente su ID persistente
                    'persistent_id': persistent_id,
                    'is_reconnection': is_reconnection
                },
                client.rf_mode
            )
            
            if response:
                client.send_bytes_direct(response)
            
            # Notificar a web clients (mantener)
            self._notify_web_clients_update()
        
        elif msg_type == 'heartbeat':
            # MANTENER código existente sin cambios
            response = NativeAndroidProtocol.create_control_packet(
                'heartbeat_response',
                {
                    'timestamp': int(time.time() * 1000),
                    'clients_connected': len(self.clients)
                },
                client.rf_mode
            )
            if response:
                client.send_bytes_direct(response)
    
    def _notify_web_clients_update(self):
        """Notificar a websocket server sobre cambio de clientes"""
        try:
            from audio_server import websocket_server
            websocket_server.broadcast_clients_update()
        except Exception as e:
            if config.DEBUG:
                logger.error(f"Error notificando web: {e}")
    
    def on_audio_data(self, audio_data):
        """Callback directo desde AudioCapture"""
        if not self.running:
            return
        
        if isinstance(audio_data, memoryview):
            audio_data = np.frombuffer(audio_data, dtype=np.float32).reshape(-1, self.channel_manager.num_channels)
        
        samples = audio_data.shape[0]
        current_position = self.increment_sample_position(samples)
        
        with self.client_lock:
            clients_to_remove = []
            sent = 0
            
            for client_id, client in list(self.clients.items()):
                if client.status == 0:
                    clients_to_remove.append(client_id)
                    continue
                
                # ✅ Obtener canales desde channel_manager
                subscription = self.channel_manager.get_client_subscription(client_id)
                if not subscription:
                    continue
                
                channels = subscription.get('channels', [])
                if not channels:
                    continue
                
                # Actualizar subscribed_channels del cliente
                client.subscribed_channels = set(channels)
                
                try:
                    if client.send_audio_android(audio_data, current_position):
                        sent += 1
                    else:
                        self.update_stats(packets_dropped=1)
                        if not client.auto_reconnect:
                            clients_to_remove.append(client_id)
                except Exception as e:
                    if config.DEBUG:
                        logger.error(f"❌ Envío {client_id[:15]}: {e}")
                    if not client.auto_reconnect:
                        clients_to_remove.append(client_id)
            
            for client_id in clients_to_remove:
                client = self.clients.get(client_id)
                preserve = client.auto_reconnect if client else False
                self._disconnect_client(client_id, preserve_state=preserve)
            
            if sent > 0:
                self.update_stats(packets_sent=sent)
    
    def _disconnect_client(self, client_id: str, preserve_state: bool = False):
        with self.client_lock:
            client = self.clients.pop(client_id, None)
            if client:
                self.update_stats(clients_disconnected=1)

                if preserve_state and client.auto_reconnect:
                    with self.persistent_lock:
                        subscription = self.channel_manager.get_client_subscription(client_id)
                        if subscription:
                            # ✅ USAR client.persistent_id (que ahora es igual a client_id)
                            # PERO dejar claro que estamos guardando por persistent_id
                            self.persistent_state[client.persistent_id] = {
                                'channels': subscription.get('channels', []),
                                'gains': subscription.get('gains', {}),
                                'pans': subscription.get('pans', {}),
                                'mutes': subscription.get('mutes', {}),
                                'solos': list(subscription.get('solos', set())),
                                'pre_listen': subscription.get('pre_listen'),
                                'master_gain': subscription.get('master_gain', 1.0),
                                'last_seen': time.time(),
                                'reconnection_count': client.reconnection_count,
                                'client_type': 'native'
                            }
                            logger.info(f"💾 Estado guardado para reconexión: {client.persistent_id[:15]}")
                        elif client.persistent_id in self.persistent_state:
                            # Si ya existe, actualizar last_seen
                            self.persistent_state[client.persistent_id]['last_seen'] = time.time()

                logger.info(f"🔌 Desconectado: {client_id[:15]} (reconnect={preserve_state})")
                client.close()

                self.channel_manager.unsubscribe_client(client_id)

                # ✅ AGREGAR: Notificar desconexión a Web UI
                self._notify_client_disconnected(client_id)

    # ✅ AGREGAR este método nuevo después de _disconnect_client:
    def _notify_client_disconnected(self, client_id):
        """Notificar a web clients sobre desconexión"""
        try:
            from audio_server import websocket_server
            websocket_server.socketio.emit('client_disconnected', {
                'client_id': client_id,
                'timestamp': int(time.time() * 1000)
            }, broadcast=True)
            logger.info(f"📢 Notificación de desconexión enviada: {client_id[:15]}")
        except Exception as e:
            if config.DEBUG:
                logger.error(f"Error notificando desconexión: {e}")
    
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
            stats = self.stats.copy()
            stats['active_clients'] = len(self.clients)
            
            with self.persistent_lock:
                stats['cached_states'] = len(self.persistent_state)
            
            return stats
    
    def get_client_count(self):
        with self.client_lock:
            return len(self.clients)
    
    def get_active_client_count(self):
        with self.client_lock:
            return sum(1 for c in self.clients.values() if c.subscribed_channels)