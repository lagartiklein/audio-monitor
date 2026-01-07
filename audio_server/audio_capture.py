import sounddevice as sd

import numpy as np

import threading

import config

import os

import sys

import time  # ✅ Agregar para medición de latencia



class AudioCapture:

    """

    ✅ OPTIMIZADO: Captura directa con prioridad RT y VU meters reales

    """

    def __init__(self):

        self.stream = None

        self.running = False

        self.actual_channels = 0

        self.physical_channels = 0  # ✅ NUEVO: Guardar canales reales del dispositivo

        self.callback_lock = threading.Lock()

        self.rt_priority_set = False

        
        # ✅ Callbacks directos (sin colas)
        self.callbacks = []  # Lista de funciones callback
        
        # ✅ NUEVO: Mixer de audio para cliente maestro
        self.audio_mixer = None
        self.channel_manager = None
        self.master_client_id = None

        

        # 🎚️ VU METERS: Sistema de análisis de niveles

        self.vu_callback = None

        self.vu_update_interval = config.VU_UPDATE_INTERVAL if hasattr(config, 'VU_UPDATE_INTERVAL') else 100  # ms

        self.vu_last_update = 0

        self.vu_peak_hold = {}  # {channel: peak_value}

        self.vu_peak_decay = 0.95  # Factor de decaimiento de picos

        # ✅ Latencia: Medición dinámica

        self.latency_measurements = []

        self.last_callback_time = None

        self.max_latency_samples = 100  # Mantener promedio de 100 mediciones

        self.stream_latency = 0.0  # ✅ Latencia del motor de audio

        

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

                self._set_windows_priority()
                self.rt_priority_set = True
                

        except Exception as e:

            print(f"[RF] ⚠️ RT priority no disponible: {e}")

    
    def _set_windows_priority(self):
        """✅ NUEVO: Establecer prioridad alta en Windows para audio en tiempo real"""
        try:
            import ctypes
            
            # Constantes de Windows
            PROCESS_SET_INFORMATION = 0x0200
            HIGH_PRIORITY_CLASS = 0x00000080
            REALTIME_PRIORITY_CLASS = 0x00000100
            
            pid = os.getpid()
            
            # Abrir el proceso
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_SET_INFORMATION, False, pid)
            if not handle:
                print("[RF] ⚠️ No se pudo obtener handle del proceso en Windows")
                return
            
            try:
                # Establecer prioridad HIGH (más seguro que REALTIME)
                success = ctypes.windll.kernel32.SetPriorityClass(handle, HIGH_PRIORITY_CLASS)
                
                if success:
                    print("[RF] ✅ Prioridad ALTA establecida (Windows - HIGH_PRIORITY_CLASS)")
                else:
                    print("[RF] ⚠️ No se pudo establecer prioridad en Windows")
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
                
        except Exception as e:
            print(f"[RF] ⚠️ Error estableciendo prioridad Windows: {e}")

    

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

        
    def set_audio_mixer(self, mixer):
        """✅ NUEVO: Conectar AudioMixer"""
        self.audio_mixer = mixer
        print(f"[AudioCapture] 🎛️ AudioMixer conectado")
    
    def set_channel_manager(self, channel_manager):
        """✅ NUEVO: Conectar ChannelManager"""
        self.channel_manager = channel_manager
        if hasattr(channel_manager, 'get_master_client_id'):
            self.master_client_id = channel_manager.get_master_client_id()
        print(f"[AudioCapture] 🎧 Cliente maestro: {self.master_client_id}")

    def unregister_callback(self, callback):

        """Eliminar un callback"""

        with self.callback_lock:

            self.callbacks = [(n, cb) for n, cb in self.callbacks if cb != callback]

    def get_average_latency(self):

        """Obtener latencia de procesamiento promedio en ms"""

        if not self.latency_measurements:

            return self.stream_latency  # Fallback a latencia del motor

        return sum(self.latency_measurements) / len(self.latency_measurements)

    

    def register_vu_callback(self, callback):

        """

        🎚️ NUEVO: Registrar callback para niveles VU

        El callback recibirá: dict {channel: {'rms': float, 'peak': float, 'db': float}}

        """

        self.vu_callback = callback

        print(f"[RF] 🎚️ VU callback registrado")

    

    def calculate_vu_levels(self, audio_data):

        """

        🎚️ NUEVO: Calcular niveles RMS y peak por canal

        """

        if not self.vu_callback:

            return

        

        import time

        current_time = time.time() * 1000  # ms

        

        # Limitar frecuencia de actualización

        if current_time - self.vu_last_update < self.vu_update_interval:

            return

        

        self.vu_last_update = current_time

        

        try:

            # Convertir memoryview a ndarray si es necesario

            if isinstance(audio_data, memoryview):

                audio_array = np.frombuffer(audio_data, dtype=np.float32).reshape(-1, self.actual_channels)

            else:

                audio_array = audio_data

            

            if audio_array.size == 0:

                return

            

            levels = {}

            

            for ch in range(audio_array.shape[1]):

                channel_data = audio_array[:, ch]

                

                # RMS (Root Mean Square) - nivel promedio

                rms = np.sqrt(np.mean(channel_data ** 2))

                

                # Peak - valor máximo absoluto

                peak = np.max(np.abs(channel_data))

                

                # Peak hold con decaimiento

                if ch in self.vu_peak_hold:

                    self.vu_peak_hold[ch] = max(peak, self.vu_peak_hold[ch] * self.vu_peak_decay)

                else:

                    self.vu_peak_hold[ch] = peak

                

                # Convertir a dB (con clipping para evitar -inf)

                rms_db = 20 * np.log10(max(rms, 1e-6))  # Mínimo -120dB

                peak_db = 20 * np.log10(max(peak, 1e-6))

                

                # Normalizar a rango 0-100 para VU meter visual

                # -60dB = 0%, 0dB = 100%

                rms_percent = max(0, min(100, (rms_db + 60) / 60 * 100))

                peak_percent = max(0, min(100, (peak_db + 60) / 60 * 100))

                

                levels[ch] = {

                    'rms': rms,  # Valor lineal

                    'peak': peak,  # Valor lineal

                    'rms_db': rms_db,  # dB

                    'peak_db': peak_db,  # dB

                    'rms_percent': rms_percent,  # Para UI (0-100)

                    'peak_percent': peak_percent,  # Para UI (0-100)

                    'peak_hold': self.vu_peak_hold[ch]

                }

            

            # Enviar niveles al callback

            self.vu_callback(levels)

            

        except Exception as e:

            if config.DEBUG:

                print(f"[RF] ⚠️ Error calculando VU: {e}")

    

    def start_capture(self, device_id=None):
        """
        Inicia la captura de audio utilizando un dispositivo de entrada específico o selecciona automáticamente uno adecuado.
        Si no se especifica `device_id`, busca el primer dispositivo de entrada con más de 2 canales disponibles.
        Configura y arranca un flujo de audio (`InputStream`) con los parámetros definidos en la configuración global (`config`).
        Establece la prioridad del hilo y la afinidad de CPU si está configurado.
        Imprime información relevante sobre el dispositivo, canales, sample rate, tamaño de bloque, callbacks registrados, modo de captura, VU meters y latencia teórica.
        Al finalizar, retorna la cantidad real de canales capturados.
        Args:
            device_id (int, optional): ID del dispositivo de entrada de audio a utilizar. Si es None, selecciona automáticamente.
        Returns:
            int: Número real de canales capturados por el dispositivo seleccionado.
        """

        """Iniciar captura de audio con dispositivo específico"""

        if device_id is None:

            # Buscar dispositivo con más de 2 canales


            devices = sd.query_devices()
            # Buscar el primer dispositivo con más de 2 canales
            for i, d in enumerate(devices):
                try:
                    max_channels = d.get('max_input_channels', 0) if isinstance(d, dict) else getattr(d, 'max_input_channels', 0)
                except Exception:
                    max_channels = 0
                if isinstance(max_channels, (int, float)) and max_channels > 2:
                    device_id = i
                    break
            else:
                device_id = 0

        


        device_info = sd.query_devices(device_id)
        # Acceso seguro al número de canales
        if isinstance(device_info, dict):
            channels = device_info.get('max_input_channels', 1)
        else:
            channels = getattr(device_info, 'max_input_channels', 1)

        

        print(f"\n{'='*70}")

        print(f"[RF] 🎙️ INICIANDO CAPTURA OPTIMIZADA")

        print(f"{'='*70}")

        print(f"   Dispositivo: {device_info.get('name') if isinstance(device_info, dict) else getattr(device_info, 'name', 'Unknown')}")

        print(f"   📊 Canales: {channels}")

        print(f"   ⚙️ Sample Rate: {config.SAMPLE_RATE} Hz")

        print(f"   📦 Block Size: {config.BLOCKSIZE} samples (~{config.BLOCKSIZE/config.SAMPLE_RATE*1000:.2f}ms)")

        print(f"   📞 Callbacks registrados: {len(self.callbacks)}")

        print(f"   ⚡ Modo: DIRECTO (sin colas)")

        print(f"   🎚️ VU Meters: {'ENABLED' if self.vu_callback else 'DISABLED'}")

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

        self.physical_channels = channels  # ✅ Guardar canales reales capturados

        self.running = True

        self.stream.start()

        # ✅ Capturar latencia del motor de audio

        self.stream_latency = self.stream.latency * 1000  # Convertir a ms

        

        print(f"[RF] ✅ Captura RF DIRECTA iniciada: {channels} canal(es) (sin relleno artificial)")

        print(f"   🎯 Latencia del motor: {self.stream_latency:.2f} ms")

        print(f"{'='*70}\n")

        

        # ✅ Retornar la cantidad real de canales capturados

        return self.actual_channels

    

    def _audio_callback(self, indata, frames, time_info, status):

        """✅ Callback optimizado - usa memoryview sin copias + VU meters"""

        # ✅ Medir latencia de procesamiento completa

        process_start = time.time()

        

        if status:

            print(f"[RF] ⚠️ Status: {status}")

        
        # ✅ Procesar audio para cliente maestro
        if self.audio_mixer and self.channel_manager and self.master_client_id:
            try:
                if isinstance(indata, memoryview):
                    audio_array = np.frombuffer(indata, dtype=np.float32).reshape(-1, self.actual_channels)
                else:
                    audio_array = indata
                
                self.audio_mixer.process_and_broadcast(
                    audio_array,
                    self.channel_manager,
                    self.master_client_id
                )
            except Exception as e:
                if config.DEBUG:
                    print(f"[RF] ⚠️ Error maestro: {e}")

        # 🎚️ CALCULAR VU LEVELS (si está habilitado)

        if self.vu_callback:

            try:

                self.calculate_vu_levels(indata)

            except Exception as e:

                if config.DEBUG:

                    print(f"[RF] ⚠️ Error VU: {e}")

        

        audio_to_send = indata

        

        # PROCESAR CALLBACKS DE AUDIO

        with self.callback_lock:

            if not self.callbacks:

                return

            

            # ✅ Usar memoryview para evitar copias innecesarias

            if config.USE_MEMORYVIEW:

                # Pasar como memoryview (zero-copy)

                audio_view = memoryview(audio_to_send)

                

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
                        # Convertir a ndarray para hacer copia si es memoryview
                        if isinstance(audio_to_send, memoryview):
                            callback(np.array(audio_to_send))
                        else:
                            callback(audio_to_send.copy())

                    except Exception as e:

                        if config.DEBUG:

                            print(f"[RF] ❌ Error en callback '{name}': {e}")

        

        # ✅ Calcular latencia total de procesamiento y envío

        process_end = time.time()

        total_latency = (process_end - process_start) * 1000  # ms

        

        self.latency_measurements.append(total_latency)

        if len(self.latency_measurements) > self.max_latency_samples:

            self.latency_measurements.pop(0)

    

    def stop_capture(self):

        """Detener captura de audio"""

        if self.stream:

            self.running = False

            self.stream.stop()

            self.stream.close()

            self.stream_latency = 0.0  # ✅ Reset latencia

            print(f"[RF] 🛑 Captura detenida")

            

            with self.callback_lock:

                self.callbacks.clear()

            

            self.vu_callback = None

            self.vu_peak_hold.clear()

    

    def get_device_info(self):

        """Obtener información del dispositivo actual"""

        if self.stream:

            return {

                'channels': self.actual_channels,

                'running': self.running,

                'callbacks': len(self.callbacks),

                'rt_priority': self.rt_priority_set,

                'vu_enabled': self.vu_callback is not None

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

            'running': self.running,

            'vu_enabled': self.vu_callback is not None,

            'vu_update_interval': self.vu_update_interval

        }