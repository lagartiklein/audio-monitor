import sounddevice as sd
import numpy as np
import queue
import config

class AudioCapture:
    def __init__(self):
        self.device_info = None
        self.stream = None
        self.audio_queue = queue.Queue(maxsize=config.QUEUE_SIZE)
        
    def list_devices(self):
        """Lista todas las interfaces de audio disponibles"""
        devices = sd.query_devices()
        audio_interfaces = []
        
        for i, device in enumerate(devices):
            if device['max_input_channels'] > 2:  # Solo interfaces multi-canal
                audio_interfaces.append({
                    'id': i,
                    'name': device['name'],
                    'channels': device['max_input_channels'],
                    'sample_rate': int(device['default_samplerate'])
                })
        
        return audio_interfaces
    
    def start_capture(self, device_id=None):
        """Inicia captura de audio en thread de alta prioridad"""
        
        # Si no se especifica device, usar el primero con >2 canales
        if device_id is None:
            devices = self.list_devices()
            if not devices:
                raise Exception("No se encontraron interfaces multi-canal")
            device_id = devices[0]['id']
        
        self.device_info = sd.query_devices(device_id)
        channels = min(self.device_info['max_input_channels'], config.CHANNELS_MAX)
        
        if config.VERBOSE:
            print(f"[*] Iniciando captura:")
            print(f"    Dispositivo: {self.device_info['name']}")
            print(f"    Canales: {channels}")
            print(f"    Sample rate: {config.SAMPLE_RATE} Hz")
            print(f"    Blocksize: {config.BLOCKSIZE} ({config.BLOCKSIZE/config.SAMPLE_RATE*1000:.1f}ms)")
        
        self.stream = sd.InputStream(
            device=device_id,
            channels=channels,
            samplerate=config.SAMPLE_RATE,
            blocksize=config.BLOCKSIZE,
            dtype=np.float32,  # Capturamos en float32, convertimos después
            callback=self._audio_callback
        )
        
        self.stream.start()
        return channels
    
    def _audio_callback(self, indata, frames, time_info, status):
        """Callback ejecutado en thread de audio (alta prioridad)"""
        if status:
            print(f"[!] Audio status: {status}")
        
        try:
            # Copiar datos y poner en queue sin bloquear
            self.audio_queue.put_nowait(indata.copy())
        except queue.Full:
            # Si la queue está llena, descartar (cliente lento)
            if config.VERBOSE:
                print("[!] Queue llena, descartando buffer")
    
    def get_audio_data(self):
        """Obtiene datos de audio (bloquea hasta que haya datos)"""
        return self.audio_queue.get()
    
    def stop_capture(self):
        """Detiene la captura"""
        if self.stream:
            self.stream.stop()
            self.stream.close()
            if config.VERBOSE:
                print("[*] Captura detenida")