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
        # ⭐ CORREGIDO: Queue con tamaño 2 para buffer ping-pong
        self.audio_queue = queue.Queue(maxsize=config.QUEUE_SIZE)
        self.running = False
        self.actual_channels = 0
        self.last_warning_time = 0
        self.last_log_time = 0
        self.drop_counter = 0  # Contador de bloques descartados
        
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
            print(f"[AudioCapture] 🔱 {len(audio_interfaces)} interfaces encontradas")
            return audio_interfaces
        except Exception as e:
            print(f"[AudioCapture] ❌ Error: {e}")
            return []
    
    def start_capture(self, device_id=None):
        if device_id is None:
            devices = self.list_devices()
            if not devices: 
                print("[AudioCapture] ❌ No hay interfaces multicanal")
                raise Exception("No multi-channel interfaces found")
            device_id = devices[0]['id']
            print(f"[AudioCapture] Usando dispositivo por defecto: ID {device_id}")
        
        self.device_info = sd.query_devices(device_id)
        channels = min(self.device_info['max_input_channels'], 32)
        
        print(f"[AudioCapture] Iniciando captura RF:")
        print(f"  🔱 Dispositivo: {self.device_info['name']}")
        print(f"  📊 Canales: {channels}")
        print(f"  ⚙️ Sample Rate: {config.SAMPLE_RATE} Hz")
        print(f"  📦 Block Size: {config.BLOCKSIZE} samples ({(config.BLOCKSIZE/config.SAMPLE_RATE)*1000:.2f}ms)")
        print(f"  ⭐ MODO RF: Buffer de {config.QUEUE_SIZE} bloques, procesamiento inmediato")
        
        self.stream = sd.InputStream(
            device=device_id,
            channels=channels,
            samplerate=config.SAMPLE_RATE,
            blocksize=config.BLOCKSIZE,
            dtype='float32',
            callback=self._audio_callback,
            latency='low'
        )
        
        self.actual_channels = channels
        self.running = True
        self.stream.start()
        
        latency_ms = (config.BLOCKSIZE/config.SAMPLE_RATE)*1000
        print(f"[AudioCapture] ✅ Captura RF iniciada: {channels} canales, {latency_ms:.2f}ms, queue_size={config.QUEUE_SIZE}")
        return channels
    
    def _audio_callback(self, indata, frames, time_info, status):
        try:
            current_time = time.time()
            
            # ⭐ CORREGIDO: Manejo inteligente de cola para RF
            if self.audio_queue.full():
                # En modo RF, descartar el bloque más viejo es CORRECTO
                try:
                    discarded = self.audio_queue.get_nowait()
                    self.drop_counter += 1
                    
                    # Log warnings ocasionales
                    if config.LOG_QUEUE_WARNINGS and current_time - self.last_warning_time > 2.0:
                        print(f"[AudioCapture-RF] ⚠️ Cola llena, descartando bloque viejo (total descartados: {self.drop_counter})")
                        self.last_warning_time = current_time
                        
                except queue.Empty:
                    # Esto no debería pasar si full() es True, pero por seguridad
                    pass
            
            # ⭐ Poner el nuevo bloque en cola
            self.audio_queue.put_nowait(indata.copy())
            
            # Log periódico de estado (solo si VERBOSE)
            if config.VERBOSE and current_time - self.last_log_time > 5.0:
                qsize = self.audio_queue.qsize()
                print(f"[AudioCapture-RF] Estado: cola={qsize}/{config.QUEUE_SIZE}, descartados={self.drop_counter}")
                self.last_log_time = current_time
                
        except Exception as e:
            # Solo log si pasa más de 1 segundo desde el último error
            if current_time - self.last_log_time > 1.0:
                print(f"[AudioCapture-RF] ❌ Error en callback: {e}")
                self.last_log_time = current_time
    
    def get_audio_data(self, timeout=0.05):
        try:
            return self.audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def stop_capture(self):
        if self.stream:
            print("[AudioCapture] Deteniendo captura RF...")
            self.running = False
            try:
                self.stream.stop()
                self.stream.close()
                print(f"[AudioCapture] ✅ Captura RF detenida. Bloques descartados: {self.drop_counter}")
            except Exception as e:
                print(f"[AudioCapture] ❌ Error: {e}")