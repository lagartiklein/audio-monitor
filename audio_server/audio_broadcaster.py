import threading, queue, time, logging, sys, os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import config



logger = logging.getLogger(__name__)



class AudioBroadcaster:

    def __init__(self, audio_capture, queue_size=None):

        self.audio_capture = audio_capture

        # OPTIMIZACIÓN: Usa el QUEUE_SIZE optimizado (3 en lugar de 10)

        self.queue_size = queue_size or config.QUEUE_SIZE

        self.output_queues = {}

        self.running = False

        self.broadcast_thread = None

        self.lock = threading.RLock()

        self.stats = {

            'total_packets': 0, 

            'dropped_packets': {}, 

            'queue_overruns': {}, 

            'active_consumers': 0, 

            'start_time': time.time(),

            'last_warning_time': 0

        }

        print("[AudioBroadcaster] 🎙️ Inicializado")

    

    def register_consumer(self, consumer_name):

        with self.lock:

            if consumer_name in self.output_queues:

                print(f"[AudioBroadcaster] ⚠️ Consumidor '{consumer_name}' ya registrado")

                return self.output_queues[consumer_name]

            

            consumer_queue = queue.Queue(maxsize=self.queue_size)

            self.output_queues[consumer_name] = consumer_queue

            self.stats['dropped_packets'][consumer_name] = 0

            self.stats['queue_overruns'][consumer_name] = 0

            self.stats['active_consumers'] = len(self.output_queues)

            print(f"[AudioBroadcaster] ✅ Consumidor '{consumer_name}' registrado (queue_size={self.queue_size})")

            return consumer_queue

    

    def start(self):

        if self.running: 

            print("[AudioBroadcaster] ⚠️ Ya está corriendo")

            return

        

        self.running = True

        self.broadcast_thread = threading.Thread(target=self._broadcast_loop, daemon=True, name="AudioBroadcaster")

        self.broadcast_thread.start()

        print("[AudioBroadcaster] ✅ Iniciado")

    

    def _broadcast_loop(self):

        print("[AudioBroadcaster] 🔄 Loop iniciado")

        

        packet_counter = 0

        last_log_time = time.time()

        

        while self.running:

            try:

                block_time = config.BLOCKSIZE / config.SAMPLE_RATE

                # OPTIMIZACIÓN: timeout reducido

                audio_data = self.audio_capture.get_audio_data(timeout=block_time * 1.5)

                if audio_data is None: 

                    continue

                

                self.stats['total_packets'] += 1

                packet_counter += 1

                

                # Log periódico de estadísticas

                if packet_counter >= 500:

                    current_time = time.time()

                    elapsed = current_time - last_log_time

                    rate = packet_counter / elapsed if elapsed > 0 else 0

                    print(f"[AudioBroadcaster] 📊 Audio: shape={audio_data.shape}, rate={rate:.1f} pkt/s, total={self.stats['total_packets']:,}")

                    last_log_time = current_time

                    packet_counter = 0

                

                with self.lock:

                    if not self.output_queues:

                        continue

                    

                    for consumer_name, consumer_queue in self.output_queues.items():

                        try:

                            consumer_queue.put_nowait(audio_data.copy())

                        except queue.Full:

                            self.stats['queue_overruns'][consumer_name] += 1

                            

                            # Intentar hacer espacio

                            try:

                                consumer_queue.get_nowait()

                                consumer_queue.put_nowait(audio_data.copy())

                            except:

                                self.stats['dropped_packets'][consumer_name] += 1

                                if self.stats['dropped_packets'][consumer_name] % 50 == 0:

                                    print(f"[AudioBroadcaster] ❌ '{consumer_name}' - {self.stats['dropped_packets'][consumer_name]} paquetes descartados")

            

            except Exception as e:

                print(f"[AudioBroadcaster] ❌ Error crítico: {e}")

                import traceback

                traceback.print_exc()

                time.sleep(0.01)

        

        print("[AudioBroadcaster] 🛑 Loop detenido")

    

    def stop(self):

        print("[AudioBroadcaster] Deteniendo...")

        self.running = False

        if self.broadcast_thread: 

            self.broadcast_thread.join(timeout=2)

        

        with self.lock:

            consumer_count = len(self.output_queues)

            print(f"[AudioBroadcaster] Desregistrando {consumer_count} consumidores...")

            for consumer_name in list(self.output_queues.keys()):

                self.unregister_consumer(consumer_name)

        

        uptime = time.time() - self.stats['start_time']

        print(f"[AudioBroadcaster] ✅ Detenido. Uptime: {uptime:.1f}s")

    

    def unregister_consumer(self, consumer_name):

        with self.lock:

            if consumer_name in self.output_queues:

                q = self.output_queues.pop(consumer_name)

                try:

                    while True: 

                        q.get_nowait()

                except queue.Empty: 

                    pass

                

                self.stats['active_consumers'] = len(self.output_queues)

                print(f"[AudioBroadcaster] ➖ '{consumer_name}' desregistrado")

    

    def get_stats(self):

        """Obtener estadísticas silenciosamente"""

        with self.lock:

            return {

                'total_packets': self.stats['total_packets'],

                'active_consumers': self.stats['active_consumers'],

                'dropped_packets': self.stats['dropped_packets'].copy(),

                'queue_overruns': self.stats['queue_overruns'].copy(),

                'uptime': time.time() - self.stats['start_time']

            }