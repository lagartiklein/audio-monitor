import sounddevice as sd
import numpy as np
import threading
import config
import os
import sys

class AudioCapture:
    """
    ✅ OPTIMIZADO: Captura directa con prioridad RT y sin copias
    """
    def __init__(self):
        self.stream = None
        self.running = False
        self.actual_channels = 0
        self.callback_lock = threading.Lock()
        self.rt_priority_set = False
        
        # ✅ Callbacks directos (sin colas)
        self.callbacks = []  # Lista de funciones callback
        
    def set_realtime_priority(self):
        """✅ Configurar prioridad real-time en Linux/macOS"""
        if self.rt_priority_set:
            return
        
        try:
            if sys.platform.startswith('linux'):
                import ctypes
                import ctypes.util
                
                libc = ctypes.CDLL(ctypes.util.find_library('c'))
                
                class SchedParam(ctypes.Structure):
                    _fields_ = [('sched_priority', ctypes.c_int)]
                
                # SCHED_FIFO = 1, prioridad 50
                param = SchedParam(50)
                result = libc.sched_setscheduler(0, 1, ctypes.byref(param))
                
                if result == 0:
                    print("[RF] ✅ Thread con prioridad REAL-TIME establecida")
                    self.rt_priority_set = True
                else:
                    print("[RF] ⚠️ No se pudo establecer RT priority (ejecutar con sudo)")
                    
            elif sys.platform == 'darwin':  # macOS
                import ctypes
                libc = ctypes.CDLL('libc.dylib')
                
                # Aumentar prioridad (valores negativos = mayor prioridad)
                result = libc.setpriority(0, 0, -20)  # PRIO_PROCESS, PID, priority
                
                if result == 0:
                    print("[RF] ✅ Thread con prioridad ALTA establecida (macOS)")
                    self.rt_priority_set = True
                    
            elif sys.platform == 'win32':
                import ctypes
                
                # HIGH_PRIORITY_CLASS
                ctypes.windll.kernel32.SetPriorityClass(
                    ctypes.windll.kernel32.GetCurrentProcess(),
                    0x00000080
                )
                print("[RF] ✅ Prioridad ALTA establecida (Windows)")
                self.rt_priority_set = True
                
        except Exception as e:
            print(f"[RF] ⚠️ RT priority no disponible: {e}")
    
    def set_cpu_affinity(self):
        """✅ Asignar thread a cores específicos"""
        if not config.CPU_AFFINITY:
            return
        
        try:
            if sys.platform.startswith('linux'):
                import os
                pid = os.getpid()
                cores = ','.join(map(str, config.CPU_AFFINITY))
                os.system(f'taskset -cp {cores} {pid} > /dev/null 2>&1')
                print(f"[RF] ✅ CPU Affinity: cores {cores}")
                
        except Exception as e:
            print(f"[RF] ⚠️ CPU Affinity no disponible: {e}")
        
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
        """Iniciar captura de audio con dispositivo específico"""
        if device_id is None:
            # Buscar dispositivo con más de 2 canales
            devices = sd.query_devices()
            device_id = next((i for i, d in enumerate(devices) if d['max_input_channels'] > 2), 0)
        
        device_info = sd.query_devices(device_id)
        channels = min(device_info['max_input_channels'], 32)
        
        print(f"\n{'='*70}")
        print(f"[RF] 🎙️  INICIANDO CAPTURA OPTIMIZADA")
        print(f"{'='*70}")
        print(f"   Dispositivo: {device_info['name']}")
        print(f"   📊 Canales: {channels}")
        print(f"   ⚙️  Sample Rate: {config.SAMPLE_RATE} Hz")
        print(f"   📦 Block Size: {config.BLOCKSIZE} samples (~{config.BLOCKSIZE/config.SAMPLE_RATE*1000:.2f}ms)")
        print(f"   📞 Callbacks registrados: {len(self.callbacks)}")
        print(f"   ⚡ Modo: DIRECTO (sin colas)")
        print(f"   🎯 Latencia teórica: ~{config.BLOCKSIZE/config.SAMPLE_RATE*1000:.2f}ms")
        
        # ✅ Establecer prioridad ANTES de crear stream
        if config.AUDIO_THREAD_PRIORITY:
            self.set_realtime_priority()
            self.set_cpu_affinity()
        
        self.stream = sd.InputStream(
            device=device_id,
            channels=channels,
            samplerate=config.SAMPLE_RATE,
            blocksize=config.BLOCKSIZE,
            dtype='float32',
            callback=self._audio_callback,
            latency='low'  # ✅ Latencia mínima
        )
        
        self.actual_channels = channels
        self.running = True
        self.stream.start()
        
        print(f"[RF] ✅ Captura RF DIRECTA iniciada: {channels} canales")
        print(f"{'='*70}\n")
        
        return channels
    
    def _audio_callback(self, indata, frames, time_info, status):
        """✅ Callback optimizado - usa memoryview sin copias"""
        if status:
            print(f"[RF] ⚠️ Status: {status}")
        
        with self.callback_lock:
            if not self.callbacks:
                return
            
            # ✅ Usar memoryview para evitar copias innecesarias
            if config.USE_MEMORYVIEW:
                # Pasar como memoryview (zero-copy)
                audio_view = memoryview(indata)
                
                for name, callback in self.callbacks:
                    try:
                        callback(audio_view)
                    except Exception as e:
                        if config.DEBUG:
                            print(f"[RF] ❌ Error en callback '{name}': {e}")
            else:
                # Modo legacy: hacer copia para cada callback
                for name, callback in self.callbacks:
                    try:
                        callback(indata.copy())
                    except Exception as e:
                        if config.DEBUG:
                            print(f"[RF] ❌ Error en callback '{name}': {e}")
    
    def stop_capture(self):
        """Detener captura de audio"""
        if self.stream:
            self.running = False
            self.stream.stop()
            self.stream.close()
            print(f"[RF] 🛑 Captura detenida")
            
            with self.callback_lock:
                self.callbacks.clear()
    
    def get_device_info(self):
        """Obtener información del dispositivo actual"""
        if self.stream:
            return {
                'channels': self.actual_channels,
                'running': self.running,
                'callbacks': len(self.callbacks),
                'rt_priority': self.rt_priority_set
            }
        return None
    
    def get_stats(self):
        """Obtener estadísticas de captura"""
        if not self.stream:
            return {}
        
        return {
            'channels': self.actual_channels,
            'sample_rate': config.SAMPLE_RATE,
            'blocksize': config.BLOCKSIZE,
            'latency_ms': config.BLOCKSIZE / config.SAMPLE_RATE * 1000,
            'callbacks': len(self.callbacks),
            'rt_priority': self.rt_priority_set,
            'running': self.running
        }