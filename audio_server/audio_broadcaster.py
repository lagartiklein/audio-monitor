"""
Audio Broadcaster - Solución para múltiples servidores
Replica audio de una fuente única a múltiples consumidores sin race conditions
"""

import threading
import queue
import time
import logging
import sys
import os
from typing import Dict, Optional
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import config

logger = logging.getLogger(__name__)

class AudioBroadcaster:
    """
    Broadcaster que resuelve el problema de múltiples consumidores
    
    PROBLEMA ORIGINAL:
    - WebSocket y Nativo consumían del mismo audio_queue
    - Race condition: quien llama primero a .get() obtiene el paquete
    - El otro servidor se queda sin audio → frames perdidos
    
    SOLUCIÓN:
    - Un solo consumidor lee de audio_capture.audio_queue
    - Replica el audio a N colas (una por servidor)
    - Cada servidor lee de su propia cola sin conflictos
    """
    
    def __init__(self, audio_capture, queue_size: int = None):
        """
        Args:
            audio_capture: Instancia de AudioCapture
            queue_size: Tamaño de cada cola de salida (default: config.QUEUE_SIZE)
        """
        self.audio_capture = audio_capture
        self.queue_size = queue_size or config.QUEUE_SIZE
        
        # ✅ Colas de salida para cada servidor
        # Key: nombre del servidor (ej: "websocket", "native")
        # Value: queue.Queue con audio replicado
        self.output_queues: Dict[str, queue.Queue] = {}
        
        # Control
        self.running = False
        self.broadcast_thread = None
        self.lock = threading.RLock()
        
        # Estadísticas
        self.stats = {
            'total_packets': 0,
            'dropped_packets': {},  # Por servidor
            'queue_overruns': {},   # Por servidor
            'active_consumers': 0,
            'start_time': time.time()
        }
        
        logger.info("🎙️ AudioBroadcaster inicializado")
    
    def register_consumer(self, consumer_name: str) -> queue.Queue:
        """
        Registra un nuevo consumidor (servidor)
        
        Args:
            consumer_name: Nombre único del consumidor ("websocket", "native", etc)
            
        Returns:
            Queue dedicada para este consumidor
        """
        with self.lock:
            if consumer_name in self.output_queues:
                logger.warning(f"⚠️ Consumidor '{consumer_name}' ya existe, reusando queue")
                return self.output_queues[consumer_name]
            
            # Crear cola dedicada para este consumidor
            consumer_queue = queue.Queue(maxsize=self.queue_size)
            self.output_queues[consumer_name] = consumer_queue
            
            # Inicializar estadísticas
            self.stats['dropped_packets'][consumer_name] = 0
            self.stats['queue_overruns'][consumer_name] = 0
            self.stats['active_consumers'] = len(self.output_queues)
            
            logger.info(f"✅ Consumidor '{consumer_name}' registrado (queue size: {self.queue_size})")
            
            return consumer_queue
    
    def unregister_consumer(self, consumer_name: str):
        """
        Desregistra un consumidor
        
        Args:
            consumer_name: Nombre del consumidor a eliminar
        """
        with self.lock:
            if consumer_name in self.output_queues:
                # Limpiar cola
                consumer_queue = self.output_queues.pop(consumer_name)
                
                try:
                    while True:
                        consumer_queue.get_nowait()
                except queue.Empty:
                    pass
                
                self.stats['active_consumers'] = len(self.output_queues)
                
                logger.info(f"➖ Consumidor '{consumer_name}' desregistrado")
    
    def start(self):
        """Inicia el broadcaster"""
        if self.running:
            logger.warning("⚠️ Broadcaster ya está corriendo")
            return
        
        self.running = True
        self.stats['start_time'] = time.time()
        
        self.broadcast_thread = threading.Thread(
            target=self._broadcast_loop,
            daemon=True,
            name="AudioBroadcaster"
        )
        self.broadcast_thread.start()
        
        logger.info("✅ Broadcaster iniciado")
    
    def stop(self):
        """Detiene el broadcaster"""
        logger.info("🛑 Deteniendo broadcaster...")
        
        self.running = False
        
        if self.broadcast_thread and self.broadcast_thread.is_alive():
            self.broadcast_thread.join(timeout=2)
        
        # Limpiar todas las colas
        with self.lock:
            for consumer_name in list(self.output_queues.keys()):
                self.unregister_consumer(consumer_name)
        
        logger.info("✅ Broadcaster detenido")
    
    def _broadcast_loop(self):
        """
        Loop principal de broadcast
        
        FUNCIONAMIENTO:
        1. Lee UN paquete de audio_capture.audio_queue (único consumidor)
        2. REPLICA ese paquete a TODAS las colas de salida
        3. Si una cola está llena, descarta el paquete más viejo
        """
        logger.info("🎙️ Broadcast loop iniciado")
        
        consecutive_errors = 0
        max_consecutive_errors = 10
        
        while self.running:
            try:
                # ✅ ÚNICO CONSUMIDOR del audio_capture
                block_time = config.BLOCKSIZE / config.SAMPLE_RATE
                audio_data = self.audio_capture.get_audio_data(timeout=block_time * 2)
                
                if audio_data is None:
                    consecutive_errors += 1
                    if consecutive_errors > max_consecutive_errors:
                        logger.warning(f"⚠️ Muchos timeouts consecutivos: {consecutive_errors}")
                        time.sleep(0.01)
                    continue
                
                # Reset error counter en éxito
                consecutive_errors = 0
                self.stats['total_packets'] += 1
                
                # ✅ REPLICAR a todas las colas de salida
                with self.lock:
                    if not self.output_queues:
                        # Sin consumidores, continuar (no bloquear captura)
                        continue
                    
                    for consumer_name, consumer_queue in self.output_queues.items():
                        try:
                            # Intentar poner sin bloquear
                            consumer_queue.put_nowait(audio_data.copy())
                            
                        except queue.Full:
                            # Cola llena → remover el más viejo y poner el nuevo
                            self.stats['queue_overruns'][consumer_name] += 1
                            
                            try:
                                # Descartar paquete viejo
                                consumer_queue.get_nowait()
                                # Intentar de nuevo
                                consumer_queue.put_nowait(audio_data.copy())
                                
                                # Log solo si es significativo
                                if self.stats['queue_overruns'][consumer_name] % 100 == 0:
                                    logger.warning(
                                        f"⚠️ Queue overrun '{consumer_name}': "
                                        f"{self.stats['queue_overruns'][consumer_name]} veces"
                                    )
                            except:
                                # Si falla, contar como dropped
                                self.stats['dropped_packets'][consumer_name] += 1
                
                # Log periódico (cada 100 paquetes)
                if config.VERBOSE and self.stats['total_packets'] % 100 == 0:
                    self._log_stats()
            
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"❌ Error en broadcast loop: {e}")
                
                if consecutive_errors >= max_consecutive_errors:
                    logger.error("❌ Demasiados errores consecutivos, deteniendo broadcaster")
                    break
                
                time.sleep(0.01)
        
        logger.info("🛑 Broadcast loop detenido")
    
    def _log_stats(self):
        """Log de estadísticas periódicas"""
        uptime = time.time() - self.stats['start_time']
        
        logger.info(
            f"📊 Broadcaster: {self.stats['total_packets']} paquetes, "
            f"{self.stats['active_consumers']} consumidores, "
            f"{uptime:.1f}s uptime"
        )
        
        # Detalles por consumidor
        for consumer_name in self.output_queues.keys():
            dropped = self.stats['dropped_packets'].get(consumer_name, 0)
            overruns = self.stats['queue_overruns'].get(consumer_name, 0)
            
            if dropped > 0 or overruns > 0:
                logger.debug(
                    f"  '{consumer_name}': dropped={dropped}, overruns={overruns}"
                )
    
    def get_stats(self) -> dict:
        """
        Obtiene estadísticas del broadcaster
        
        Returns:
            Dict con estadísticas completas
        """
        with self.lock:
            uptime = time.time() - self.stats['start_time']
            
            # Calcular tasas de pérdida por consumidor
            drop_rates = {}
            for consumer_name in self.output_queues.keys():
                dropped = self.stats['dropped_packets'].get(consumer_name, 0)
                total = self.stats['total_packets']
                drop_rates[consumer_name] = (dropped / total * 100) if total > 0 else 0
            
            return {
                'uptime': round(uptime, 1),
                'total_packets': self.stats['total_packets'],
                'active_consumers': self.stats['active_consumers'],
                'consumers': list(self.output_queues.keys()),
                'dropped_packets': dict(self.stats['dropped_packets']),
                'queue_overruns': dict(self.stats['queue_overruns']),
                'drop_rates_percent': drop_rates,
                'running': self.running
            }
    
    def print_stats(self):
        """Imprime estadísticas formateadas"""
        stats = self.get_stats()
        
        print("\n📊 Estadísticas del Broadcaster:")
        print(f"    Uptime: {stats['uptime']}s")
        print(f"    Paquetes totales: {stats['total_packets']}")
        print(f"    Consumidores activos: {stats['active_consumers']}")
        
        if stats['consumers']:
            print(f"    Consumidores: {', '.join(stats['consumers'])}")
            
            for consumer in stats['consumers']:
                dropped = stats['dropped_packets'].get(consumer, 0)
                overruns = stats['queue_overruns'].get(consumer, 0)
                drop_rate = stats['drop_rates_percent'].get(consumer, 0)
                
                print(f"\n    📡 '{consumer}':")
                print(f"        Dropped: {dropped} ({drop_rate:.2f}%)")
                print(f"        Overruns: {overruns}")


