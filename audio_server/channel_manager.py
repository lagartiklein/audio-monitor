# channel_manager.py

import config

import logging

import time



logger = logging.getLogger(__name__)



class ChannelManager:

    """

    ✅ GESTOR MEJORADO: Control centralizado desde Web

    - Mezclas individuales por cliente

    - Pre-escucha (PFL)

    - Solo/Mute

    - Ganancias y panoramas
    
    ✅ NUEVO: Integración con Device Registry para identificación persistente
    
    ✅ NUEVO: Mapeo automático de interfaces físicas a canales lógicos

    """

    def __init__(self, num_channels):
        # Usar el número de canales real de la interfaz
        self.num_channels = num_channels

        self.subscriptions = {}  # client_id -> subscription_data

        self.client_types = {}   # client_id -> "native" | "web"

        # ✅ socketio se inyecta desde websocket_server

        self.socketio = None
        
        # ✅ NUEVO: Device registry para ID persistente
        self.device_registry = None
        self.device_client_map = {}  # device_uuid -> client_id (mapeo activo)

        # ✅ NUEVO: Session ID del servidor (cambia en cada arranque)
        self.server_session_id = None
        
        # ✅ NUEVO: Mapeo de interfaces físicas a canales lógicos
        self.device_channel_map = {}  # device_uuid -> {'start_channel': int, 'num_channels': int, 'physical_channels': int}
        self.next_available_channel = 0  # Próximo canal disponible para asignar

        print(f"[ChannelManager] ✅ Inicializado: {num_channels} canales")

    

    def set_socketio(self, socketio_instance):

        """✅ Método para inyectar socketio después de inicialización"""

        self.socketio = socketio_instance

        logger.info("[ChannelManager] ✅ SocketIO registrado")
    
    def set_device_registry(self, device_registry):
        """✅ NUEVO: Inyectar device registry"""
        self.device_registry = device_registry
        logger.info("[ChannelManager] ✅ Device Registry registrado")

    def set_server_session_id(self, session_id: str):
        """✅ NUEVO: Session ID del servidor (cambia en cada arranque)."""
        self.server_session_id = session_id
        logger.info(f"[ChannelManager] 🧷 Server session: {session_id[:12]}")
    
    def register_device_to_channels(self, device_uuid: str, physical_channels: int) -> dict:
        """
        ✅ NUEVO: Mapear dispositivo físico a canales lógicos automáticamente
        
        Si una interfaz tiene 8 canales y es la primera, se asigna a canales 0-7
        Si otra interfaz tiene 16 canales, se asigna a canales 8-23, etc
        
        Args:
            device_uuid: UUID único del dispositivo
            physical_channels: Número de canales del dispositivo físico
            
        Returns:
            {
                'start_channel': int,      # Canal inicial asignado
                'num_channels': int,       # Número de canales asignados
                'physical_channels': int,  # Canales del dispositivo físico
                'operacional': bool        # Si hay canales dentro del rango 0-47
            }
        """
        if device_uuid in self.device_channel_map:
            # Ya está mapeado, retornar mapeo existente
            return self.device_channel_map[device_uuid]
        
        # Calcular canales disponibles
        # Asignar solo los canales realmente disponibles
        channels_needed = min(physical_channels, self.num_channels - self.next_available_channel)
        
        if channels_needed <= 0:
            logger.warning(f"[ChannelManager] ⚠️ No hay canales disponibles para {device_uuid[:12]}")
            return {
                'start_channel': -1,
                'num_channels': 0,
                'physical_channels': physical_channels,
                'operacional': False
            }
        
        # Mapear este dispositivo
        mapping = {
            'start_channel': self.next_available_channel,
            'num_channels': channels_needed,
            'physical_channels': physical_channels,
            'operacional': True
        }
        
        self.device_channel_map[device_uuid] = mapping
        self.next_available_channel += channels_needed
        
        logger.info(
            f"[ChannelManager] 🔗 Dispositivo mapeado: {device_uuid[:12]} "
            f"({physical_channels} canales físicos) -> "
            f"Canales lógicos {mapping['start_channel']}-{mapping['start_channel'] + channels_needed - 1}"
        )
        
        # ✅ NUEVO: Notificar al socketio sobre cambio de canales operacionales
        if self.socketio:
            try:
                self.socketio.emit(
                    'operational_channels_updated',
                    {
                        'operational_channels': list(self.get_operational_channels()),
                        'device_uuid': device_uuid,
                        'mapping': mapping
                    },
                    broadcast=True
                )
                logger.debug(f"[ChannelManager] 📢 Notificado cambio de canales operacionales")
            except Exception as e:
                logger.debug(f"[ChannelManager] ⚠️ Error notificando: {e}")
        
        return mapping
    
    def get_device_channel_map(self, device_uuid: str) -> dict:
        """Obtener mapeo de canales para un dispositivo"""
        return self.device_channel_map.get(device_uuid, {
            'start_channel': -1,
            'num_channels': 0,
            'physical_channels': 0,
            'operacional': False
        })
    
    def get_operational_channels(self) -> set:
        """
        ✅ NUEVO: Obtener conjunto de canales que tienen dispositivos físicos asignados
        Útil para marcar canales operacionales en la UI
        """
        operational = set()
        for mapping in self.device_channel_map.values():
            if mapping.get('operacional'):
                start = mapping['start_channel']
                num = mapping['num_channels']
                operational.update(range(start, start + num))
        return operational

    

    def subscribe_client(self, client_id, channels, gains=None, pans=None, client_type="web", device_uuid=None):

        """

        Suscribir cliente con configuración de mezcla

        

        Args:

            client_id: ID del cliente (temporal o socket ID)
            
            channels: Lista de canales (puede estar vacía para Android)

            gains: Dict {channel: gain_linear}

            pans: Dict {channel: pan}

            client_type: "native" (Android) o "web"
            
            device_uuid: ✅ NUEVO - UUID único del dispositivo

        """

        # ✅ NUEVO: Convertir canales a int si vienen como strings
        try:
            channels = [int(ch) for ch in channels]
        except (ValueError, TypeError):
            channels = []
        
        # ✅ VALIDAR canales dentro del rango permitido

        valid_channels = [ch for ch in channels if 0 <= ch < self.num_channels]

        

        if gains is None:

            gains = {ch: 1.0 for ch in valid_channels}

        

        if pans is None:

            pans = {ch: 0.0 for ch in valid_channels}

        

        # ✅ Inicializar mutes para los canales válidos

        mutes = {}

        for ch in valid_channels:

            mutes[ch] = False

        

        self.subscriptions[client_id] = {

            'channels': valid_channels,

            'gains': gains,

            'pans': pans,

            'mutes': mutes,

            'solos': set(),

            'pre_listen': None,

            'master_gain': 1.0,

            'client_type': client_type,
            'device_uuid': device_uuid,  # ✅ NUEVO

            'last_update': time.time()

        }

        

        self.client_types[client_id] = client_type
        
        # ✅ NUEVO: Mapear device_uuid -> client_id si está disponible
        if device_uuid:
            self.device_client_map[device_uuid] = client_id

            # ✅ Registrar/actualizar dispositivo en el registry
            if self.device_registry:
                try:
                    self.device_registry.register_device(device_uuid, {
                        'type': client_type,
                        'name': f"{client_type}-{device_uuid[:8]}",
                        'primary_ip': None
                    })
                except Exception as e:
                    logger.debug(f"[ChannelManager] Device registry register failed: {e}")

        

        logger.info(f"[ChannelManager] 📡 Cliente {client_id[:8]} ({client_type}) suscrito:")

        logger.info(f"   Canales: {len(valid_channels)}")
        
        if device_uuid:
            logger.info(f"   Device UUID: {device_uuid[:12]}")

    

    def unsubscribe_client(self, client_id):

        """Desuscribir cliente"""

        if client_id in self.subscriptions:

            channels_count = len(self.subscriptions[client_id]['channels'])

            client_type = self.client_types.get(client_id, "unknown")
            
            # ✅ NUEVO: Remover del mapeo de device_uuid
            device_uuid = self.subscriptions[client_id].get('device_uuid')
            if device_uuid and self.device_client_map.get(device_uuid) == client_id:
                del self.device_client_map[device_uuid]

            del self.subscriptions[client_id]

            self.client_types.pop(client_id, None)

            logger.info(f"[ChannelManager] 📡 Cliente {client_id[:8]} ({client_type}) desuscrito ({channels_count} canales)")
    
    def get_client_by_device_uuid(self, device_uuid):
        """✅ NUEVO: Buscar client_id por device_uuid"""
        return self.device_client_map.get(device_uuid)

    

    def update_client_mix(self, client_id, channels=None, gains=None, pans=None, 

                          mutes=None, solos=None, pre_listen=None, master_gain=None):

        """

        ✅ MEJORADO: Actualizar mezcla de un cliente con validaciones

        """

        if client_id not in self.subscriptions:

            logger.warning(f"[ChannelManager] Cliente {client_id[:8]} no encontrado")

            return False

        

        sub = self.subscriptions[client_id]

        

        # ✅ Validar y actualizar canales

        if channels is not None:

            # ✅ NUEVO: Convertir a int si vienen como strings
            try:
                channels = [int(ch) for ch in channels]
            except (ValueError, TypeError):
                channels = []
            
            # Filtrar canales válidos

            valid_channels = [ch for ch in channels if 0 <= ch < self.num_channels]

            sub['channels'] = valid_channels

            

            # Asegurar que existen gains y pans para los nuevos canales

            for ch in valid_channels:

                if ch not in sub['gains']:

                    sub['gains'][ch] = 1.0

                if ch not in sub['pans']:

                    sub['pans'][ch] = 0.0

                if ch not in sub['mutes']:

                    sub['mutes'][ch] = False

        

        # ✅ Validar y actualizar gains (limitar 0.0 - 10.0)

        if gains is not None:

            # ✅ NUEVO: Convertir claves a int y valores a float
            for ch_raw, gain in gains.items():

                try:
                    ch = int(ch_raw)
                    if 0 <= ch < self.num_channels:

                        sub['gains'][ch] = max(0.0, min(float(gain), 10.0))
                except (ValueError, TypeError):
                    pass

        

        # ✅ Validar y actualizar pans (limitar -1.0 - 1.0)

        if pans is not None:

            # ✅ NUEVO: Convertir claves a int y valores a float
            for ch_raw, pan in pans.items():

                try:
                    ch = int(ch_raw)
                    if 0 <= ch < self.num_channels:

                        sub['pans'][ch] = max(-1.0, min(float(pan), 1.0))
                except (ValueError, TypeError):
                    pass

        

        # ✅ Validar y actualizar mutes

        if mutes is not None:

            # ✅ NUEVO: Convertir claves a int
            for ch_raw, mute in mutes.items():

                try:
                    ch = int(ch_raw)
                    if 0 <= ch < self.num_channels:

                        sub['mutes'][ch] = bool(mute)
                except (ValueError, TypeError):
                    pass

        

        # ✅ Validar y actualizar solos

        if solos is not None:

            # ✅ NUEVO: Convertir a int si vienen como strings
            try:
                solos = [int(ch) for ch in solos]
            except (ValueError, TypeError):
                solos = []
            
            valid_solos = [ch for ch in solos if 0 <= ch < self.num_channels]

            sub['solos'] = set(valid_solos)

        

        # ✅ Validar y actualizar pre_listen

        if pre_listen is not None:

            # ✅ NUEVO: Convertir a int si viene como string
            try:
                pre_listen = int(pre_listen)
            except (ValueError, TypeError):
                pre_listen = -1
            
            if pre_listen == -1 or (0 <= pre_listen < self.num_channels):

                sub['pre_listen'] = pre_listen

            elif pre_listen is None:

                sub['pre_listen'] = None

        

        # ✅ Validar y actualizar master_gain (limitar 0.0 - 5.0)

        if master_gain is not None:

            sub['master_gain'] = max(0.0, min(float(master_gain), 5.0))

        

        sub['last_update'] = time.time()

        # ✅ MEJORADO: Persistir estado por dispositivo (sin restricción de sesión para persistencia permanente)
        device_uuid = sub.get('device_uuid')
        if device_uuid and self.device_registry:
            try:
                self.device_registry.update_configuration(
                    device_uuid,
                    {
                        'channels': sub.get('channels', []),
                        'gains': sub.get('gains', {}),
                        'pans': sub.get('pans', {}),
                        'mutes': sub.get('mutes', {}),
                        'solos': list(sub.get('solos', set())),
                        'pre_listen': sub.get('pre_listen'),
                        'master_gain': sub.get('master_gain', 1.0),
                        'timestamp': int(time.time() * 1000)
                    }
                    # ✅ Sin session_id - persistencia permanente aunque servidor reinicie
                )
                logger.debug(f"[ChannelManager] 💾 Config persistida para {device_uuid[:12]}")
            except Exception as e:
                logger.debug(f"[ChannelManager] Persist config failed: {e}")

        

        if config.DEBUG:

            logger.debug(f"[ChannelManager] Mezcla actualizada para {client_id[:8]}")

        

        # ✅ Manejo de solos: Silenciar otros canales si hay canales en solo

        if sub['solos']:

            for ch in range(self.num_channels):

                sub['mutes'][ch] = ch not in sub['solos']



        # ✅ Manejo de pre_listen: Asegurar que solo el canal seleccionado esté activo

        if sub['pre_listen'] is not None:

            for ch in range(self.num_channels):

                sub['mutes'][ch] = ch != sub['pre_listen']



        # ✅ CORREGIDO: Emitir sin 'broadcast' parameter

        if self.socketio:

            try:

                self.socketio.emit('mix_updated', {

                    'client_id': client_id,

                    'channels': sub['channels'],

                    'gains': sub['gains'],

                    'pans': sub['pans'],

                    'mutes': sub['mutes'],

                    'solos': list(sub['solos']),

                    'pre_listen': sub['pre_listen'],

                    'master_gain': sub['master_gain']

                })  # ✅ SIN broadcast=True

            except Exception as e:

                logger.error(f"[ChannelManager] Error emitiendo mix_updated: {e}")

        

        return True

    

    def get_client_subscription(self, client_id):

        """Obtener suscripción completa de un cliente"""

        return self.subscriptions.get(client_id, None)

    

    def should_send_channel(self, client_id, channel):

        """

        Determinar si se debe enviar un canal a un cliente

        """

        if client_id not in self.subscriptions:

            return False

        

        subscription = self.subscriptions[client_id]

        

        # Pre-escucha tiene prioridad

        if subscription.get('pre_listen') is not None:

            return channel == subscription['pre_listen']

        

        # Si hay solos activos, solo enviar esos canales

        solos = subscription.get('solos', set())

        if solos:

            return channel in solos

        

        # Verificar mute

        mutes = subscription.get('mutes', {})

        if mutes.get(channel, False):

            return False

        

        # Verificar que esté suscrito al canal

        return channel in subscription.get('channels', [])

    

    def get_channel_gain(self, client_id, channel):

        """Obtener ganancia efectiva de un canal para un cliente"""

        if client_id not in self.subscriptions:

            return 0.0

        

        subscription = self.subscriptions[client_id]

        

        # Pre-escucha: ganancia fija

        if subscription.get('pre_listen') == channel:

            return 1.0

        

        # Ganancia del canal

        channel_gain = subscription.get('gains', {}).get(channel, 1.0)

        

        # Ganancia master

        master_gain = subscription.get('master_gain', 1.0)

        

        return channel_gain * master_gain

    

    def get_channel_pan(self, client_id, channel):

        """Obtener panorama de un canal para un cliente"""

        if client_id not in self.subscriptions:

            return 0.0

        

        subscription = self.subscriptions[client_id]

        return subscription.get('pans', {}).get(channel, 0.0)

    

    def get_all_clients_info(self):
        """
        ✅ NUEVO: Obtener info de todos los clientes
        """
        clients_info = []

        # Obtener clientes nativos conectados (si hay native_server)
        connected_native_ids = set()
        if hasattr(self, 'native_server') and self.native_server:
            with self.native_server.client_lock:
                connected_native_ids = set(self.native_server.clients.keys())

        # Los clientes web activos se consideran conectados si están en subscriptions
        connected_web_ids = set(
            client_id for client_id, t in self.client_types.items() if t == 'web'
        )

        for client_id, sub in self.subscriptions.items():
            client_type = self.client_types.get(client_id, "unknown")
            device_uuid = sub.get('device_uuid')

            # ✅ Obtener device_model y custom_name desde device_registry
            device_model = None
            custom_name = None
            device_name = None
            if device_uuid and self.device_registry:
                try:
                    device_info = self.device_registry.get_device(device_uuid)
                    if device_info:
                        device_model = device_info.get('device_info', {}).get('model') or \
                                      device_info.get('device_info', {}).get('device_model')
                        custom_name = device_info.get('custom_name')
                        device_name = device_info.get('name')
                except Exception as e:
                    logger.debug(f"[ChannelManager] Error getting device info: {e}")

            # Determinar si está conectado
            connected = False
            if client_type == 'native':
                connected = client_id in connected_native_ids
            elif client_type == 'web':
                connected = client_id in connected_web_ids

            clients_info.append({
                'id': client_id,
                'type': client_type,
                'device_uuid': device_uuid,
                'device_model': device_model,
                'custom_name': custom_name,
                'device_name': device_name,
                'channels': sub['channels'],
                'gains': sub['gains'],
                'pans': sub['pans'],
                'solos': list(sub.get('solos', set())),  # ✅ Incluir solos como lista
                'active_channels': len(sub['channels']),
                'has_solo': len(sub.get('solos', set())) > 0,
                'pre_listen': sub.get('pre_listen'),
                'master_gain': sub.get('master_gain', 1.0),
                'last_update': sub.get('last_update', 0),
                'connected': connected
            })
        return clients_info

    

    def get_stats(self):

        """Obtener estadísticas del gestor"""

        total_clients = len(self.subscriptions)

        native_clients = sum(1 for t in self.client_types.values() if t == "native")

        web_clients = sum(1 for t in self.client_types.values() if t == "web")

        

        total_channels_subscribed = sum(

            len(sub['channels']) for sub in self.subscriptions.values()

        )

        

        clients_with_solo = sum(

            1 for sub in self.subscriptions.values() 

            if sub.get('solos')

        )

        

        clients_with_pre_listen = sum(

            1 for sub in self.subscriptions.values() 

            if sub.get('pre_listen') is not None

        )

        

        return {

            'total_clients': total_clients,

            'native_clients': native_clients,

            'web_clients': web_clients,

            'total_channels_subscribed': total_channels_subscribed,

            'clients_with_solo': clients_with_solo,

            'clients_with_pre_listen': clients_with_pre_listen,

            'available_channels': self.num_channels

        }