import threading, queue, time, logging, sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import config

logger = logging.getLogger(__name__)

class AudioBroadcaster:
    def __init__(self, audio_capture, queue_size=None):
        self.audio_capture = audio_capture
        self.queue_size = queue_size or config.QUEUE_SIZE
        self.output_queues = {}
        self.running = False
        self.broadcast_thread = None
        self.lock = threading.RLock()
        self.stats = {'total_packets': 0, 'dropped_packets': {}, 'queue_overruns': {}, 'active_consumers': 0, 'start_time': time.time()}
        print("[AudioBroadcaster] 🎙️ AudioBroadcaster inicializado")
        logger.info("🎙️ AudioBroadcaster inicializado")
    
    def register_consumer(self, consumer_name):
        with self.lock:
            if consumer_name in self.output_queues:
                print(f"[AudioBroadcaster] ⚠️  Consumidor '{consumer_name}' ya registrado")
                return self.output_queues[consumer_name]
            
            consumer_queue = queue.Queue(maxsize=self.queue_size)
            self.output_queues[consumer_name] = consumer_queue
            self.stats['dropped_packets'][consumer_name] = 0
            self.stats['queue_overruns'][consumer_name] = 0
            self.stats['active_consumers'] = len(self.output_queues)
            print(f"[AudioBroadcaster] ✅ Consumidor '{consumer_name}' registrado. Consumidores activos: {self.stats['active_consumers']}")
            logger.info(f"✅ Consumidor '{consumer_name}' registrado")
            return consumer_queue
    
    def start(self):
        if self.running: 
            print("[AudioBroadcaster] ⚠️  Broadcaster ya está corriendo")
            return
        
        self.running = True
        self.broadcast_thread = threading.Thread(target=self._broadcast_loop, daemon=True, name="AudioBroadcaster")
        self.broadcast_thread.start()
        print("[AudioBroadcaster] ✅ Broadcaster iniciado")
        logger.info("✅ Broadcaster iniciado")
    
    def _broadcast_loop(self):
        print("[AudioBroadcaster] 🔄 Broadcast loop iniciado")
        logger.info("🎙️ Broadcast loop iniciado")
        
        while self.running:
            try:
                block_time = config.BLOCKSIZE / config.SAMPLE_RATE
                audio_data = self.audio_capture.get_audio_data(timeout=block_time * 2)
                if audio_data is None: 
                    continue
                
                self.stats['total_packets'] += 1
                if self.stats['total_packets'] % 100 == 0:
                    print(f"[AudioBroadcaster] 📊 Paquetes procesados: {self.stats['total_packets']}")
                
                with self.lock:
                    if not self.output_queues:
                        continue
                    
                    active_consumers = len(self.output_queues)
                    for consumer_name, consumer_queue in self.output_queues.items():
                        try:
                            consumer_queue.put_nowait(audio_data.copy())
                        except queue.Full:
                            self.stats['queue_overruns'][consumer_name] += 1
                            print(f"[AudioBroadcaster] ⚠️  Cola llena para '{consumer_name}', sobrecargas: {self.stats['queue_overruns'][consumer_name]}")
                            
                            try:
                                consumer_queue.get_nowait()
                                consumer_queue.put_nowait(audio_data.copy())
                            except:
                                self.stats['dropped_packets'][consumer_name] += 1
                                print(f"[AudioBroadcaster] ❌ Paquete descartado para '{consumer_name}', total: {self.stats['dropped_packets'][consumer_name]}")
            
            except Exception as e:
                print(f"[AudioBroadcaster] ❌ Error en broadcast loop: {e}")
                logger.error(f"❌ Error en broadcast loop: {e}")
                time.sleep(0.01)
        
        print("[AudioBroadcaster] 🛑 Broadcast loop detenido")
        logger.info("🛑 Broadcast loop detenido")
    
    def stop(self):
        print("[AudioBroadcaster] Deteniendo broadcaster...")
        self.running = False
        if self.broadcast_thread: 
            self.broadcast_thread.join(timeout=2)
        
        with self.lock:
            consumer_count = len(self.output_queues)
            print(f"[AudioBroadcaster] Desregistrando {consumer_count} consumidores...")
            for consumer_name in list(self.output_queues.keys()):
                self.unregister_consumer(consumer_name)
        
        uptime = time.time() - self.stats['start_time']
        print(f"[AudioBroadcaster] ✅ Broadcaster detenido. Uptime: {uptime:.1f}s, Paquetes totales: {self.stats['total_packets']}")
        logger.info("✅ Broadcaster detenido")
    
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
                print(f"[AudioBroadcaster] ➖ Consumidor '{consumer_name}' desregistrado. Consumidores activos: {self.stats['active_consumers']}")
                logger.info(f"➖ Consumidor '{consumer_name}' desregistrado")