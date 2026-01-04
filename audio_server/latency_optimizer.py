"""
⚡ Latency Optimizer - Monitoreo y reducción de latencia WebSocket
✅ Debouncing de parámetros frecuentes
✅ Batching de actualizaciones
✅ Logging de latencias
"""

import time
import logging
import threading
from collections import defaultdict
from typing import Dict, Callable, Any

logger = logging.getLogger(__name__)


class LatencyOptimizer:
    """
    ✅ Sistema para reducir latencia en cambios frecuentes de parámetros
    - Debounce: agrupa cambios múltiples dentro de una ventana de tiempo
    - Batching: envía cambios en lotes en lugar de uno por uno
    - Latency tracking: mide tiempos de respuesta
    """

    def __init__(self, debounce_ms: int = 50):
        self.debounce_ms = debounce_ms / 1000.0  # convertir a segundos
        self.pending_updates = {}  # client_id -> {'gains': {...}, 'pans': {...}, ...}
        self.debounce_timers = {}  # client_id -> threading.Timer
        self.lock = threading.Lock()
        
        # Latency tracking
        self.latency_samples = defaultdict(list)  # event_type -> [latencies_ms]
        self.max_samples = 100  # Mantener último 100 muestras
        
        logger.info(f"[LatencyOptimizer] ✅ Inicializado (debounce: {debounce_ms}ms)")

    def queue_parameter_update(self, client_id: str, param_type: str, channel: int, value: float):
        """
        Encolar una actualización de parámetro con debouncing
        
        Args:
            client_id: ID del cliente
            param_type: 'gain' o 'pan'
            channel: Canal afectado
            value: Valor del parámetro
        """
        with self.lock:
            # Inicializar estructura si no existe
            if client_id not in self.pending_updates:
                self.pending_updates[client_id] = {'gains': {}, 'pans': {}}
            
            # Almacenar el cambio
            key = 'gains' if param_type == 'gain' else 'pans'
            self.pending_updates[client_id][key][channel] = value
            
            # Cancelar timer anterior si existe
            if client_id in self.debounce_timers:
                self.debounce_timers[client_id].cancel()
            
            # Crear nuevo timer (ejecutará después de debounce_ms)
            timer = threading.Timer(
                self.debounce_ms,
                self._flush_pending_updates,
                args=[client_id]
            )
            self.debounce_timers[client_id] = timer
            timer.start()

    def _flush_pending_updates(self, client_id: str):
        """Enviar los cambios pendientes acumulados"""
        with self.lock:
            if client_id not in self.pending_updates:
                return
            
            updates = self.pending_updates.pop(client_id)
            if client_id in self.debounce_timers:
                del self.debounce_timers[client_id]
        
        # Aquí retornar los updates para que el caller los envíe
        if updates['gains'] or updates['pans']:
            logger.debug(f"[LatencyOptimizer] 🚀 Flush updates: {client_id[:8]} "
                        f"(gains: {len(updates['gains'])}, pans: {len(updates['pans'])})")
        
        return updates if (updates['gains'] or updates['pans']) else None

    def get_pending_updates(self, client_id: str) -> Dict[str, Dict[int, float]] | None:
        """Obtener y limpiar updates pendientes"""
        with self.lock:
            if client_id in self.pending_updates:
                updates = self.pending_updates.pop(client_id)
                if client_id in self.debounce_timers:
                    self.debounce_timers[client_id].cancel()
                    del self.debounce_timers[client_id]
                
                if updates['gains'] or updates['pans']:
                    return updates
        
        return None

    def record_latency(self, event_type: str, latency_ms: float):
        """Registrar muestra de latencia"""
        with self.lock:
            samples = self.latency_samples[event_type]
            samples.append(latency_ms)
            
            # Mantener solo las últimas N muestras
            if len(samples) > self.max_samples:
                samples.pop(0)

    def get_latency_stats(self) -> Dict[str, Dict[str, float]]:
        """Obtener estadísticas de latencia"""
        import statistics
        
        stats = {}
        with self.lock:
            for event_type, samples in self.latency_samples.items():
                if samples:
                    stats[event_type] = {
                        'avg': statistics.mean(samples),
                        'min': min(samples),
                        'max': max(samples),
                        'samples': len(samples)
                    }
        
        return stats

    def log_latency_summary(self):
        """Loguear resumen de latencias"""
        stats = self.get_latency_stats()
        if stats:
            logger.info("[LatencyOptimizer] 📊 Latencia WebSocket:")
            for event_type, data in stats.items():
                logger.info(f"  {event_type}: avg={data['avg']:.2f}ms, "
                           f"min={data['min']:.2f}ms, max={data['max']:.2f}ms")


# Instancia global
_optimizer_instance = None


def get_optimizer(debounce_ms: int = 50) -> LatencyOptimizer:
    """Obtener o crear instancia global del optimizer"""
    global _optimizer_instance
    if _optimizer_instance is None:
        _optimizer_instance = LatencyOptimizer(debounce_ms)
    return _optimizer_instance
