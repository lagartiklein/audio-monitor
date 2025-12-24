"""
Audio Capture - Captura multi-canal optimizada
Versión para servidor dual
"""

import sounddevice as sd
import numpy as np
import queue
import threading
import time
import sys
import os

# Agregar ruta para importar config unificada
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import config

class AudioCapture:
    def __init__(self):
        self.device_info = None
        self.stream = None
        self.audio_queue = queue.Queue(maxsize=config.QUEUE_SIZE)
        self.running = False
        self.actual_sample_rate = None
        
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
            return [{
                'id': 0,
                'name': 'Dispositivo Simulado (Fallback)',
                'channels': 8,
                'sample_rate': 44100
            }]
    
    def start_capture(self, device_id=None):
        """Inicia captura de audio"""
        if device_id is None:
            devices = self.list_devices()
            if not devices:
                raise Exception("No se encontraron interfaces multi-canal")
            device_id = devices[0]['id']
        
        self.device_info = sd.query_devices(device_id)
        channels = min(self.device_info['max_input_channels'], config.CHANNELS_MAX)
        
        # Determinar sample rate
        self.actual_sample_rate = config.SAMPLE_RATE
        
        if config.VERBOSE:
            print(f"[*] Iniciando captura de audio:")
            print(f"    Dispositivo: {self.device_info['name']}")
            print(f"    Canales: {channels}")
            print(f"    Sample rate: {self.actual_sample_rate} Hz")
            print(f"    Blocksize: {config.BLOCKSIZE} samples")
            
            latency_ms = (config.BLOCKSIZE / self.actual_sample_rate) * 1000
            print(f"    Latencia por bloque: {latency_ms:.1f}ms")
            print(f"    Formato: {config.DTYPE}")
        
        # Crear stream con parámetros optimizados
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
            
            # Intentar con parámetros más conservadores
            print("[*] Intentando con parámetros más conservadores...")
            try:
                self.stream = sd.InputStream(
                    device=device_id,
                    channels=min(2, channels),
                    samplerate=44100,
                    blocksize=512,
                    dtype=config.DTYPE,
                    callback=self._audio_callback
                )
                channels = 2
                self.actual_sample_rate = 44100
            except Exception as e2:
                print(f"[!] Error crítico: {e2}")
                raise
        
        self.running = True
        self.stream.start()
        
        if config.VERBOSE:
            print(f"[✓] Captura iniciada correctamente")
            
            # Verificar latencia real
            if hasattr(self.stream, 'latency'):
                actual_latency = self.stream.latency
                if actual_latency:
                    print(f"    Latencia de captura: {actual_latency*1000:.1f}ms")
        
        return channels
    
    def _audio_callback(self, indata, frames, time_info, status):
        """Callback ejecutado en thread de audio"""
        if status:
            if config.VERBOSE:
                print(f"[!] Audio status: {status}")
        
        try:
            # Copiar datos y poner en queue SIN bloquear
            self.audio_queue.put_nowait(indata.copy())
            
        except queue.Full:
            # Queue llena = cliente no consume rápido suficiente
            # Descartar buffer (mejor que bloquear el callback)
            pass
    
    def get_audio_data(self, timeout=1.0):
        """Obtiene datos de audio con timeout"""
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