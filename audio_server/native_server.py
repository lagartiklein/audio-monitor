import socket, select, threading, time, json, struct, numpy as np, logging, sys, os

from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import config

import queue  # <-- IMPORTANTE: Agregar esta línea

from audio_server.native_protocol import NativeAndroidProtocol



# Configurar logging

logging.basicConfig(

    level=logging.INFO,

    format='%(asctime)s - %(levelname)s - %(message)s',

    datefmt='%H:%M:%S'

)

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

        self.connect_time = datetime.now().strftime('%H:%M:%S')

        self.rf_mode = False  # Modo RF activado por defecto

        try:

            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

            self.socket.settimeout(10.0)

        except Exception as e:

            logger.warning(f"⚠️  Error configurando socket para {client_id[:15]}: {e}")

    

    def update_heartbeat(self): 

        self.last_heartbeat = time.time()

    

    def is_alive(self, timeout: float = 30.0) -> bool: 

        return time.time() - self.last_heartbeat < timeout

    

    def send_bytes(self, data: bytes) -> bool:

        try:

            total_sent = 0

            while total_sent < len(data):

                sent = self.socket.send(data[total_sent:])

                if sent == 0: 

                    logger.warning(f"⚠️  Socket cerrado al enviar para {self.id[:15]}")

                    return False

                total_sent += sent

            return True

        except Exception as e:

            logger.error(f"❌ Error enviando datos a {self.id[:15]}: {e}")

            self.status = 0

            return False

    

    def send_audio_android(self, audio_data: np.ndarray, sample_position: int) -> bool:

        if not self.subscribed_channels: 

            return True

        

        try:

            channels = sorted(list(self.subscribed_channels))

            logger.debug(f"🎵 {self.id[:15]} - Preparando audio: {len(channels)} canales, {audio_data.shape[0]} samples")

            

            # ⭐ USAR MODO RF SI ESTÁ ACTIVADO

            packet_bytes = NativeAndroidProtocol.create_audio_packet(

                audio_data, 

                channels, 

                sample_position, 

                self.audio_sequence,

                self.rf_mode  # ⭐ Pasar modo RF al protocolo

            )

            

            # Verificar que el paquete tenga el magic number correcto

            if len(packet_bytes) >= 4:

                received_magic = struct.unpack('!I', packet_bytes[:4])[0]

                if received_magic != NativeAndroidProtocol.MAGIC_NUMBER:

                    logger.error(f"❌ {self.id[:15]} - Magic inválido en paquete generado: 0x{received_magic:08x}")

                    return False

            

            success = self.send_bytes(packet_bytes)

            if success: 

                self.audio_sequence += 1

                logger.debug(f"📤 {self.id[:15]} - Audio enviado: {len(packet_bytes)} bytes")

            return success

            

        except Exception as e:

            logger.error(f"❌ {self.id[:15]} - Error creando paquete de audio: {e}")

            import traceback

            traceback.print_exc()

            return False

    

    def send_handshake_response(self, capture_channels: int):

        try:

            response_data = {

                'server_version': '2.1.0',

                'protocol_version': NativeAndroidProtocol.PROTOCOL_VERSION,

                'sample_rate': 48000,

                'max_channels': capture_channels,

                'session_id': self.id,

                'status': 'ready',

                'timestamp': int(time.time() * 1000),

                'block_size': config.BLOCKSIZE,

                'rf_mode': self.rf_mode  # ⭐ INFORMAR AL CLIENTE

            }

            

            response = NativeAndroidProtocol.create_control_packet(

                'handshake_response', 

                response_data,

                self.rf_mode  # ⭐ Pasar flag RF al protocolo

            )

            success = self.send_bytes(response)

            

            if success:

                logger.info(f"📤 Handshake enviado a {self.id[:15]}")

            else:

                logger.error(f"❌ Falló envío de handshake a {self.id[:15]}")

            

            return success

        except Exception as e:

            logger.error(f"❌ Error en handshake para {self.id[:15]}: {e}")

            return False

    

    def send_subscribe_response(self, channels: list):

        try:

            response_data = {

                'channels': channels,

                'timestamp': int(time.time() * 1000),

                'status': 'success'

            }

            response = NativeAndroidProtocol.create_control_packet('subscribed', response_data)

            success = self.send_bytes(response)

            

           

            

            return success

        except Exception as e:

            logger.error(f"❌ Error en subscribe response para {self.id[:15]}: {e}")

            return False

    

    def close(self):

        try:

            if self.socket: 

                self.socket.close()

                logger.debug(f"🔌 Socket cerrado para {self.id[:15]}")

        except Exception as e:

            logger.debug(f"⚠️  Error cerrando socket {self.id[:15]}: {e}")

        finally:

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

        self.stats = {

            'start_time': datetime.now().strftime('%H:%M:%S'),

            'total_clients': 0,

            'active_clients': 0,

            'total_packets_sent': 0,

            'audio_errors': 0,

            'bytes_sent': 0,

            'last_audio_time': 0

        }

        logger.info("🎵 Servidor nativo inicializado")

    

    def start(self):

        if self.running: 

            logger.warning("⚠️  Servidor ya está corriendo")

            return

        

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

            

            logger.info(f"🟢 SERVIDOR INICIADO en {config.NATIVE_HOST}:{config.NATIVE_PORT}")

            logger.info(f"📡 Esperando conexiones de clientes Android...")

            

        except Exception as e:

            logger.error(f"❌ Error iniciando servidor: {e}")

            raise

    

    def stop(self):

        logger.info("🛑 Deteniendo servidor nativo...")

        self.running = False

        

        # Desconectar todos los clientes

        with self.client_lock:

            client_count = len(self.clients)

            if client_count > 0:

                logger.info(f"🔌 Desconectando {client_count} cliente(s)...")

                for client_id, client in list(self.clients.items()):

                    logger.info(f"   ➖ Desconectando: {client_id[:15]}")

                    client.close()

                self.clients.clear()

                self.stats['active_clients'] = 0

        

        # Cerrar socket del servidor

        if self.server_socket:

            try:

                self.server_socket.close()

            except:

                pass

        

        # Esperar threads

        for thread in [self.accept_thread, self.audio_thread]:

            if thread and thread.is_alive():

                thread.join(timeout=2)

        

        # Mostrar estadísticas finales

        uptime = datetime.now().strftime('%H:%M:%S')

        logger.info(f"📊 ESTADÍSTICAS FINALES:")

        logger.info(f"   ⏱️  Inicio: {self.stats['start_time']} - Fin: {uptime}")

        logger.info(f"   👥 Clientes totales: {self.stats['total_clients']}")

        logger.info(f"   📦 Paquetes de audio enviados: {self.stats['total_packets_sent']:,}")

        logger.info(f"   📊 Bytes enviados: {self.stats['bytes_sent']:,}")

        logger.info(f"   ❌ Errores de audio: {self.stats['audio_errors']}")

        

        logger.info("✅ Servidor nativo detenido")

    

    def _accept_loop(self):

        logger.info("🔍 Escuchando conexiones entrantes...")

        while self.running:

            try:

                readable, _, _ = select.select([self.server_socket], [], [], 0.5)

                for sock in readable:

                    if sock is self.server_socket:

                        client_socket, address = self.server_socket.accept()

                        client_id = f"android_{address[0]}_{int(time.time() * 1000)}"

                        client_ip = address[0]

                        

                        # Crear cliente

                        client = NativeClient(

                            client_id, 

                            client_socket, 

                            address, 

                            self.channel_manager.num_channels

                        )

                        

                        with self.client_lock:

                            self.clients[client_id] = client

                            self.stats['total_clients'] += 1

                            self.stats['active_clients'] += 1

                        

                        # Mostrar conexión

                        current_time = datetime.now().strftime('%H:%M:%S')

                        logger.info(f"✅ NUEVO CLIENTE CONECTADO:")

                        logger.info(f"   🔗 ID: {client_id[:15]}")

                        logger.info(f"   🌐 IP: {client_ip}")

                        logger.info(f"   ⏰ Hora: {current_time}")

                        logger.info(f"   👥 Clientes activos: {self.stats['active_clients']}/{config.NATIVE_MAX_CLIENTS}")

                        

                        # Iniciar thread de lectura para este cliente

                        read_thread = threading.Thread(

                            target=self._client_read_loop, 

                            args=(client_id,),

                            daemon=True, 

                            name=f"NativeRead_{client_id[:8]}"

                        )

                        read_thread.start()

                        

            except Exception as e:

                if self.running:

                    logger.error(f"❌ Error en accept loop: {e}")

    

    def _client_read_loop(self, client_id: str):

        client = self.clients.get(client_id)

        if not client: 

            return

        

        HEADER_SIZE = 16

        consecutive_errors = 0

        bytes_received = 0

        messages_received = 0

        

        logger.info(f"📖 Iniciando lectura para {client_id[:15]}")

        

        while self.running and client.status != 0:

            try:

                # Leer header

                header_data = self._recv_exact(client.socket, HEADER_SIZE)

                if not header_data:

                    logger.warning(f"⚠️  Conexión cerrada por {client_id[:15]}")

                    break

                

                bytes_received += len(header_data)

                

                try:

                        # Decodificar header (nuevo formato)

                        magic, version, typeAndFlags, timestamp, payloadLength = struct.unpack('!IHHII', header_data)

                        msgType = (typeAndFlags >> 8) & 0xFF

                        flags = typeAndFlags & 0xFF

                        sequence = 0  # RF no usa sequence

                        messages_received += 1

                    

                        logger.debug(f"📦 {client_id[:15]} - Header: magic=0x{magic:08x}, type={msgType}, payload={payloadLength}")

                    

                        # Validar magic number

                        if magic != NativeAndroidProtocol.MAGIC_NUMBER:

                            logger.error(f"❌ {client_id[:15]} - Magic inválido: 0x{magic:08x} esperado: 0x{NativeAndroidProtocol.MAGIC_NUMBER:08x}")

                            consecutive_errors += 1

                            if consecutive_errors >= 3: 

                                logger.warning(f"⚠️  {client_id[:15]} - Demasiados errores, desconectando")

                                break

                            continue

                    

                        consecutive_errors = 0

                    

                        # Leer payload si existe

                        payload = b''

                        if payloadLength > 0:

                            if payloadLength > 1024 * 1024:  # 1MB máximo

                                logger.error(f"❌ {client_id[:15]} - Payload demasiado grande: {payloadLength} bytes")

                                break

                        

                            payload = self._recv_exact(client.socket, payloadLength)

                            if not payload:

                                logger.error(f"❌ {client_id[:15]} - Error leyendo payload")

                                break

                        

                            bytes_received += len(payload)

                    

                        # Procesar mensaje

                        if msgType == NativeAndroidProtocol.MSG_TYPE_CONTROL:

                            try:

                                message = json.loads(payload.decode('utf-8'))

                                msg_type_str = message.get('type', 'unknown')

                                logger.info(f"📨 {client_id[:15]} - Control recibido: {msg_type_str}")

                                self._handle_control_message(client, message)

                            except Exception as e:

                                logger.error(f"❌ {client_id[:15]} - Error procesando control: {e}")

                    

                        elif msgType == NativeAndroidProtocol.MSG_TYPE_AUDIO:

                            logger.debug(f"🎵 {client_id[:15]} - Audio recibido: {payloadLength} bytes")

                    

                        else:

                            logger.warning(f"⚠️  {client_id[:15]} - Tipo de mensaje desconocido: {msgType}")

                

                except struct.error as e:

                    logger.error(f"❌ {client_id[:15]} - Error decodificando header: {e}")

                    consecutive_errors += 1

                    if consecutive_errors >= 3: break

                    continue

                

                # Actualizar heartbeat

                client.update_heartbeat()

                

            except socket.timeout: 

                continue

            except (ConnectionError, BrokenPipeError, OSError) as e:

                logger.warning(f"⚠️  {client_id[:15]} - Error de conexión: {e}")

                break

            except Exception as e:

                logger.error(f"❌ {client_id[:15]} - Error en read loop: {e}")

                break

        

        # Estadísticas de este cliente

        duration = time.time() - (client.last_heartbeat - 30)  # Estimación

        logger.info(f"📊 {client_id[:15]} - ESTADÍSTICAS:")

        logger.info(f"   📥 Bytes recibidos: {bytes_received:,}")

        logger.info(f"   📨 Mensajes recibidos: {messages_received}")

        logger.info(f"   ⏱️  Duración aproximada: {duration:.1f}s")

        

        self._disconnect_client(client_id)

    

    def _recv_exact(self, sock: socket.socket, size: int):

        data = b''

        start_time = time.time()

        while len(data) < size and (time.time() - start_time) < 5.0:  # 5 segundos timeout

            try:

                chunk = sock.recv(size - len(data))

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

            logger.info(f"🤝 {client.id[:15]} - HANDSHAKE recibido")

            

            # Verificar versión de protocolo

            client_version = message.get('protocol_version', 1)

            if client_version != NativeAndroidProtocol.PROTOCOL_VERSION:

                logger.error(f"❌ {client.id[:15]} - Versión incompatible: cliente={client_version}, servidor={NativeAndroidProtocol.PROTOCOL_VERSION}")

                client.close()

                return

            

            # ⭐ DETECTAR MODO RF DEL CLIENTE

            client.rf_mode = message.get('rf_mode', False)

            if client.rf_mode:

                logger.info(f"⭐ {client.id[:15]} - CLIENTE EN MODO RF")

                client.socket.settimeout(2.0)  # Timeout más corto

            else:

                logger.info(f"📱 {client.id[:15]} - Cliente en modo normal")

            

            client.authenticated = True

            client.status = 2

            

            # Enviar respuesta (INCLUIR rf_mode en respuesta)

            success = client.send_handshake_response(self.audio_capture.actual_channels)

            

            if success:

                logger.info(f"✅ {client.id[:15]} - Handshake completado exitosamente")

                logger.info(f"   📊 Canales disponibles: {self.audio_capture.actual_channels}")

                logger.info(f"   ⚙️  Protocolo: v{NativeAndroidProtocol.PROTOCOL_VERSION}")

            else:

                logger.error(f"❌ {client.id[:15]} - Falló handshake")

                client.close()

                

        elif msg_type == 'subscribe':

            channels = message.get('channels', [])

            logger.info(f"📡 {client.id[:15]} - SUBSCRIBE recibido: {channels}")

            

            # Validar canales

            valid = [ch for ch in channels if 0 <= ch < self.audio_capture.actual_channels]

            if valid:

                client.subscribed_channels = set(valid)

                success = client.send_subscribe_response(valid)

                

                if success:

                    logger.info(f"✅ {client.id[:15]} - Suscrito a canales: {valid}")

                    logger.info(f"   🎚️  Canales activos: {len(valid)}/{self.audio_capture.actual_channels}")

                else:

                    logger.error(f"❌ {client.id[:15]} - Error enviando confirmación de suscripción")

                

                # Registrar en channel manager

                self.channel_manager.subscribe_client(client.id, valid, {ch: 1.0 for ch in valid})

            else:

                logger.warning(f"⚠️  {client.id[:15]} - No hay canales válidos en la suscripción")

                

        elif msg_type == 'heartbeat':

            client.update_heartbeat()

            logger.debug(f"💓 {client.id[:15]} - Heartbeat recibido")

            

        elif msg_type == 'unsubscribe':

            logger.info(f"📡 {client.id[:15]} - UNSUBSCRIBE recibido")

            client.subscribed_channels.clear()

            self.channel_manager.unsubscribe_client(client.id)

            

        else:

            logger.warning(f"⚠️  {client.id[:15]} - Tipo de mensaje desconocido: '{msg_type}'")

    

    def _audio_distribution_loop(self):

        logger.info("🎵 Iniciando distribución de audio...")

        consecutive_errors = 0

        sample_position = 0

        last_stats_time = time.time()

        packets_this_interval = 0

        last_packet_time = time.time()

        

        while self.running:

            try:

                # Obtener audio

                if self.use_broadcaster and self.audio_queue:

                    try: 

                        audio_data = self.audio_queue.get(timeout=0.01)

                    except queue.Empty:

                        continue

                else:

                    audio_data = self.audio_capture.get_audio_data(timeout=0.01)

                

                if audio_data is None or audio_data.size == 0:

                    consecutive_errors += 1

                    if consecutive_errors > 100: 

                        logger.warning("⚠️  Muchos errores consecutivos en audio")

                        time.sleep(0.1)

                    continue

                

                consecutive_errors = 0

                sample_position += audio_data.shape[0]

                packets_this_interval += 1

                

                # Enviar a cada cliente

                with self.client_lock:

                    if not self.clients: 

                        continue

                    

                    clients_to_remove = []

                    active_clients = 0

                    sending_clients = 0

                    

                    for client_id, client in self.clients.items():

                        if client.status == 0:

                            clients_to_remove.append(client_id)

                            continue

                        

                        active_clients += 1

                        

                        if not client.is_alive():

                            logger.warning(f"⚠️  {client_id[:15]} - Timeout, desconectando")

                            clients_to_remove.append(client_id)

                            continue

                        

                        if not client.subscribed_channels or not client.authenticated:

                            continue

                        

                        sending_clients += 1

                        

                        try:

                            success = client.send_audio_android(audio_data, sample_position)

                            last_packet_time = time.time()

                            

                            if success: 

                                self.stats['total_packets_sent'] += 1

                                if audio_data.shape[0] > 0 and len(client.subscribed_channels) > 0:

                                    bytes_estimate = len(client.subscribed_channels) * audio_data.shape[0] * 4

                                    self.stats['bytes_sent'] += bytes_estimate

                            else:

                                self.stats['audio_errors'] += 1

                                logger.error(f"❌ {client_id[:15]} - Falló envío de audio")

                                clients_to_remove.append(client_id)

                                

                        except Exception as e:

                            logger.error(f"❌ {client_id[:15]} - Error enviando audio: {e}")

                            self.stats['audio_errors'] += 1

                            clients_to_remove.append(client_id)

                    

                    # Desconectar clientes problemáticos

                    for client_id in clients_to_remove:

                        self._disconnect_client(client_id)

                    

                    # Log de estadísticas periódicas

                    current_time = time.time()

                    if current_time - last_stats_time >= 5.0:

                        if sending_clients > 0:

                            logger.info(f"📊 ESTADO AUDIO:")

                            logger.info(f"   👥 Clientes activos: {active_clients}")

                            logger.info(f"   🎵 Enviando audio a: {sending_clients}")

                            logger.info(f"   📦 Paquetes totales: {self.stats['total_packets_sent']:,}")

                            logger.info(f"   📈 Bytes enviados: {self.stats['bytes_sent']:,}")

                            logger.info(f"   ⏱️  Último paquete: {current_time - last_packet_time:.2f}s atrás")

                        

                        packets_this_interval = 0

                        last_stats_time = current_time

                

            except Exception as e:

                logger.error(f"❌ Error en distribución de audio: {e}")

                consecutive_errors += 1

                if consecutive_errors >= 10:

                    logger.error("❌ Demasiados errores en distribución de audio")

                    time.sleep(1.0)

                time.sleep(0.01)

        

        logger.info("🛑 Distribución de audio detenida")

    

    def _disconnect_client(self, client_id: str):

        with self.client_lock:

            client = self.clients.pop(client_id, None)

            if client:

                current_time = datetime.now().strftime('%H:%M:%S')

                duration = "desconocida"

                try:

                    connect_time_obj = datetime.strptime(client.connect_time, '%H:%M:%S')

                    disconnect_time_obj = datetime.strptime(current_time, '%H:%M:%S')

                    duration_seconds = (disconnect_time_obj - connect_time_obj).seconds

                    duration = f"{duration_seconds // 60}:{duration_seconds % 60:02d}"

                except:

                    pass

                

                logger.info(f"❌ CLIENTE DESCONECTADO:")

                logger.info(f"   🔗 ID: {client_id[:15]}")

                logger.info(f"   🌐 IP: {client.address[0]}")

                logger.info(f"   ⏰ Conexión: {client.connect_time} - Desconexión: {current_time}")

                logger.info(f"   ⏱️  Duración: {duration}")

                logger.info(f"   👥 Clientes restantes: {len(self.clients)}/{config.NATIVE_MAX_CLIENTS}")

                

                client.close()

                self.channel_manager.unsubscribe_client(client_id)

                self.stats['active_clients'] -= 1

    

    def print_status(self):

        """Función para imprimir estado actual del servidor"""

        with self.client_lock:

            current_time = datetime.now().strftime('%H:%M:%S')

            logger.info(f"📡 ESTADO DEL SERVIDOR - {current_time}")

            logger.info(f"   🟢 Servidor: {'ACTIVO' if self.running else 'INACTIVO'}")

            logger.info(f"   👥 Clientes conectados: {len(self.clients)}")

            

            if self.clients:

                logger.info(f"   📋 LISTA DE CLIENTES:")

                for i, (client_id, client) in enumerate(self.clients.items(), 1):

                    status_text = "AUTENTICADO" if client.authenticated else "CONECTADO"

                    channels_text = f"{len(client.subscribed_channels)} canales" if client.subscribed_channels else "sin suscripción"

                    idle_time = int(time.time() - client.last_heartbeat)

                    

                    logger.info(f"   {i:2d}. {client_id[:15]} - {status_text}")

                    logger.info(f"        IP: {client.address[0]}, {channels_text}")

                    logger.info(f"        ⏰ Conectado: {client.connect_time}, ⏳ Idle: {idle_time}s")

            

            logger.info(f"   📊 Paquetes enviados: {self.stats['total_packets_sent']:,}")

            logger.info(f"   📈 Bytes enviados: {self.stats['bytes_sent']:,}")

            logger.info(f"   ⚠️  Errores: {self.stats['audio_errors']}")