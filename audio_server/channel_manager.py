# channel_manager.py

import config

import logging

import time

from audio_server.websocket_server import app



logger = logging.getLogger(__name__)



class ChannelManager:

    """

    ✅ GESTOR MEJORADO: Control centralizado desde Web

    - Mezclas individuales por cliente

    - Pre-escucha (PFL)

    - Solo/Mute

    - Ganancias y panoramas

    """

    def __init__(self, num_channels):

        self.num_channels = num_channels

        self.subscriptions = {}  # client_id -> subscription_data

        self.client_types = {}   # client_id -> "native" | "web"

        # ✅ socketio se inyecta desde websocket_server

        self.socketio = None

        print(f"[ChannelManager] ✅ Inicializado: {num_channels} canales")

    

    def set_socketio(self, socketio_instance):

        """✅ Método para inyectar socketio después de inicialización"""

        self.socketio = socketio_instance

        logger.info("[ChannelManager] ✅ SocketIO registrado")

    

    def subscribe_client(self, client_id, channels, gains=None, pans=None, client_type="web"):

        """

        Suscribir cliente con configuración de mezcla

        

        Args:

            client_id: ID del cliente

            channels: Lista de canales (puede estar vacía para Android)

            gains: Dict {channel: gain_linear}

            pans: Dict {channel: pan}

            client_type: "native" (Android) o "web"

        """

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

            'last_update': time.time()

        }

        

        self.client_types[client_id] = client_type

        

        logger.info(f"[ChannelManager] 📡 Cliente {client_id[:8]} ({client_type}) suscrito:")

        logger.info(f"   Canales: {len(valid_channels)}")

    

    def unsubscribe_client(self, client_id):

        """Desuscribir cliente"""

        if client_id in self.subscriptions:

            channels_count = len(self.subscriptions[client_id]['channels'])

            client_type = self.client_types.get(client_id, "unknown")

            del self.subscriptions[client_id]

            self.client_types.pop(client_id, None)

            logger.info(f"[ChannelManager] 📡 Cliente {client_id[:8]} ({client_type}) desuscrito ({channels_count} canales)")

    

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

            for ch, gain in gains.items():

                if 0 <= ch < self.num_channels:

                    sub['gains'][ch] = max(0.0, min(float(gain), 10.0))

        

        # ✅ Validar y actualizar pans (limitar -1.0 - 1.0)

        if pans is not None:

            for ch, pan in pans.items():

                if 0 <= ch < self.num_channels:

                    sub['pans'][ch] = max(-1.0, min(float(pan), 1.0))

        

        # ✅ Validar y actualizar mutes

        if mutes is not None:

            for ch, mute in mutes.items():

                if 0 <= ch < self.num_channels:

                    sub['mutes'][ch] = bool(mute)

        

        # ✅ Validar y actualizar solos

        if solos is not None:

            valid_solos = [ch for ch in solos if 0 <= ch < self.num_channels]

            sub['solos'] = set(valid_solos)

        

        # ✅ Validar y actualizar pre_listen

        if pre_listen is not None:

            if pre_listen == -1 or (0 <= pre_listen < self.num_channels):

                sub['pre_listen'] = pre_listen

            elif pre_listen is None:

                sub['pre_listen'] = None

        

        # ✅ Validar y actualizar master_gain (limitar 0.0 - 5.0)

        if master_gain is not None:

            sub['master_gain'] = max(0.0, min(float(master_gain), 5.0))

        

        sub['last_update'] = time.time()

        

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

                with app.app_context():

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

        

        for client_id, sub in self.subscriptions.items():

            client_type = self.client_types.get(client_id, "unknown")

            

            clients_info.append({

                'id': client_id,

                'type': client_type,

                'channels': sub['channels'],

                'active_channels': len(sub['channels']),

                'has_solo': len(sub.get('solos', set())) > 0,

                'pre_listen': sub.get('pre_listen'),

                'master_gain': sub.get('master_gain', 1.0),

                'last_update': sub.get('last_update', 0)

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