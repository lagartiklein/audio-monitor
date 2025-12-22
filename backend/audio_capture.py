"""

Audio Capture - Captura multi-canal optimizada para baja latencia

CORREGIDO: ValidaciÃ³n de sample rate, mejor manejo de errores

"""



import sounddevice as sd

import numpy as np

import queue

import config



class AudioCapture:

    def __init__(self):

        self.device_info = None

        self.stream = None

        self.audio_queue = queue.Queue(maxsize=config.QUEUE_SIZE)

        self.running = False

        self.actual_sample_rate = None

        

    def list_devices(self):

        """Lista todas las interfaces de audio disponibles con >2 canales"""

        devices = sd.query_devices()

        audio_interfaces = []

        

        for i, device in enumerate(devices):

            # Solo interfaces multi-canal (>2 canales)

            if device['max_input_channels'] > 2:

                audio_interfaces.append({

                    'id': i,

                    'name': device['name'],

                    'channels': device['max_input_channels'],

                    'sample_rate': int(device['default_samplerate'])

                })

        

        return audio_interfaces

    

    def start_capture(self, device_id=None):

        """

        Inicia captura de audio en thread de alta prioridad

        Retorna: nÃºmero de canales disponibles

        """

        

        # Si no se especifica device, usar el primero con >2 canales

        if device_id is None:

            devices = self.list_devices()

            if not devices:

                raise Exception("No se encontraron interfaces multi-canal")

            device_id = devices[0]['id']

        

        self.device_info = sd.query_devices(device_id)

        channels = min(self.device_info['max_input_channels'], config.CHANNELS_MAX)

        

        # Usar sample rate del dispositivo (ya configurado en main.py)

        self.actual_sample_rate = config.SAMPLE_RATE

        

        if config.VERBOSE:

            print(f"[*] Iniciando captura de audio:")

            print(f"    Dispositivo: {self.device_info['name']}")

            print(f"    Canales: {channels}")

            print(f"    Sample rate: {self.actual_sample_rate} Hz")

            print(f"    Blocksize: {config.BLOCKSIZE} samples ({config.BLOCKSIZE/self.actual_sample_rate*1000:.1f}ms)")

            print(f"    Formato: {config.DTYPE}")

        

        # Crear stream con parÃ¡metros optimizados

        try:

            self.stream = sd.InputStream(

                device=device_id,

                channels=channels,

                samplerate=self.actual_sample_rate,

                blocksize=config.BLOCKSIZE,

                dtype=config.DTYPE,

                callback=self._audio_callback,

                latency='low'

            )

        except Exception as e:

            print(f"[!] Error creando stream: {e}")

            raise

        

        self.running = True

        self.stream.start()

        

        if config.VERBOSE:

            print(f"[âœ“] Captura iniciada correctamente")

            

            # Verificar latencia real

            actual_latency = self.stream.latency

            if actual_latency:

                print(f"    Latencia de captura: {actual_latency*1000:.1f}ms")

        

        return channels

    

    def _audio_callback(self, indata, frames, time_info, status):

        """

        Callback ejecutado en thread de audio (alta prioridad)

        CRÃTICO: Debe ser lo mÃ¡s rÃ¡pido posible

        """

        if status:

            if config.VERBOSE:

                print(f"[!] Audio status: {status}")

        

        try:

            # Verificar que recibimos el nÃºmero correcto de frames

            if frames != config.BLOCKSIZE:

                if config.VERBOSE:

                    print(f"[!] Frame mismatch: esperado {config.BLOCKSIZE}, recibido {frames}")

            

            # Copiar datos y poner en queue SIN bloquear

            self.audio_queue.put_nowait(indata.copy())

            

        except queue.Full:

            # Queue llena = cliente no consume rÃ¡pido suficiente

            # Descartar buffer (mejor que bloquear el callback)

            if config.VERBOSE:

                print("[!] Queue llena - buffer descartado (cliente lento)")

    

    def get_audio_data(self, timeout=1.0):

        """

        Obtiene datos de audio con timeout

        Retorna: numpy array (frames, channels) en float32 o None si timeout

        """

        try:

            return self.audio_queue.get(timeout=timeout)

        except queue.Empty:

            return None

    

    def stop_capture(self):

        """Detiene la captura limpiamente"""

        if self.stream:

            self.running = False

            try:

                self.stream.stop()

                self.stream.close()

                if config.VERBOSE:

                    print("[*] Captura de audio detenida")

            except Exception as e:

                print(f"[!] Error deteniendo stream: {e}")

        

        # Limpiar queue

        try:

            while True:

                self.audio_queue.get_nowait()

        except queue.Empty:

            pass