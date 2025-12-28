import sounddevice as sd
import numpy as np
import threading
import config

class AudioCapture:
    """
    ✅ SIMPLIFICADO: Sin colas, envío directo a servidores
    """
    def __init__(self):
        self.stream = None
        self.running = False
        self.actual_channels = 0
        self.callback_lock = threading.Lock()
        
        # ✅ Callbacks directos (sin colas)
        self.callbacks = []  # Lista de funciones callback
        
    def register_callback(self, callback, name="unnamed"):
        """Registrar un callback que se llamará con cada bloque de audio"""
        with self.callback_lock:
            self.callbacks.append((name, callback))
            print(f"[RF] 📞 Callback registrado: '{name}'")
        
    def unregister_callback(self, callback):
        """Eliminar un callback"""
        with self.callback_lock:
            self.callbacks = [(n, cb) for n, cb in self.callbacks if cb != callback]
    
    def start_capture(self, device_id=None):
        if device_id is None:
            devices = sd.query_devices()
            device_id = next((i for i, d in enumerate(devices) if d['max_input_channels'] > 2), 0)
        
        device_info = sd.query_devices(device_id)
        channels = min(device_info['max_input_channels'], 32)
        
        print(f"[RF] 🎙️  Iniciando captura DIRECTA: {device_info['name']}")
        print(f"   📊 Canales: {channels}")
        print(f"   ⚙️  Sample Rate: {config.SAMPLE_RATE} Hz")
        print(f"   📦 Block Size: {config.BLOCKSIZE} samples")
        print(f"   📞 Callbacks registrados: {len(self.callbacks)}")
        
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
        
        print(f"[RF] ✅ Captura RF DIRECTA iniciada: {channels} canales")
        return channels
    
    def _audio_callback(self, indata, frames, time_info, status):
        """Callback que se ejecuta en cada bloque de audio"""
        if status:
            print(f"[RF] ⚠️ Status: {status}")
        
        # ✅ Llamar directamente a todos los callbacks registrados
        with self.callback_lock:
            if not self.callbacks:
                return
            
            # Hacer una copia para cada callback
            for name, callback in self.callbacks:
                try:
                    # Llamar al callback con una copia del audio
                    callback(indata.copy())
                except Exception as e:
                    print(f"[RF] ❌ Error en callback '{name}': {e}")
    
    def stop_capture(self):
        if self.stream:
            self.running = False
            self.stream.stop()
            self.stream.close()
            print(f"[RF] 🛑 Captura detenida")
            
            with self.callback_lock:
                self.callbacks.clear()