# ✅ EJEMPLO DE USO
if __name__ == "__main__":
    print("🧪 Probando AudioBroadcaster...")
    
    # Simulación básica
    import config
    from audio_server.audio_capture import AudioCapture
    
    # Crear captura
    capture = AudioCapture()
    devices = capture.list_devices()
    
    if devices:
        # Iniciar captura
        capture.start_capture(devices[0]['id'])
        
        # Crear broadcaster
        broadcaster = AudioBroadcaster(capture)
        broadcaster.start()
        
        # Registrar consumidores
        websocket_queue = broadcaster.register_consumer("websocket")
        native_queue = broadcaster.register_consumer("native")
        
        print("✅ Broadcaster configurado")
        print("   • websocket_queue creada")
        print("   • native_queue creada")
        print("\n⏳ Probando por 5 segundos...")
        
        # Simular consumo
        start_time = time.time()
        ws_packets = 0
        native_packets = 0
        
        while time.time() - start_time < 5:
            # Consumir de websocket queue
            try:
                ws_data = websocket_queue.get(timeout=0.1)
                ws_packets += 1
            except queue.Empty:
                pass
            
            # Consumir de native queue
            try:
                native_data = native_queue.get(timeout=0.1)
                native_packets += 1
            except queue.Empty:
                pass
            
            time.sleep(0.01)
        
        print(f"\n📦 Paquetes recibidos:")
        print(f"   WebSocket: {ws_packets}")
        print(f"   Nativo: {native_packets}")
        
        # Mostrar estadísticas
        broadcaster.print_stats()
        
        # Limpiar
        broadcaster.stop()
        capture.stop_capture()
        
        print("\n✅ Prueba completada")
    else:
        print("❌ No hay dispositivos de audio disponibles")