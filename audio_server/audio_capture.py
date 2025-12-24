"""
Audio Capture - Compatible con ASIO y otras interfaces
Versión optimizada con manejo especial para ASIO
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
        self.is_asio = False  # ✅ Detectar si es ASIO
        
        # Estadísticas de buffer
        self.stats = {
            'total_callbacks': 0,
            'dropped_frames': 0,
            'underruns': 0,
            'overruns': 0,
            'last_queue_size': 0,
            'min_queue_size': config.QUEUE_SIZE,
            'max_queue_size': 0,
            'audio_errors': 0
        }
        
        self.monitor_thread = None
        self.last_stats_time = time.time()
        
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
        """Inicia captura de audio con configuración optimizada"""
        if device_id is None:
            devices = self.list_devices()
            if not devices:
                raise Exception("No se encontraron interfaces multi-canal")
            device_id = devices[0]['id']
        
        self.device_info = sd.query_devices(device_id)
        channels = min(self.device_info['max_input_channels'], config.CHANNELS_MAX)
        
        # ✅ Detectar si es ASIO
        device_name = self.device_info['name'].upper()
        self.is_asio = 'ASIO' in device_name
        
        # Determinar sample rate
        self.actual_sample_rate = config.SAMPLE_RATE
        
        if config.VERBOSE:
            print(f"[*] Iniciando captura de audio OPTIMIZADA:")
            print(f"    Dispositivo: {self.device_info['name']}")
            if self.is_asio:
                print(f"    🎯 ASIO detectado - usando configuración optimizada")
            print(f"    Canales: {channels}")
            print(f"    Sample rate: {self.actual_sample_rate} Hz")
            print(f"    Blocksize: {config.BLOCKSIZE} samples")
            
            latency_ms = (config.BLOCKSIZE / self.actual_sample_rate) * 1000
            print(f"    Latencia por bloque: {latency_ms:.1f}ms")
            print(f"    Queue size: {config.QUEUE_SIZE} bloques ({config.QUEUE_SIZE * latency_ms:.1f}ms buffer)")
            print(f"    Formato: {config.DTYPE}")
        
        # ✅ Configuración ASIO-compatible
        try:
            if self.is_asio:
                # ✅ ASIO: Configuración SIMPLE sin flags extras
                print(f"[*] Usando configuración ASIO simple...")
                self.stream = sd.InputStream(
                    device=device_id,
                    channels=channels,
                    samplerate=self.actual_sample_rate,
                    blocksize=config.BLOCKSIZE,
                    dtype=config.DTYPE,
                    callback=self._audio_callback,
                    latency='low'
                )
            else:
                # ✅ No-ASIO: Usar todas las optimizaciones
                print(f"[*] Usando configuración completa (no-ASIO)...")
                extra_settings = config.AUDIO_EXTRA_SETTINGS if config.AUDIO_EXTRA_SETTINGS else {}
                
                self.stream = sd.InputStream(
                    device=device_id,
                    channels=channels,
                    samplerate=self.actual_sample_rate,
                    blocksize=config.BLOCKSIZE,
                    dtype=config.DTYPE,
                    callback=self._audio_callback,
                    latency=config.AUDIO_LATENCY,
                    **extra_settings
                )
                
        except Exception as e:
            print(f"[!] Error creando stream: {e}")
            print(f"[*] Intentando configuración mínima conservadora...")
            
            # Fallback ultra-simple
            try:
                self.stream = sd.InputStream(
                    device=device_id,
                    channels=channels,
                    samplerate=self.actual_sample_rate,
                    blocksize=config.BLOCKSIZE,
                    dtype=config.DTYPE,
                    callback=self._audio_callback
                )
            except Exception as e2:
                print(f"[!] Error crítico: {e2}")
                raise
        
        self.running = True
        self.stream.start()
        
        # Iniciar thread de monitoreo
        if config.LOG_BUFFER_STATS:
            self.monitor_thread = threading.Thread(
                target=self._monitor_loop,
                daemon=True,
                name="BufferMonitor"
            )
            self.monitor_thread.start()
        
        if config.VERBOSE:
            print(f"[✓] Captura iniciada correctamente")
            
            # Verificar latencia real
            if hasattr(self.stream, 'latency'):
                actual_latency = self.stream.latency
                if actual_latency:
                    input_latency = actual_latency[0] if isinstance(actual_latency, tuple) else actual_latency
                    print(f"    Latencia de entrada: {input_latency*1000:.1f}ms")
        
        return channels
    
    def _audio_callback(self, indata, frames, time_info, status):
        """Callback OPTIMIZADO con mejor manejo de errores"""
        self.stats['total_callbacks'] += 1
        
        if status:
            self.stats['audio_errors'] += 1
            if hasattr(status, 'input_underflow') and status.input_underflow:
                self.stats['underruns'] += 1
            if hasattr(status, 'input_overflow') and status.input_overflow:
                self.stats['overruns'] += 1
                
            if config.VERBOSE and self.stats['audio_errors'] % 10 == 1:
                print(f"[!] Audio status: {status}")
        
        try:
            self.audio_queue.put_nowait(indata.copy())
            
        except queue.Full:
            self.stats['dropped_frames'] += 1
            
            # ⚠️ Solo advertir cada 10 frames descartados
            if self.stats['dropped_frames'] % 10 == 1:
                print(f"[⚠️] Buffer lleno - frames descartados: {self.stats['dropped_frames']}")
                print(f"    Posibles causas:")
                print(f"    - Cliente no consume suficientemente rápido")
                print(f"    - QUEUE_SIZE muy pequeño ({config.QUEUE_SIZE})")
                print(f"    - Procesamiento del servidor demasiado lento")
    
    def get_audio_data(self, timeout=1.0):
        """Obtiene datos de audio con mejor manejo"""
        try:
            data = self.audio_queue.get(timeout=timeout)
            
            current_size = self.audio_queue.qsize()
            self.stats['last_queue_size'] = current_size
            self.stats['min_queue_size'] = min(self.stats['min_queue_size'], current_size)
            self.stats['max_queue_size'] = max(self.stats['max_queue_size'], current_size)
            
            # ⚠️ Detectar underruns (queue casi vacía)
            if current_size < config.QUEUE_SIZE * config.BUFFER_UNDERRUN_THRESHOLD:
                if self.stats['total_callbacks'] % 100 == 0:
                    print(f"[⚠️] Buffer bajo: {current_size}/{config.QUEUE_SIZE} "
                          f"({current_size/config.QUEUE_SIZE*100:.0f}%)")
            
            return data
            
        except queue.Empty:
            if config.VERBOSE:
                print(f"[⚠️] Audio queue vacía - posible underrun")
            return None
    
    def _monitor_loop(self):
        """Thread que monitorea salud del buffer"""
        print("[*] Monitor de buffer iniciado")
        
        while self.running:
            try:
                time.sleep(config.BUFFER_STATS_INTERVAL)
                
                if not self.running:
                    break
                
                current_size = self.audio_queue.qsize()
                fill_percent = (current_size / config.QUEUE_SIZE) * 100
                
                dropped_rate = 0
                if self.stats['total_callbacks'] > 0:
                    dropped_rate = (self.stats['dropped_frames'] / 
                                  self.stats['total_callbacks']) * 100
                
                if config.VERBOSE:
                    print(f"\n[📊] Estadísticas de Buffer:")
                    print(f"    Queue: {current_size}/{config.QUEUE_SIZE} ({fill_percent:.0f}%)")
                    print(f"    Min/Max: {self.stats['min_queue_size']}/{self.stats['max_queue_size']}")
                    print(f"    Callbacks: {self.stats['total_callbacks']}")
                    print(f"    Frames descartados: {self.stats['dropped_frames']} ({dropped_rate:.2f}%)")
                    
                    if self.stats['underruns'] > 0 or self.stats['overruns'] > 0:
                        print(f"    ⚠️ Underruns: {self.stats['underruns']}")
                        print(f"    ⚠️ Overruns: {self.stats['overruns']}")
                
                # Advertencias
                if fill_percent < config.BUFFER_UNDERRUN_THRESHOLD * 100:
                    print(f"[⚠️] BUFFER CRÍTICO BAJO: {fill_percent:.0f}%")
                    print(f"    → Incrementa QUEUE_SIZE o BLOCKSIZE en config.py")
                    
                elif fill_percent > config.BUFFER_OVERRUN_THRESHOLD * 100:
                    print(f"[⚠️] BUFFER CRÍTICO ALTO: {fill_percent:.0f}%")
                    print(f"    → Cliente no está consumiendo suficientemente rápido")
                
                if dropped_rate > 5.0:
                    print(f"[⚠️] ALTA TASA DE DESCARTE: {dropped_rate:.1f}%")
                    print(f"    → Sistema sobrecargado o QUEUE_SIZE insuficiente")
                
                self.stats['min_queue_size'] = current_size
                self.stats['max_queue_size'] = current_size
                
            except Exception as e:
                if config.VERBOSE:
                    print(f"[!] Error en monitor loop: {e}")
        
        print("[*] Monitor de buffer detenido")
    
    def get_stats(self):
        """Obtiene estadísticas actuales"""
        return {
            **self.stats,
            'current_queue_size': self.audio_queue.qsize(),
            'queue_fill_percent': (self.audio_queue.qsize() / config.QUEUE_SIZE) * 100,
            'sample_rate': self.actual_sample_rate,
            'blocksize': config.BLOCKSIZE,
            'latency_ms': (config.BLOCKSIZE / self.actual_sample_rate) * 1000,
            'is_asio': self.is_asio
        }
    
    def stop_capture(self):
        """Detiene la captura limpiamente"""
        if self.stream:
            self.running = False
            
            if self.monitor_thread and self.monitor_thread.is_alive():
                self.monitor_thread.join(timeout=1)
            
            try:
                self.stream.stop()
                self.stream.close()
                
                if config.VERBOSE:
                    print("[*] Captura de audio detenida")
                    
                    if self.stats['total_callbacks'] > 0:
                        print(f"\n[📊] Estadísticas Finales:")
                        print(f"    Total callbacks: {self.stats['total_callbacks']}")
                        print(f"    Frames descartados: {self.stats['dropped_frames']}")
                        dropped_rate = (self.stats['dropped_frames'] / 
                                      self.stats['total_callbacks']) * 100
                        print(f"    Tasa de descarte: {dropped_rate:.2f}%")
                        
                        if self.stats['underruns'] > 0 or self.stats['overruns'] > 0:
                            print(f"    Underruns: {self.stats['underruns']}")
                            print(f"    Overruns: {self.stats['overruns']}")
                            
            except Exception as e:
                print(f"[!] Error deteniendo stream: {e}")
        
        # Limpiar queue
        try:
            while True:
                self.audio_queue.get_nowait()
        except queue.Empty:
            pass