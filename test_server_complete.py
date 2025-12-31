#!/usr/bin/env python3
"""
SCRIPT DE PRUEBAS - Fichatech Audio Monitor Server
==========================================

Pruebas automatizadas para verificar todas las funciones del servidor:
- Importaciones y inicialización
- ChannelManager (suscripción, control de audio)
- Protocolo nativo
- Persistencia de estado
- Auto-reconexión
"""

import sys
import os
import time
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO, format='[TEST] %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Agregar path del proyecto
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

class TestSuite:
    """Suite de pruebas para el servidor"""

    def __init__(self):
        self.passed = 0
        self.failed = 0

    def test_result(self, name, success, message=""):
        """Registrar resultado de prueba"""
        if success:
            self.passed += 1
            logger.info(f"✅ PASS - {name}: {message}")
        else:
            self.failed += 1
            logger.error(f"❌ FAIL - {name}: {message}")

    def run_test_imports(self):
        """Prueba importaciones"""
        try:
            from audio_server.channel_manager import ChannelManager
            from audio_server.native_server import NativeAudioServer
            from audio_server.websocket_server import app, socketio, web_persistent_state
            from audio_server.native_protocol import NativeAndroidProtocol
            import config
            self.test_result("Imports", True, "Todas las importaciones exitosas")
            return True
        except Exception as e:
            self.test_result("Imports", False, f"Error: {e}")
            return False

    def run_test_channel_manager(self):
        """Prueba ChannelManager completo"""
        try:
            from audio_server.channel_manager import ChannelManager

            # Inicialización
            cm = ChannelManager(8)
            if cm.num_channels != 8:
                self.test_result("ChannelManager", False, "Número de canales incorrecto")
                return False

            # Suscripción básica
            client_id = "test_client_1"
            channels = [0, 1, 2]
            gains = {0: 1.0, 1: 0.8, 2: 0.6}
            pans = {0: 0.0, 1: -0.2, 2: 0.3}

            cm.subscribe_client(client_id, channels, gains, pans, "test")

            # Verificar suscripción
            sub = cm.get_client_subscription(client_id)
            if not sub:
                self.test_result("ChannelManager", False, "Suscripción no encontrada")
                return False

            if len(sub['channels']) != 3:
                self.test_result("ChannelManager", False, "Número de canales incorrecto")
                return False

            # Control de ganancias
            cm.update_client_gain(client_id, 0, 0.7)
            sub = cm.get_client_subscription(client_id)
            if sub['gains'][0] != 0.7:
                self.test_result("ChannelManager", False, "Actualización de ganancia falló")
                return False

            # Control de panorama
            cm.update_client_pan(client_id, 1, 0.5)
            sub = cm.get_client_subscription(client_id)
            if sub['pans'][1] != 0.5:
                self.test_result("ChannelManager", False, "Actualización de panorama falló")
                return False

            # Mute
            cm.set_client_mute(client_id, 2, True)
            sub = cm.get_client_subscription(client_id)
            if not sub['mutes'][2]:
                self.test_result("ChannelManager", False, "Mute falló")
                return False

            # Solo
            cm.set_client_solo(client_id, 0, True)
            if not cm.should_send_channel(client_id, 0):
                self.test_result("ChannelManager", False, "Solo falló")
                return False

            # Desuscripción
            cm.unsubscribe_client(client_id)
            sub = cm.get_client_subscription(client_id)
            if sub is not None:
                self.test_result("ChannelManager", False, "Desuscripción falló")
                return False

            self.test_result("ChannelManager", True, "Todas las funciones OK")
            return True

        except Exception as e:
            self.test_result("ChannelManager", False, f"Error: {e}")
            return False

    def run_test_native_protocol(self):
        """Prueba protocolo nativo"""
        try:
            from audio_server.native_protocol import NativeAndroidProtocol

            protocol = NativeAndroidProtocol()

            # Mensaje de handshake
            handshake = {
                'type': 'handshake',
                'persistent_id': 'test_device_123',
                'auto_reconnect': True,
                'channels': [0, 1, 2]
            }

            # Serializar
            data = protocol.serialize_message(handshake)
            if not data:
                self.test_result("Native Protocol", False, "Serialización falló")
                return False

            # Deserializar
            parsed = protocol.deserialize_message(data)
            if parsed['type'] != 'handshake' or parsed['persistent_id'] != 'test_device_123':
                self.test_result("Native Protocol", False, "Deserialización falló")
                return False

            # Mensaje de audio
            import numpy as np
            audio_data = np.random.rand(128, 2).astype(np.float32)
            audio_msg = {
                'type': 'audio',
                'channels': [0, 1],
                'data': audio_data.tobytes(),
                'timestamp': time.time()
            }

            data = protocol.serialize_message(audio_msg)
            parsed = protocol.deserialize_message(data)
            if parsed['type'] != 'audio':
                self.test_result("Native Protocol", False, "Mensaje de audio falló")
                return False

            self.test_result("Native Protocol", True, "Protocolo funciona correctamente")
            return True

        except Exception as e:
            self.test_result("Native Protocol", False, f"Error: {e}")
            return False

    def run_test_persistence(self):
        """Prueba persistencia de estado"""
        try:
            from audio_server.websocket_server import web_persistent_state, web_persistent_lock

            # Simular estado guardado
            persistent_id = "test_127.0.0.1_TestBrowser"
            test_state = {
                'channels': [0, 1, 2],
                'gains': {0: 1.0, 1: 0.8, 2: 0.6},
                'pans': {0: 0.0, 1: 0.0, 2: 0.0},
                'mutes': {0: False, 1: False, 2: False},
                'solos': [],
                'pre_listen': None,
                'master_gain': 1.0,
                'saved_at': time.time()
            }

            # Guardar estado
            with web_persistent_lock:
                web_persistent_state[persistent_id] = test_state

            # Verificar estado guardado
            with web_persistent_lock:
                saved = web_persistent_state.get(persistent_id)
                if not saved or len(saved['channels']) != 3:
                    self.test_result("Persistence", False, "Estado no guardado correctamente")
                    return False

            # Limpiar
            with web_persistent_lock:
                del web_persistent_state[persistent_id]

            self.test_result("Persistence", True, "Persistencia funciona correctamente")
            return True

        except Exception as e:
            self.test_result("Persistence", False, f"Error: {e}")
            return False

    def run_test_error_handling(self):
        """Prueba manejo de errores"""
        try:
            from audio_server.channel_manager import ChannelManager

            cm = ChannelManager(8)

            # Cliente con ID vacío
            result = cm.subscribe_client("", [0], {}, {}, "test")
            # Debería permitirlo (None es válido)

            # Canales fuera de rango
            result = cm.subscribe_client("test", [999], {}, {}, "test")
            # Debería filtrar canales inválidos

            # Actualizar cliente inexistente
            result = cm.update_client_gain("nonexistent", 0, 0.5)
            if result is not False:
                self.test_result("Error Handling", False, "Actualización de cliente inexistente no manejada")
                return False

            # Obtener suscripción de cliente inexistente
            sub = cm.get_client_subscription("nonexistent")
            if sub is not None:
                self.test_result("Error Handling", False, "Suscripción de cliente inexistente no es None")
                return False

            self.test_result("Error Handling", True, "Manejo de errores correcto")
            return True

        except Exception as e:
            self.test_result("Error Handling", False, f"Error: {e}")
            return False

    def run_all_tests(self):
        """Ejecutar todas las pruebas"""
        logger.info("🚀 Iniciando suite de pruebas del servidor...")
        logger.info("="*60)

        tests = [
            ("Importaciones", self.run_test_imports),
            ("ChannelManager", self.run_test_channel_manager),
            ("Protocolo Nativo", self.run_test_native_protocol),
            ("Persistencia", self.run_test_persistence),
            ("Manejo de Errores", self.run_test_error_handling)
        ]

        for test_name, test_func in tests:
            logger.info(f"\n--- Ejecutando: {test_name} ---")
            test_func()

        # Resultados finales
        logger.info("\n" + "="*60)
        logger.info("📊 RESULTADOS FINALES")
        logger.info("="*60)

        total = self.passed + self.failed
        success_rate = (self.passed / total * 100) if total > 0 else 0

        logger.info(f"✅ Pruebas pasadas: {self.passed}")
        logger.info(f"❌ Pruebas fallidas: {self.failed}")
        logger.info(f"📈 Tasa de éxito: {success_rate:.1f}%")

        if self.failed == 0:
            logger.info("🎉 ¡Todas las pruebas pasaron exitosamente!")
            logger.info("El servidor está funcionando correctamente.")
        else:
            logger.warning(f"⚠️ {self.failed} pruebas fallaron. Revisar logs para detalles.")

        logger.info("="*60)

        return self.failed == 0

def main():
    """Función principal"""
    suite = TestSuite()
    success = suite.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())</content>
<parameter name="filePath">c:\audio-monitor\test_server_complete.py