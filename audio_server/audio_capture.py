"""
Audio Capture - Captura multi-canal optimizada
Versión optimizada para baja latencia y buffer estable
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
        
        # Estadísticas
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
            return [{
                'id': 0,
                'name': 'Dispositivo Simulado (Fallback)',
                'channels': 8,
                'sample_rate': 44100
            }]
    
    def start_capture(self, device_id=None):
        """Inicia captura de audio optimizada"""
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
            print(f"    Queue size: {config.QUEUE_SIZE}")
        
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
        """Callback optimizado con monitoreo de buffer"""
        self.stats['total_callbacks'] += 1
        current_time = time.time()
        
        if status and config.VERBOSE:
            print(f"[!] Audio status: {status}")
        
        # Monitorear tasa de callbacks
        time_since_last = current_time - self.stats['last_callback_time']
        self.stats['last_callback_time'] = current_time
        
        # Actualizar estadísticas de queue
        current_qsize = self.audio_queue.qsize()
        self.stats['queue_min'] = min(self.stats['queue_min'], current_qsize)
        self.stats['queue_max'] = max(self.stats['queue_max'], current_qsize)
        
        try:
            # Poner en queue sin bloquear
            self.audio_queue.put_nowait(indata.copy())
            
            # Solo mostrar warnings si buffer muy bajo (y VERBOSE)
            if config.VERBOSE:
                if current_qsize == 0:
                    print(f"[⚠️] Audio queue vacía - posible underrun")
                elif current_qsize < 3:
                    fill_percent = (current_qsize / config.QUEUE_SIZE) * 100
                    if fill_percent < 10:
                        print(f"[⚠️] Buffer crítico bajo: {current_qsize}/{config.QUEUE_SIZE} ({fill_percent:.0f}%)")
                    elif fill_percent < 30:
                        print(f"[⚠️] Buffer bajo: {current_qsize}/{config.QUEUE_SIZE} ({fill_percent:.0f}%)")
                        
        except queue.Full:
            # Queue llena - incrementar contador de frames descartados
            self.stats['dropped_frames'] += 1
            
            if config.VERBOSE:
                # Mostrar cada 10 frames descartados para no saturar la consola
                if self.stats['dropped_frames'] % 10 == 0:
                    drop_rate = (self.stats['dropped_frames'] / self.stats['total_callbacks']) * 100
                    print(f"[⚠️] Buffer lleno - frames descartados: {self.stats['dropped_frames']}")
                    print(f"    Tasa de descarte: {drop_rate:.2f}%")
                    print(f"    Posibles causas:")
                    print(f"    - Cliente no consume suficientemente rápido")
                    print(f"    - QUEUE_SIZE muy pequeño ({config.QUEUE_SIZE})")
                    print(f"    - Procesamiento del servidor demasiado lento")
    
    def get_audio_data(self, timeout=1.0):
        """Obtiene datos de audio con timeout"""
        try:
            return self.audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def get_stats(self):
        """Obtener estadísticas de captura"""
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
            'sample_rate': self.actual_sample_rate or config.SAMPLE_RATE,
            'running': self.running
        }
    
    def print_stats(self):
        """Imprimir estadísticas detalladas"""
        stats = self.get_stats()
        
        print(f"\n[📊] Estadísticas de Buffer:")
        print(f"    Queue: {stats['queue_fill']}/{stats['queue_capacity']} ({stats['queue_fill_percent']:.0f}%)")
        print(f"    Min/Max: {stats['queue_min']}/{stats['queue_max']}")
        print(f"    Callbacks: {stats['total_callbacks']}")
        print(f"    Frames descartados: {stats['dropped_frames']} ({stats['drop_rate_percent']:.2f}%)")
        
        if stats['queue_fill_percent'] < 10:
            print(f"[⚠️] BUFFER CRÍTICO BAJO: {stats['queue_fill_percent']:.0f}%")
            print(f"    → Incrementa QUEUE_SIZE o BLOCKSIZE en config.py")
        elif stats['queue_fill_percent'] > 90:
            print(f"[⚠️] BUFFER CRÍTICO ALTO: {stats['queue_fill_percent']:.0f}%")
            print(f"    → Cliente no consume rápido suficiente")
        
        if stats['drop_rate_percent'] > 1.0:
            print(f"[⚠️] ALTA TASA DE DESCARTE: {stats['drop_rate_percent']:.2f}%")
            print(f"    → Considera aumentar QUEUE_SIZE en config.py")
    
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
        
        # Imprimir estadísticas finales
        self.print_stats()
        
        # Limpiar queue
        try:
            while True:
                self.audio_queue.get_nowait()
        except queue.Empty:
            pass