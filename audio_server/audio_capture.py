import sounddevice as sd, numpy as np, queue, threading, time, sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import config

class AudioCapture:
    def __init__(self):
        self.device_info = None
        self.stream = None
        self.audio_queue = queue.Queue(maxsize=config.QUEUE_SIZE)
        self.running = False
        self.actual_channels = 0
        
    def list_devices(self):
        try:
            devices = sd.query_devices()
            audio_interfaces = []
            for i, device in enumerate(devices):
                if device['max_input_channels'] > 2:
                    audio_interfaces.append({
                        'id': i,
                        'name': device['name'],
                        'channels': device['max_input_channels'],
                        'sample_rate': int(device.get('default_samplerate', 48000))
                    })
            print(f"[AudioCapture] Encontradas {len(audio_interfaces)} interfaces de audio multicanal")
            return audio_interfaces
        except Exception as e:
            print(f"[AudioCapture] ❌ Error listando dispositivos: {e}")
            return []
    
    def start_capture(self, device_id=None):
        if device_id is None:
            devices = self.list_devices()
            if not devices: 
                print("[AudioCapture] ❌ No se encontraron interfaces multicanal")
                raise Exception("No multi-channel interfaces found")
            device_id = devices[0]['id']
            print(f"[AudioCapture] Usando dispositivo por defecto: ID {device_id}")
        
        self.device_info = sd.query_devices(device_id)
        channels = min(self.device_info['max_input_channels'], 32)
        
        print(f"[AudioCapture] Iniciando captura:")
        print(f"  📱 Dispositivo: {self.device_info['name']}")
        print(f"  🔊 Canales: {channels}")
        print(f"  ⚙️  Sample Rate: 48000 Hz")
        print(f"  📦 Block Size: 256 samples")
        
        self.stream = sd.InputStream(
            device=device_id,
            channels=channels,
            samplerate=48000,
            blocksize=256,
            dtype='float32',
            callback=self._audio_callback,
            latency='low'
        )
        
        self.actual_channels = channels
        config.SAMPLE_RATE = 48000
        config.BLOCKSIZE = 256
        
        self.running = True
        self.stream.start()
        latency_ms = (256/48000)*1000
        print(f"[AudioCapture] ✅ Captura iniciada: {channels} canales, {latency_ms:.2f}ms latencia")
        return channels
    
    def _audio_callback(self, indata, frames, time_info, status):
        try:
            self.audio_queue.put_nowait(indata.copy())
        except queue.Full:
            print("[AudioCapture] ⚠️  Cola de audio llena, descartando bloque")
            pass
    
    def get_audio_data(self, timeout=0.1):
        try:
            return self.audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def stop_capture(self):
        if self.stream:
            print("[AudioCapture] Deteniendo captura...")
            self.running = False
            try:
                self.stream.stop()
                self.stream.close()
                print("[AudioCapture] ✅ Captura detenida")
            except Exception as e:
                print(f"[AudioCapture] ❌ Error deteniendo captura: {e}")