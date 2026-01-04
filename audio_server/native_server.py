# native_server.py - FASE 2: OPTIMIZADO CON ENVÍO ASÍNCRONO
import socket, threading, time, json, struct, numpy as np, logging
import select
from queue import Queue, Empty, Full
from audio_server.native_protocol import NativeAndroidProtocol
from collections import defaultdict
import config

logging.basicConfig(level=getattr(logging, config.LOG_LEVEL), format='[RF-SERVER] %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ✅ FASE 2: Configuración de colas asíncronas
SEND_QUEUE_SIZE = 8  # Paquetes máximos en cola por cliente
SEND_THREAD_COUNT = 2  # Threads de envío


class NativeClient:
    def __init__(self, client_id: str, sock: socket.socket, address: tuple, persistent_id: str = None):
        self.id = client_id
        self.is_temp_id = True
        self.persistent_id = persistent_id or client_id
        self.socket = sock
        self.address = address
        self.status = 1
        self.last_heartbeat = time.time()
        self.last_activity = time.time()
        self.subscribed_channels = set()
        self.rf_mode = False
        self.persistent = False
        self.auto_reconnect = False
        self.packets_sent = 0
        self.packets_dropped = 0
        self.connection_time = time.time()
        self.reconnection_count = 0
        self.consecutive_send_failures = 0
        self.max_consecutive_failures = 5
        
        # ✅ FASE 2: Cola de envío asíncrono por cliente
        self.send_queue = Queue(maxsize=SEND_QUEUE_SIZE)
        self.send_thread = None
        self.send_running = True
        
        # Socket optimizado
        try:
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, config.SOCKET_SNDBUF)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, config.SOCKET_RCVBUF)
            # ✅ FIX: Socket BLOQUEANTE con timeout para lectura, select() para escritura no-bloqueante
            self.socket.setblocking(True)
            self.socket.settimeout(3.0)  # ⚠️ Reducido: 5s → 3s para detección rápida de errores
            
            if config.TCP_KEEPALIVE:
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                if hasattr(socket, 'TCP_KEEPIDLE'):
                    self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 10)
                    self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 5)
                    self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
                    
        except Exception as e:
            logger.warning(f"⚠️ Socket options: {e}")
        
        # ✅ FASE 2: Iniciar thread de envío asíncrono
        self._start_send_thread()
    
    def update_activity(self): 
        self.last_activity = time.time()
    
    def update_heartbeat(self): 
        self.last_heartbeat = time.time()
        self.update_activity()
    
    # ✅ FASE 2: Thread de envío asíncrono por cliente
    def _start_send_thread(self):
        """Iniciar thread dedicado para envío no bloqueante"""
        self.send_thread = threading.Thread(
            target=self._send_loop, 
            daemon=True,
            name=f"send-{self.id[:8]}"
        )
        self.send_thread.start()
    
    def _send_loop(self):
        """Loop de envío asíncrono - NO BLOQUEA el hilo principal"""
        while self.send_running and self.status == 1:
            try:
                # Esperar paquete con timeout
                data = self.send_queue.get(timeout=0.5)
                if data is None:  # Señal de parada
                    break
                
                # Envío con select para no bloquear
                self._send_with_select(data)
                self.send_queue.task_done()
                
            except Empty:
                continue
            except Exception as e:
                if config.DEBUG:
                    logger.debug(f"Send loop error {self.id[:8]}: {e}")
    
    def _send_with_select(self, data: bytes) -> bool:
        """✅ FASE 2: Envío no bloqueante con select"""
        if self.status == 0 or not data or not self.socket:
            return False
        
        try:
            total_sent = 0
            data_len = len(data)
            
            while total_sent < data_len:
                # Esperar que socket esté listo para escribir (max 100ms)
                _, writable, errors = select.select([], [self.socket], [self.socket], 0.1)
                
                if errors:
                    self.consecutive_send_failures += 1
                    return False
                
                if writable:
                    try:
                        sent = self.socket.send(data[total_sent:])
                        if sent == 0:
                            self.consecutive_send_failures += 1
                            return False
                        total_sent += sent
                    except (BlockingIOError, socket.error):
                        continue
                else:
                    # Timeout - socket no disponible
                    self.consecutive_send_failures += 1
                    self.packets_dropped += 1
                    return False
            
            self.packets_sent += 1
            self.consecutive_send_failures = 0
            self.update_activity()
            return True
            
        except Exception as e:
            if config.DEBUG:
                logger.debug(f"Send error {self.id[:8]}: {e}")
            self.consecutive_send_failures += 1
            return False
    
    def is_alive(self, timeout: float = 30.0) -> bool:
        """✅ FIXED: Verificar que el cliente está REALMENTE vivo"""
        if self.status == 0:
            return False
        
        # ✅ Verificar socket
        if not self._is_socket_alive():
            return False
        
        # ✅ Verificar actividad reciente
        time_since_activity = time.time() - self.last_activity
        if time_since_activity > timeout:
            logger.warning(f"⚠️ Cliente {self.id[:15]} inactivo por {time_since_activity:.1f}s")
            return False
        
        # ✅ Verificar fallos consecutivos
        if self.consecutive_send_failures >= self.max_consecutive_failures:
            logger.warning(f"⚠️ Cliente {self.id[:15]} con {self.consecutive_send_failures} fallos consecutivos")
            return False
        
        return True
    
    def _is_socket_alive(self) -> bool:
        """✅ NUEVO: Verificar si socket está realmente conectado"""
        try:
            # Usar select con timeout 0 para verificar si socket está listo
            import select
            _, writable, errors = select.select([], [self.socket], [self.socket], 0)
            
            if errors:
                logger.debug(f"Socket {self.id[:15]} tiene errores")
                return False
            
            # Verificar si socket está cerrado
            if self.socket.fileno() == -1:
                logger.debug(f"Socket {self.id[:15]} cerrado")
                return False
            
            return True
            
        except (OSError, ValueError, AttributeError):
            return False
    
    def send_bytes_direct(self, data: bytes) -> bool:
        """✅ FASE 2: Envío asíncrono via cola - NO BLOQUEA"""
        if self.status == 0 or not data:
            return False
        
        if not self._is_socket_alive():
            self.status = 0
            self.consecutive_send_failures += 1
            return False
        
        try:
            # ✅ FASE 2: Encolar sin bloquear - descarta si cola llena
            self.send_queue.put_nowait(data)
            return True
        except Full:
            # Cola llena - descartar paquete más antiguo y encolar nuevo
            try:
                self.send_queue.get_nowait()  # Descartar antiguo
                self.packets_dropped += 1
            except Empty:
                pass
            try:
                self.send_queue.put_nowait(data)
                return True
            except Full:
                self.packets_dropped += 1
                return False
    
    def send_bytes_sync(self, data: bytes) -> bool:
        """Envío síncrono para mensajes de control (handshake, etc)"""
        if self.status == 0 or not data:
            return False
        
        if not self._is_socket_alive():
            self.status = 0
            return False
        
        try:
            # Temporalmente bloquear socket para envío síncrono
            self.socket.setblocking(True)
            self.socket.settimeout(1.0)
            try:
                self.socket.sendall(data)
                self.packets_sent += 1
                self.consecutive_send_failures = 0
                self.update_activity()
                return True
            finally:
                self.socket.setblocking(False)
                
        except socket.timeout:
            self.consecutive_send_failures += 1
            return False
        except (BrokenPipeError, ConnectionError, OSError) as e:
            logger.warning(f"⚠️ Conexión perdida con {self.id[:15]}: {e}")
            self.status = 0
            return False
        except Exception as e:
            if config.DEBUG:
                logger.warning(f"⚠️ {self.id[:15]} - Error envío sync: {e}")
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

    def send_mix_state(self, subscription: dict) -> bool:
        """Enviar estado de mezcla al cliente nativo (control packet).

        El Android renderer decide cómo aplicar (gain/pan/active).
        """
        try:
            if not subscription or self.status == 0:
                return False

            channels = subscription.get('channels', []) or []
            gains = subscription.get('gains', {}) or {}
            pans = subscription.get('pans', {}) or {}
            mutes = subscription.get('mutes', {}) or {}
            pre_listen = subscription.get('pre_listen', None)
            solos = list(subscription.get('solos', set()) or [])
            master_gain = subscription.get('master_gain', 1.0)

            payload = {
                'channels': [int(ch) for ch in channels],
                'gains': {str(int(k)): float(v) for k, v in gains.items()},
                'pans': {str(int(k)): float(v) for k, v in pans.items()},
                'mutes': {str(int(k)): bool(v) for k, v in mutes.items()},
                'pre_listen': pre_listen,
                'solos': [int(ch) for ch in solos],
                'master_gain': float(master_gain),
            }

            packet = NativeAndroidProtocol.create_control_packet(
                'mix_state',
                payload,
                self.rf_mode,
            )
            if not packet:
                return False

            # ✅ FASE 2: Mensajes de control síncronos (garantizados)
            return self.send_bytes_sync(packet)

        except Exception as e:
            if config.DEBUG:
                logger.error(f"❌ Error enviando mix_state a {self.id[:15]}: {e}")
            return False
    
    def close(self):
        """✅ MEJORADO: Cierre robusto y garantizado de recursos"""
        connection_duration = time.time() - self.connection_time
        logger.info(f"🔌 {self.id[:15]} - Duración: {connection_duration:.1f}s, "
                   f"Enviados: {self.packets_sent}, Perdidos: {self.packets_dropped}, "
                   f"Reconexiones: {self.reconnection_count}")
        self.status = 0
        
        # ✅ FIX: Detener thread de envío ANTES de cerrar socket
        self.send_running = False
        try:
            self.send_queue.put_nowait(None)  # Señal de parada
        except:
            pass
        
        # Esperar que termine el thread (con timeout corto)
        if self.send_thread and self.send_thread.is_alive():
            try:
                self.send_thread.join(timeout=0.5)
            except:
                pass
        
        # ✅ FIX: Cerrar socket con shutdown explícito (más robusto)
        if self.socket:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
            except (OSError, BrokenPipeError):
                pass  # Socket ya cerrado o error al cerrar
            
            try:
                self.socket.close()
            except (OSError, BrokenPipeError):
                pass
            
            self.socket = None
        
        logger.debug(f"✅ {self.id[:15]} - Recursos liberados correctamente")


