"""
WebRTC Bridge - Conecta el sistema existente con WebRTC
Maneja clientes tanto WebSocket como WebRTC simultáneamente
"""

import asyncio
import threading
import time
import logging
from typing import Dict
import config_webrtc as config

logger = logging.getLogger(__name__)

class WebRTCBridge:
    """
    Bridge que coordina entre WebSocket y WebRTC
    Los clientes pueden usar cualquier protocolo
    """
    
    def __init__(self, audio_capture, channel_manager, webrtc_server):
        self.audio_capture = audio_capture
        self.channel_manager = channel_manager
        self.webrtc_server = webrtc_server
        
        # Seguimiento de clientes por protocolo
        self.client_protocols: Dict[str, str] = {}  # client_id -> 'websocket' | 'webrtc'
        
        # Estado
        self.running = False
        self.bridge_thread = None
        
        # Métricas
        self.metrics = {
            'websocket_clients': 0,
            'webrtc_clients': 0,
            'total_audio_data_sent': 0,
            'start_time': time.time()
        }
        
        logger.info("WebRTC Bridge inicializado")
    
    def start(self):
        """Inicia el bridge"""
        if self.running:
            return
        
        self.running = True
        self.bridge_thread = threading.Thread(
            target=self._run_bridge_loop,
            daemon=True,
            name="WebRTC-Bridge"
        )
        self.bridge_thread.start()
        
        logger.info("WebRTC Bridge iniciado")
    
    def _run_bridge_loop(self):
        """Ejecuta el loop principal del bridge en un thread separado"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(self._bridge_loop())
        except Exception as e:
            logger.error(f"Error en bridge loop: {e}")
        finally:
            loop.close()
    
    async def _bridge_loop(self):
        """Loop principal de procesamiento del bridge"""
        logger.info("Bridge loop iniciado")
        
        # Iniciar servidor WebRTC
        await self.webrtc_server.start()
        
        try:
            while self.running:
                # Actualizar métricas
                self._update_metrics()
                
                # Mostrar estadísticas periódicamente
                if config.SHOW_METRICS:
                    elapsed = time.time() - self.metrics['start_time']
                    if elapsed > 0 and elapsed % 5 < 0.1:  # Cada ~5 segundos
                        self._log_stats()
                
                await asyncio.sleep(0.1)
                
        except asyncio.CancelledError:
            pass
        finally:
            # Detener servidor WebRTC
            await self.webrtc_server.stop()
        
        logger.info("Bridge loop detenido")
    
    def _update_metrics(self):
        """Actualiza las métricas del bridge"""
        # Contar clientes por protocolo
        ws_count = 0
        rtc_count = 0
        
        for client_id, protocol in self.client_protocols.items():
            if protocol == 'websocket':
                ws_count += 1
            elif protocol == 'webrtc':
                rtc_count += 1
        
        self.metrics['websocket_clients'] = ws_count
        self.metrics['webrtc_clients'] = rtc_count
    
    def _log_stats(self):
        """Muestra estadísticas del bridge"""
        stats = self.webrtc_server.get_stats()
        
        logger.info(
            f"[🌉 Bridge] WebSocket: {self.metrics['websocket_clients']} | "
            f"WebRTC: {self.metrics['webrtc_clients']} | "
            f"RTC Conns: {stats.get('active_connections', 0)} | "
            f"Data: {stats.get('total_bytes_sent', 0) / 1024 / 1024:.1f} MB"
        )
    
    def set_client_protocol(self, client_id: str, protocol: str):
        """Establece el protocolo usado por un cliente"""
        if protocol not in ['websocket', 'webrtc']:
            logger.warning(f"Protocolo inválido: {protocol}")
            return
        
        self.client_protocols[client_id] = protocol
        
        # Actualizar en channel manager
        self.channel_manager.subscriptions[client_id]['protocol'] = protocol
        
        logger.info(f"Cliente {client_id[:8]} usando protocolo: {protocol}")
    
    def get_client_protocol(self, client_id: str) -> str:
        """Obtiene el protocolo usado por un cliente"""
        return self.client_protocols.get(client_id, 'websocket')
    
    def remove_client(self, client_id: str):
        """Elimina un cliente del bridge"""
        if client_id in self.client_protocols:
            protocol = self.client_protocols[client_id]
            del self.client_protocols[client_id]
            
            # Cerrar conexión WebRTC si es necesario
            if protocol == 'webrtc':
                asyncio.run_coroutine_threadsafe(
                    self.webrtc_server.close_connection(client_id),
                    self.webrtc_server.loop
                )
            
            logger.info(f"Cliente {client_id[:8]} removido del bridge")
    
    def stop(self):
        """Detiene el bridge"""
        self.running = False
        if self.bridge_thread and self.bridge_thread.is_alive():
            self.bridge_thread.join(timeout=2)
        
        logger.info("WebRTC Bridge detenido")
    
    def get_metrics(self) -> dict:
        """Devuelve métricas del bridge"""
        webrtc_stats = self.webrtc_server.get_stats()
        
        return {
            **self.metrics,
            **webrtc_stats,
            'uptime': time.time() - self.metrics['start_time'],
            'protocol_distribution': {
                'websocket': self.metrics['websocket_clients'],
                'webrtc': self.metrics['webrtc_clients']
            }
        }