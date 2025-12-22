"""

Channel Manager - GestiÃ³n de suscripciones y procesamiento de canales

CORREGIDO: AlineaciÃ³n correcta de datos float32, mejor manejo de ganancias

"""



import numpy as np

import struct

import config



class ChannelManager:

    def __init__(self, num_channels):

        self.num_channels = num_channels

        # Dict: client_id -> {channels: [list], gains: {ch: gain}}

        self.subscriptions = {}

        

    def subscribe_client(self, client_id, channels, gains=None):

        """Cliente se suscribe a canales especÃ­ficos"""

        if gains is None:

            gains = {ch: 1.0 for ch in channels}

        

        self.subscriptions[client_id] = {

            'channels': channels,

            'gains': gains

        }

        

        if config.VERBOSE:

            print(f"[+] Cliente {client_id[:8]}... suscrito a {len(channels)} canales")

    

    def unsubscribe_client(self, client_id):

        """Cliente se desuscribe"""

        if client_id in self.subscriptions:

            del self.subscriptions[client_id]

            if config.VERBOSE:

                print(f"[-] Cliente {client_id[:8]}... desuscrito")

    

    def update_gain(self, client_id, channel, gain):

        """Actualiza ganancia de un canal para un cliente"""

        if client_id in self.subscriptions:

            self.subscriptions[client_id]['gains'][channel] = gain

    

    def process_audio(self, audio_data):

        """

        Procesa audio y devuelve dict por cliente

        CORREGIDO: Formato binario con alineaciÃ³n correcta

        

        Args:

            audio_data: numpy array (frames, channels) en float32 [-1.0, 1.0]

        

        Returns:

            dict: {client_id: [binary_packet1, binary_packet2, ...]}

        """

        processed = {}

        

        for client_id, sub in self.subscriptions.items():

            client_audio = []

            

            for channel in sub['channels']:

                if channel >= self.num_channels:

                    continue

                

                # Extraer canal especÃ­fico

                channel_data = audio_data[:, channel].copy()

                

                # Aplicar ganancia con NumPy (vectorizado)

                gain = sub['gains'].get(channel, 1.0)

                

                if gain != 1.0:

                    channel_data *= gain

                    

                    # Soft clipping para evitar distorsiÃ³n

                    # Limitar a [-1.0, 1.0] con tanh suave

                    channel_data = np.clip(channel_data, -1.0, 1.0)

                

                # CORREGIDO: Formato binario con alineaciÃ³n correcta

                # [channel_id (uint32 alineado)][float32 array]

                # Usar uint32 asegura alineaciÃ³n de 4 bytes

                binary_data = struct.pack('I', channel) + channel_data.astype(np.float32).tobytes()

                client_audio.append(binary_data)

            

            if client_audio:

                processed[client_id] = client_audio

        

        return processed

    

    def get_active_channels(self):

        """Devuelve set de todos los canales activos"""

        active = set()

        for sub in self.subscriptions.values():

            active.update(sub['channels'])

        return active

    

    def get_client_count(self):

        """Retorna nÃºmero de clientes conectados"""

        return len(self.subscriptions)

    

    def get_total_channel_count(self):

        """Retorna total de canales activos entre todos los clientes"""

        total = 0

        for sub in self.subscriptions.values():

            total += len(sub['channels'])

        return total