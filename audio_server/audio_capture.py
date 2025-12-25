"""

Audio Capture - âœ… ADAPTATIVO al hardware real

Detecta sample rate y blocksize del hardware y ajusta configuraciÃ³n

"""



import sounddevice as sd

import numpy as np

import queue

import threading

import time

import sys

import os



sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import config



class AudioCapture:

    def __init__(self):

        self.device_info = None

        self.stream = None

        self.audio_queue = queue.Queue(maxsize=config.QUEUE_SIZE)

        self.running = False

        self.actual_sample_rate = None

        self.actual_blocksize = None  # âœ… Guardar blocksize real

        

        # EstadÃ­sticas

        self.stats = {

            'total_callbacks': 0,

            'dropped_frames': 0,

            'queue_min': config.QUEUE_SIZE,

            'queue_max': 0,

            'last_callback_time': time.time()

        }

        

    def list_devices(self):

        """Lista interfaces de audio con >2 canales"""

        try:

            devices = sd.query_devices()

            audio_interfaces = []

            

            for i, device in enumerate(devices):

                if device['max_input_channels'] > 2:

                    sample_rate = device.get('default_samplerate', 44100)

                    if not sample_rate or sample_rate == 0:

                        sample_rate = 44100

                    

                    audio_interfaces.append({

                        'id': i,

                        'name': device['name'],

                        'channels': device['max_input_channels'],

                        'sample_rate': int(sample_rate)

                    })

            

            return audio_interfaces

            

        except Exception as e:

            print(f"[!] Error listando dispositivos: {e}")

            return []

    

    def start_capture(self, device_id=None):

        """âœ… Inicia captura FORZANDO 256 samples"""

        if device_id is None:

            devices = self.list_devices()

            if not devices:

                raise Exception("No se encontraron interfaces multi-canal")

            device_id = devices[0]['id']

        

        self.device_info = sd.query_devices(device_id)

        channels = min(self.device_info['max_input_channels'], config.CHANNELS_MAX)

        

        # âœ… Obtener sample rate REAL del dispositivo

        device_sample_rate = int(self.device_info.get('default_samplerate', 44100))

        

        print(f"[*] Iniciando captura con configuraciÃ³n ESTÃNDAR:")

        print(f"    Dispositivo: {self.device_info['name']}")

        print(f"    Canales: {channels}")

        print(f"    Sample rate detectado: {device_sample_rate} Hz")

        print(f"    Blocksize: {config.BLOCKSIZE} samples (FORZADO)")

        

        # âœ… FORZAR blocksize a 256

        forced_blocksize = config.BLOCKSIZE  # 256

        

        # Crear stream FORZANDO 256 samples

        try:

            print(f"[*] Forzando blocksize estÃ¡ndar: {forced_blocksize} samples...")

            

            self.stream = sd.InputStream(

                device=device_id,

                channels=channels,

                samplerate=device_sample_rate,

                blocksize=forced_blocksize,

                dtype=config.DTYPE,

                callback=self._audio_callback,

                latency='low'

            )

            

            # âœ… Guardar valores REALES

            self.actual_sample_rate = device_sample_rate

            self.actual_blocksize = forced_blocksize

            

            # âœ… ACTUALIZAR solo sample rate (blocksize ya es 256)

            config.update_audio_config(device_sample_rate)

            

            print(f"[âœ…] Blocksize configurado: {forced_blocksize} samples")

            

        except Exception as e:

            print(f"[!] Error con blocksize {forced_blocksize}: {e}")

            print(f"[!] El hardware no soporta {forced_blocksize} samples")

            print(f"[!] Esto puede causar problemas de sincronizaciÃ³n")

            

            # Intentar con 512 como fallback

            print(f"[*] Intentando con 512 samples como fallback...")

            try:

                self.stream = sd.InputStream(

                    device=device_id,

                    channels=channels,

                    samplerate=device_sample_rate,

                    blocksize=512,

                    dtype=config.DTYPE,

                    callback=self._audio_callback,

                    latency='low'

                )

                

                self.actual_sample_rate = device_sample_rate

                self.actual_blocksize = 512

                

                # Actualizar config con blocksize diferente

                config.BLOCKSIZE = 512

                config.NATIVE_CHUNK_SIZE = 512

                config.update_audio_config(device_sample_rate)

                

                print(f"[âš ï¸] ADVERTENCIA: Usando 512 samples en lugar de 256")

                print(f"[âš ï¸] Esto puede aumentar la latencia")

                

            except Exception as e2:

                # Ãšltimo recurso: configuraciÃ³n mÃ­nima

                print("[!] Usando configuraciÃ³n mÃ­nima de fallback...")

                self.stream = sd.InputStream(

                    device=device_id,

                    channels=min(2, channels),

                    samplerate=44100,

                    blocksize=256,

                    dtype=config.DTYPE,

                    callback=self._audio_callback

                )

                self.actual_sample_rate = 44100

                self.actual_blocksize = 256

                channels = 2

                

                config.update_audio_config(44100)

        

        self.running = True

        self.stream.start()

        

        # âœ… Mostrar configuraciÃ³n FINAL

        latency_ms = (self.actual_blocksize / self.actual_sample_rate) * 1000

        

        print(f"\n[âœ…] Captura iniciada con configuraciÃ³n FINAL:")

        print(f"    â€¢ Sample Rate: {self.actual_sample_rate} Hz")

        print(f"    â€¢ Blocksize: {self.actual_blocksize} samples")

        print(f"    â€¢ Latencia por bloque: {latency_ms:.2f}ms")

        print(f"    â€¢ Canales: {channels}")

        print(f"    â€¢ Queue size: {config.QUEUE_SIZE}")

        

        # Verificar latencia real del stream

        if hasattr(self.stream, 'latency'):

            actual_latency = self.stream.latency

            if actual_latency:

                print(f"    â€¢ Latencia total de captura: {actual_latency*1000:.1f}ms")

        

        return channels

    

    def _audio_callback(self, indata, frames, time_info, status):

        """Callback optimizado"""

        self.stats['total_callbacks'] += 1

        

        if status and config.VERBOSE:

            print(f"[!] Audio status: {status}")

        

        # Actualizar estadÃ­sticas

        current_qsize = self.audio_queue.qsize()

        self.stats['queue_min'] = min(self.stats['queue_min'], current_qsize)

        self.stats['queue_max'] = max(self.stats['queue_max'], current_qsize)

        

        try:

            # Poner en queue sin bloquear

            self.audio_queue.put_nowait(indata.copy())

            

            # âš ï¸ Warning solo si crÃ­tico

            if config.VERBOSE and current_qsize < 10:

                fill_percent = (current_qsize / config.QUEUE_SIZE) * 100

                if fill_percent < 5:

                    print(f"[âš ï¸] Buffer bajo: {current_qsize}/{config.QUEUE_SIZE}")

                        

        except queue.Full:

            self.stats['dropped_frames'] += 1

            

            # Mostrar cada 20 frames descartados

            if config.VERBOSE and self.stats['dropped_frames'] % 20 == 0:

                drop_rate = (self.stats['dropped_frames'] / 

                           self.stats['total_callbacks']) * 100

                print(f"[âš ï¸] Frames descartados: {self.stats['dropped_frames']} ({drop_rate:.1f}%)")

    

    def get_audio_data(self, timeout=0.1):

        """Obtiene datos de audio con timeout corto"""

        try:

            return self.audio_queue.get(timeout=timeout)

        except queue.Empty:

            return None

    

    def get_stats(self):

        """Obtener estadÃ­sticas"""

        current_qsize = self.audio_queue.qsize()

        queue_fill_percent = (current_qsize / config.QUEUE_SIZE) * 100 if config.QUEUE_SIZE > 0 else 0

        

        drop_rate = 0

        if self.stats['total_callbacks'] > 0:

            drop_rate = (self.stats['dropped_frames'] / self.stats['total_callbacks']) * 100

        

        return {

            'queue_fill': current_qsize,

            'queue_capacity': config.QUEUE_SIZE,

            'queue_fill_percent': queue_fill_percent,

            'queue_min': self.stats['queue_min'],

            'queue_max': self.stats['queue_max'],

            'total_callbacks': self.stats['total_callbacks'],

            'dropped_frames': self.stats['dropped_frames'],

            'drop_rate_percent': drop_rate,

            'sample_rate': self.actual_sample_rate,

            'blocksize': self.actual_blocksize,

            'running': self.running

        }

    

    def print_stats(self):

        """Imprimir estadÃ­sticas"""

        stats = self.get_stats()

        

        print(f"\n[ðŸ“Š] EstadÃ­sticas de Captura:")

        print(f"    Sample Rate: {stats['sample_rate']} Hz")

        print(f"    Blocksize: {stats['blocksize']} samples")

        print(f"    Queue: {stats['queue_fill']}/{stats['queue_capacity']} ({stats['queue_fill_percent']:.0f}%)")

        print(f"    Min/Max: {stats['queue_min']}/{stats['queue_max']}")

        print(f"    Callbacks: {stats['total_callbacks']}")

        print(f"    Descartados: {stats['dropped_frames']} ({stats['drop_rate_percent']:.2f}%)")

        

        if stats['queue_fill_percent'] < 10:

            print(f"[âš ï¸] Buffer bajo - considera aumentar QUEUE_SIZE")

        elif stats['queue_fill_percent'] > 90:

            print(f"[âš ï¸] Buffer alto - clientes no consumen rÃ¡pido")

        

        if stats['drop_rate_percent'] > 1.0:

            print(f"[âš ï¸] Alta tasa de descarte")

    

    def stop_capture(self):

        """Detiene la captura"""

        if self.stream:

            self.running = False

            try:

                self.stream.stop()

                self.stream.close()

                if config.VERBOSE:

                    print("[*] Captura de audio detenida")

            except Exception as e:

                print(f"[!] Error deteniendo stream: {e}")

        

        self.print_stats()

        

        # Limpiar queue

        try:

            while True:

                self.audio_queue.get_nowait()

        except queue.Empty:

            pass