class NativeAudioServer:
    def __init__(self, channel_manager):
        self.channel_manager = channel_manager
        self.channel_manager.native_server = self
        self.running = False
        self.server_socket = None
        self.clients = {}
        self.client_lock = threading.RLock()
        self.accept_thread = None
        self.maintenance_thread = None
        
        self.persistent_state = defaultdict(dict)
        self.persistent_lock = threading.Lock()
        self.STATE_CACHE_TIMEOUT = getattr(config, 'RF_STATE_CACHE_TIMEOUT', 300)
        self.MAX_PERSISTENT_STATES = 50
        
        self.sample_position_lock = threading.Lock()
        self.sample_position = 0
        
        self.physical_channels = 0
        
        # ✅ FASE 2: Cache de paquetes por grupo de canales
        self._packet_cache = {}  # {frozenset(channels): (packet_bytes, sample_position)}
        self._cache_lock = threading.Lock()
        
        self.stats = {
            'packets_sent': 0,
            'packets_dropped': 0,
            'clients_connected': 0,
            'clients_disconnected': 0,
            'clients_reconnected': 0,
            'clients_zombie_killed': 0,
            'cache_hits': 0,  # ✅ FASE 2: Estadísticas de cache
            'cache_misses': 0,
            'bytes_sent': 0,
            'uptime': 0,
            'cached_states': 0
        }
        self.start_time = time.time()
        self.stats_lock = threading.Lock()
    
    def set_physical_channels(self, num_channels: int):
        """✅ NUEVO: Establecer número de canales reales del dispositivo"""
        self.physical_channels = num_channels
        logger.info(f"[NativeServer] 📊 Canales físicos del dispositivo: {num_channels}")
    
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
        logger.info(f"🟢 SERVIDOR RF MODO RECEPTOR PURO - FIXED")
        logger.info(f"{'='*70}")
        logger.info(f"   🌐 Host: {config.NATIVE_HOST}:{config.NATIVE_PORT}")
        logger.info(f"   📦 BLOCKSIZE: {config.BLOCKSIZE} samples (~{config.BLOCKSIZE/config.SAMPLE_RATE*1000:.2f}ms)")
        logger.info(f"   🎵 SAMPLE_RATE: {config.SAMPLE_RATE} Hz")
        logger.info(f"   🔌 Socket TIMEOUT: 5s (REDUCED)")
        logger.info(f"   🔄 Auto-reconexión: ENABLED")
        logger.info(f"   💾 Estado cache: {self.STATE_CACHE_TIMEOUT}s (Max: {self.MAX_PERSISTENT_STATES})")
        logger.info(f"   ✅ Zombie detection: ENABLED")
        logger.info(f"{'='*70}\n")
    
    def _maintenance_loop(self):
        """✅ IMPROVED: Mantenimiento más agresivo"""
        while self.running:
            time.sleep(10)  # ✅ REDUCIDO: Cada 10s (era 30s)
            
            try:
                current_time = time.time()
                
                # ✅ 1. Limpiar estado persistente expirado (si timeout > 0)
                with self.persistent_lock:
                    if self.STATE_CACHE_TIMEOUT and self.STATE_CACHE_TIMEOUT > 0:
                        expired = [
                            pid for pid, state in self.persistent_state.items()
                            if current_time - state.get('last_seen', 0) > self.STATE_CACHE_TIMEOUT
                        ]
                        for pid in expired:
                            logger.info(f"🗑️ Limpiando estado expirado: {pid[:15]}")
                            del self.persistent_state[pid]
                    
                    # ✅ 2. Limitar cantidad de estados guardados
                    if len(self.persistent_state) > self.MAX_PERSISTENT_STATES:
                        # Eliminar los más antiguos
                        sorted_states = sorted(
                            self.persistent_state.items(),
                            key=lambda x: x[1].get('last_seen', 0)
                        )
                        to_remove = len(self.persistent_state) - self.MAX_PERSISTENT_STATES
                        for pid, _ in sorted_states[:to_remove]:
                            logger.info(f"🗑️ Limpiando estado por límite: {pid[:15]}")
                            del self.persistent_state[pid]
                
                # ✅ 3. Verificar y eliminar clientes zombies
                with self.client_lock:
                    clients_to_remove = []
                    
                    for client_id, client in list(self.clients.items()):
                        # ✅ Verificar si está realmente vivo
                        if not client.is_alive(timeout=30.0):
                            logger.warning(f"💀 Cliente zombie detectado: {client_id[:15]}")
                            clients_to_remove.append(client_id)
                            self.stats['clients_zombie_killed'] += 1
                    
                    # ✅ Eliminar zombies
                    for client_id in clients_to_remove:
                        client = self.clients.get(client_id)
                        preserve = client.auto_reconnect if client else False
                        self._disconnect_client(client_id, preserve_state=preserve)
                
                # ✅ 4. Actualizar estadísticas
                with self.stats_lock:
                    self.stats['uptime'] = int(time.time() - self.start_time)
                    self.stats['cached_states'] = len(self.persistent_state)
                
                # ✅ 5. Log periódico
                active_clients = len([c for c in self.clients.values() if c.status == 1])
                logger.info(f"📊 Clientes activos: {active_clients}, Zombies eliminados: {self.stats['clients_zombie_killed']}")
                    
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
        
        if getattr(self.channel_manager, 'native_server', None) is self:
            self.channel_manager.native_server = None

        stats = self.get_stats()
        uptime = time.time() - self.start_time
        logger.info("🛑 Servidor RF detenido")
        logger.info(f"📊 Stats - Uptime: {uptime:.1f}s")
        logger.info(f"   Clientes: {stats['clients_connected']} (Reconexiones: {stats['clients_reconnected']})")
        logger.info(f"   Zombies eliminados: {stats['clients_zombie_killed']}")
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
                    break
                
                magic, version, typeAndFlags, timestamp, payloadLength = struct.unpack('!IHHII', header_data)
                msgType = (typeAndFlags >> 8) & 0xFF
                
                if magic != NativeAndroidProtocol.MAGIC_NUMBER:
                    consecutive_errors += 1
                    if config.DEBUG:
                        logger.warning(f"⚠️ Magic inválido #{consecutive_errors} - {client_id[:15]}")

                    if consecutive_errors >= 3:  # ⚠️ REDUCIDO: 5 → 3 intentos antes de sincronizar
                        logger.info(f"🔄 Intentando resincronización... ({client_id[:15]})")
                        # ✅ FIX: Buscar siguiente MAGIC válido en el stream
                        synced_header = self._sync_to_magic(client.socket, timeout=2.0)
                        if synced_header:
                            header_data = synced_header
                            magic, version, typeAndFlags, timestamp, payloadLength = struct.unpack('!IHHII', header_data)
                            msgType = (typeAndFlags >> 8) & 0xFF
                            consecutive_errors = 0
                            logger.info(f"✅ Resincronizado: {client_id[:15]}")
                        else:
                            logger.warning(f"❌ No se pudo resincronizar - {client_id[:15]}")
                            break
                    else:
                        time.sleep(0.05)  # ⚠️ REDUCIDO: 0.1s → 0.05s (más rápido)
                        continue
                
                consecutive_errors = 0
                
                max_payload = NativeAndroidProtocol.MAX_CONTROL_PAYLOAD
                if payloadLength < 0 or payloadLength > max_payload:
                    if config.DEBUG:
                        logger.error(f"❌ Payload inválido: {payloadLength}")
                    continue
                
                payload = b''
                if payloadLength > 0:
                    payload = self._recv_exact(client.socket, payloadLength)
                    if not payload or len(payload) != payloadLength: 
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
                break
        
        self._disconnect_client(client_id, preserve_state=client.auto_reconnect)
    
    def _sync_to_magic(self, sock: socket.socket, timeout: float = 2.0) -> bytes:
        """
        ✅ FIX: Buscar MAGIC_NUMBER en el stream para resincronización automática.
        Si hay datos corruptos o fuera de sincronización, encuentra el próximo frame válido.
        
        Retorna: 16 bytes del header con MAGIC al inicio, o None si timeout
        """
        MAGIC_NUMBER = NativeAndroidProtocol.MAGIC_NUMBER
        MAGIC_BYTES = struct.pack('!I', MAGIC_NUMBER)
        buffer = b''
        start = time.time()
        
        while time.time() - start < timeout:
            try:
                byte_chunk = sock.recv(1)
                if not byte_chunk:
                    return None
                
                buffer += byte_chunk
                
                # Buscar MAGIC_NUMBER en los últimos 4 bytes
                if len(buffer) >= 4:
                    last_4 = buffer[-4:]
                    if last_4 == MAGIC_BYTES:
                        # ✅ MAGIC encontrado! Leer 12 bytes más para completar header
                        magic = last_4
                        rest = sock.recv(12)  # Leer resto del header
                        if len(rest) == 12:
                            return magic + rest
                        else:
                            return None
                    
                    # Limpiar buffer si crece demasiado (evitar memory leak)
                    if len(buffer) > 10000:
                        buffer = buffer[-4:]
                        if config.DEBUG:
                            logger.warning(f"Buffer de sincronización limpiado (datos corruptos?)")
                            
            except socket.timeout:
                continue
            except (ConnectionError, BrokenPipeError, OSError):
                return None
            except Exception as e:
                if config.DEBUG:
                    logger.debug(f"Sync error: {e}")
                return None
        
        if config.DEBUG:
            logger.warning(f"⚠️ Timeout sincronizando a MAGIC (buffer: {len(buffer)} bytes)")
        return None
    
    def _recv_exact(self, sock: socket.socket, size: int):
        """✅ FIX: Timeout más agresivo (2s en lugar de 10s) para detección rápida de errores"""
        data = b''
        timeout = 2.0  # ⚠️ REDUCIDO: 10s → 2s (detección rápida)
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
            # ✅ Preferir device_uuid si viene; fallback a client_id
            persistent_id = message.get('device_uuid') or message.get('client_id')
            raw_client_id = message.get('client_id')

            if not persistent_id:
                logger.error(f"❌ Handshake sin client_id UUID desde {client.address}")
                return
            
            # ✅ Detectar si es reconexión TEMPRANO para usarlo en lógica de mapeo
            is_reconnection = False
            with self.client_lock:
                if persistent_id in self.clients:
                    is_reconnection = True

            # ✅ Registrar/actualizar dispositivo en DeviceRegistry (si existe)
            try:
                if getattr(self.channel_manager, 'device_registry', None):
                    self.channel_manager.device_registry.register_device(persistent_id, {
                        'type': 'android',
                        'name': message.get('device_name') or message.get('name') or f"android-{persistent_id[:8]}",
                        'primary_ip': client.address[0],
                        'client_id': raw_client_id,
                        'protocol_version': message.get('protocol_version'),
                        'rf_mode': message.get('rf_mode', False),
                        'user_agent': message.get('user_agent')
                    })
            except Exception as e:
                logger.debug(f"DeviceRegistry register failed: {e}")
            
            # ✅ NUEVO: Mapear dispositivo a canales lógicos automáticamente
            # Si es la primera conexión (no es reconexión), asignar canales automáticamente
            try:
                num_physical_channels = message.get('num_channels', 0)
                if num_physical_channels > 0 and not is_reconnection:
                    device_mapping = self.channel_manager.register_device_to_channels(
                        persistent_id,
                        num_physical_channels
                    )
                    if device_mapping.get('operacional'):
                        logger.info(
                            f"[NativeServer] 🔗 Dispositivo {persistent_id[:12]} mapeado: "
                            f"{num_physical_channels} canales físicos -> "
                            f"Canales lógicos {device_mapping['start_channel']}-"
                            f"{device_mapping['start_channel'] + device_mapping['num_channels'] - 1}"
                        )
            except Exception as e:
                logger.debug(f"Device channel mapping failed: {e}")

            # ✅ FIXED: Cerrar cliente viejo ANTES de sobrescribir
            old_temp_id = client.id

            with self.client_lock:
                # ✅ Si ya existe, CERRAR el socket viejo
                if persistent_id in self.clients:
                    old_client = self.clients[persistent_id]
                    
                    logger.info(f"🔄 Reconexión detectada: {persistent_id[:15]}")
                    logger.info(f"   Cerrando conexión anterior...")
                    
                    # ✅ CERRAR socket viejo
                    try:
                        old_client.status = 0
                        old_client.close()
                    except Exception as e:
                        logger.warning(f"⚠️ Error cerrando cliente viejo: {e}")

            # Cambiar ID del cliente
            client.id = persistent_id
            client.persistent_id = persistent_id
            client.is_temp_id = False

            # ✅ Actualizar diccionario de clientes
            with self.client_lock:
                # Remover entrada temporal
                if old_temp_id in self.clients and old_temp_id != persistent_id:
                    del self.clients[old_temp_id]

                # ✅ AGREGAR/SOBRESCRIBIR con nuevo cliente
                self.clients[persistent_id] = client

            logger.info(f"✅ ID actualizado: {old_temp_id[:25]} → {persistent_id[:15]}")

            client.rf_mode = message.get('rf_mode', False)
            client.persistent = message.get('persistent', False)
            client.auto_reconnect = message.get('auto_reconnect', False)

            logger.info(f"🤝 {client.id[:15]} - HANDSHAKE: "
                       f"reconnection={is_reconnection}, "
                       f"auto_reconnect={client.auto_reconnect}")

            # Buscar estado persistente
            restored_state = None
            if client.auto_reconnect:
                with self.persistent_lock:
                    if persistent_id in self.persistent_state:
                        restored_state = self.persistent_state[persistent_id]
                        logger.info(f"💾 Estado restaurado para: {persistent_id[:15]}")
                        self.persistent_state[persistent_id]['last_seen'] = time.time()

            # ✅ MEJORADO: restaurar desde DeviceRegistry SIN restricción de session_id (persistencia permanente)
            if restored_state is None and getattr(self.channel_manager, 'device_registry', None):
                try:
                    # ✅ Obtener configuración sin restricción de sesión para persistencia permanente
                    disk_state = self.channel_manager.device_registry.get_configuration(persistent_id)
                    if disk_state:
                        restored_state = disk_state
                        logger.info(f"💾 ✅ Estado restaurado PERMANENTEMENTE desde DeviceRegistry: {persistent_id[:15]} - {len(disk_state.get('channels', []))} canales")
                except Exception as e:
                    logger.debug(f"DeviceRegistry restore failed: {e}")

            if restored_state is not None and is_reconnection:
                client.reconnection_count = restored_state.get('reconnection_count', 0) + 1
                self.stats['clients_reconnected'] += 1

            # Registrar en channel_manager
            channels_to_subscribe = []
            if restored_state and 'channels' in restored_state:
                channels_to_subscribe = restored_state['channels']
                logger.info(f"📡 Canales restaurados: {len(channels_to_subscribe)} canales")

            self.channel_manager.subscribe_client(
                persistent_id,
                channels_to_subscribe,
                client_type="native",
                device_uuid=persistent_id
            )

            # Aplicar estado restaurado
            if restored_state:
                self.channel_manager.update_client_mix(
                    persistent_id,
                    gains=restored_state.get('gains', {}),
                    pans=restored_state.get('pans', {}),
                    mutes=restored_state.get('mutes', {}),
                    solos=restored_state.get('solos', []),
                    pre_listen=restored_state.get('pre_listen'),
                    master_gain=restored_state.get('master_gain', 1.0)
                )

            # Enviar respuesta
            response = NativeAndroidProtocol.create_control_packet(
                'handshake_response',
                {
                    'server_version': '2.5.0-RF-FIXED',
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
                    'persistent_id': persistent_id,
                    'is_reconnection': is_reconnection
                },
                client.rf_mode
            )
            
            if response:
                # ✅ FASE 2: Handshake siempre síncrono
                client.send_bytes_sync(response)

            # ✅ NUEVO: Enviar estado completo de mezcla para que el Android aplique
            try:
                subscription = self.channel_manager.get_client_subscription(persistent_id)
                if subscription:
                    client.send_mix_state(subscription)
            except Exception as e:
                if config.DEBUG:
                    logger.debug(f"mix_state send failed: {e}")
            
            self._notify_web_clients_update()
        
        elif msg_type == 'heartbeat':
            # ✅ FIX: Responder heartbeat INMEDIATAMENTE con retry logic
            response = NativeAndroidProtocol.create_control_packet(
                'heartbeat_response',
                {
                    'timestamp': int(time.time() * 1000),
                    'clients_connected': len(self.clients)
                },
                client.rf_mode
            )
            if response:
                # ✅ FIX: Intentar envío sync CON REINTENTOS
                max_attempts = 3
                for attempt in range(max_attempts):
                    if client.send_bytes_sync(response):
                        if config.DEBUG:
                            logger.debug(f"💓 Heartbeat response enviado a {client.id[:15]}")
                        break
                    else:
                        if attempt < max_attempts - 1:
                            time.sleep(0.05)  # Esperar 50ms antes de reintentar
                        else:
                            logger.warning(f"⚠️ No se pudo enviar heartbeat response a {client.id[:15]}")

        elif msg_type == 'update_mix':
            # ✅ Permitir que el cliente Android controle su propia mezcla (ON/gain/pan)
            try:
                persistent_id = getattr(client, 'persistent_id', None) or client.id

                channels = message.get('channels')
                gains = message.get('gains')
                pans = message.get('pans')

                def _int_keyed_map(m):
                    if not isinstance(m, dict):
                        return None
                    out = {}
                    for k, v in m.items():
                        try:
                            out[int(k)] = float(v)
                        except Exception:
                            continue
                    return out

                gains_int = _int_keyed_map(gains)
                pans_int = _int_keyed_map(pans)

                ok = self.channel_manager.update_client_mix(
                    persistent_id,
                    channels=channels,
                    gains=gains_int,
                    pans=pans_int,
                )

                if ok:
                    # ✅ NUEVO: Persistir el estado para que sea global y durable (igual que en WebSocket)
                    try:
                        subscription = self.channel_manager.get_client_subscription(persistent_id)
                        device_uuid = None
                        if subscription:
                            device_uuid = subscription.get('device_uuid') or persistent_id

                        if device_uuid and getattr(self.channel_manager, 'device_registry', None):
                            config_to_save = {
                                'channels': subscription.get('channels', []) if subscription else [],
                                'gains': subscription.get('gains', {}) if subscription else {},
                                'pans': subscription.get('pans', {}) if subscription else {},
                                'mutes': subscription.get('mutes', {}) if subscription else {},
                                'solos': list(subscription.get('solos', set())) if subscription else [],
                                'pre_listen': subscription.get('pre_listen') if subscription else None,
                                'master_gain': subscription.get('master_gain', 1.0) if subscription else 1.0,
                                'timestamp': int(time.time() * 1000)
                            }
                            self.channel_manager.device_registry.update_configuration(device_uuid, config_to_save)
                    except Exception as e:
                        if config.DEBUG:
                            logger.debug(f"DeviceRegistry update (native update_mix) failed: {e}")

                    # refrescar web y devolver estado al propio Android
                    self._notify_web_clients_update()
                    try:
                        subscription = self.channel_manager.get_client_subscription(persistent_id)
                        if subscription:
                            client.send_mix_state(subscription)
                    except Exception:
                        pass
            except Exception as e:
                if config.DEBUG:
                    logger.error(f"❌ update_mix error: {e}")
    
    def _notify_web_clients_update(self):
        try:
            from audio_server import websocket_server
            websocket_server.broadcast_clients_update()
        except Exception as e:
            if config.DEBUG:
                logger.error(f"Error notificando web: {e}")
    
    def broadcast_control_update(self, channel: int, source: str, gain: float = None, pan: float = None, active: bool = None, mute: bool = None):
        """
        ✅ NUEVO: Propagar cambio de control a todos los clientes nativos conectados
        Usado cuando web UI cambia un control y necesitamos sincronizar Android
        """
        try:
            control_data = {
                'type': 'control_update',
                'source': source,
                'channel': channel,
                'timestamp': int(time.time() * 1000)
            }
            
            if gain is not None:
                control_data['gain'] = gain
            if pan is not None:
                control_data['pan'] = pan
            if active is not None:
                control_data['active'] = active
            if mute is not None:
                control_data['mute'] = mute
            
            packet = NativeAndroidProtocol.create_control_packet('control_update', control_data, True)
            if not packet:
                return
            
            # ✅ FASE 2: Snapshot de clientes y envío síncrono
            with self.client_lock:
                active_clients = [(cid, c) for cid, c in self.clients.items() if c.status == 1 and c.is_alive()]
            
            for client_id, client in active_clients:
                try:
                    client.send_bytes_sync(packet)
                except Exception as e:
                    if config.DEBUG:
                        logger.debug(f"Error enviando control_update a {client_id[:12]}: {e}")
            
            logger.debug(f"📢 Control broadcast: ch={channel}, source={source}")
            
        except Exception as e:
            if config.DEBUG:
                logger.error(f"Error en broadcast_control_update: {e}")

    def push_mix_state_to_client(self, client_id: str) -> bool:
        """Enviar el estado de mezcla actual a un cliente nativo conectado."""
        try:
            subscription = self.channel_manager.get_client_subscription(client_id)
            if not subscription:
                return False

            with self.client_lock:
                client = self.clients.get(client_id)
                if not client:
                    return False
                return client.send_mix_state(subscription)
        except Exception as e:
            if config.DEBUG:
                logger.error(f"❌ push_mix_state_to_client({client_id[:12]}) failed: {e}")
            return False
    
    def on_audio_data(self, audio_data):
        """✅ FASE 2: Envío optimizado con cache de paquetes y menos contención"""
        if not self.running:
            return
        
        if isinstance(audio_data, memoryview):
            audio_data = np.frombuffer(audio_data, dtype=np.float32).reshape(-1, self.channel_manager.num_channels)
        
        samples = audio_data.shape[0]
        current_position = self.increment_sample_position(samples)
        
        # ✅ FASE 2: Tomar snapshot de clientes con lock mínimo
        with self.client_lock:
            active_clients = [
                (client_id, client, self.channel_manager.get_client_subscription(client_id))
                for client_id, client in self.clients.items()
                if client.status == 1
            ]
        
        if not active_clients:
            return
        
        # ✅ FASE 2: Limpiar cache del frame anterior
        self._packet_cache.clear()
        
        clients_to_remove = []
        sent = 0
        
        # ✅ FASE 2: Procesar sin lock global
        for client_id, client, subscription in active_clients:
            if not client.is_alive():
                clients_to_remove.append(client_id)
                continue
            
            if not subscription:
                continue
            
            channels = subscription.get('channels', [])
            if not channels:
                continue
            
            # ✅ FASE 2: Usar cache de paquetes por grupo de canales
            channel_key = frozenset(channels)
            
            cached = self._packet_cache.get(channel_key)
            if cached:
                packet_bytes = cached
                self.update_stats(cache_hits=1)
            else:
                # Crear paquete y cachear
                valid_channels = sorted([ch for ch in channels if ch < audio_data.shape[1]])
                if not valid_channels:
                    continue
                    
                packet_bytes = NativeAndroidProtocol.create_audio_packet(
                    audio_data, valid_channels, current_position, 0, client.rf_mode
                )
                
                if packet_bytes:
                    self._packet_cache[channel_key] = packet_bytes
                    self.update_stats(cache_misses=1)
                else:
                    continue
            
            client.subscribed_channels = set(channels)
            
            try:
                if client.send_bytes_direct(packet_bytes):
                    sent += 1
                else:
                    if client.consecutive_send_failures >= client.max_consecutive_failures:
                        clients_to_remove.append(client_id)
                    self.update_stats(packets_dropped=1)
            except Exception as e:
                if config.DEBUG:
                    logger.error(f"❌ Envío {client_id[:15]}: {e}")
                clients_to_remove.append(client_id)
        
        # ✅ FASE 2: Limpiar clientes muertos con lock
        if clients_to_remove:
            for client_id in clients_to_remove:
                with self.client_lock:
                    client = self.clients.get(client_id)
                if client:
                    preserve = client.auto_reconnect
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
                            self.persistent_state[client.persistent_id]['last_seen'] = time.time()

                logger.info(f"🔌 Desconectado: {client_id[:15]} (reconnect={preserve_state})")
                client.close()

                self.channel_manager.unsubscribe_client(client_id)
                self._notify_client_disconnected(client_id)

    def _notify_client_disconnected(self, client_id):
        try:
            from audio_server import websocket_server
            websocket_server.socketio.emit('client_disconnected', {
                'client_id': client_id,
                'timestamp': int(time.time() * 1000)
            })  # Eliminado broadcast=True
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