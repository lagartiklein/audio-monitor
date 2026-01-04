#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🚀 Servidor de Audio - Modo Headless (Sin GUI)
Solo ejecuta el servidor WebSocket y TCP nativo
"""

import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from audio_server.channel_manager import ChannelManager
from audio_server.websocket_server import app, socketio, init_server
from audio_server.device_registry import init_device_registry
from audio_server.native_server import NativeAudioServer
import logging

# Configurar logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='[SERVER] %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    print("\n" + "="*70)
    print("  🎙️ FICHATECH AUDIO SERVER - HEADLESS MODE")
    print("="*70)
    print(f"  📡 WebSocket Port: {config.WEB_PORT}")
    print(f"  📱 Native Port: {config.NATIVE_PORT}")
    print("="*70 + "\n")
    
    try:
        # Inicializar device registry
        print("📁 Inicializando device registry...")
        init_device_registry()
        
        # Crear channel manager
        print("📊 Creando channel manager...")
        # Detectar número de canales (por defecto 8)
        num_channels = getattr(config, 'NUM_CHANNELS', 8)
        channel_manager = ChannelManager(num_channels)
        
        # Inicializar servidor
        print("🚀 Inicializando servidor WebSocket...")
        init_server(channel_manager)
        
        # Iniciar servidor nativo
        print("📱 Iniciando servidor nativo (TCP)...")
        native_server = NativeAudioServer(channel_manager)
        native_server.start()
        
        print("\n✅ SERVIDOR INICIADO CORRECTAMENTE\n")
        print(f"  🌐 http://127.0.0.1:{config.WEB_PORT}/")
        print(f"  📡 TCP 127.0.0.1:{config.NATIVE_PORT}\n")
        
        # Iniciar servidor web
        print("🚀 Iniciando Flask-SocketIO...\n")
        socketio.run(
            app,
            host='0.0.0.0',
            port=config.WEB_PORT,
            debug=False,
            use_reloader=False,
            log_output=False
        )
        
    except KeyboardInterrupt:
        print("\n\n⛔ Servidor detenido por usuario")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
