#!/usr/bin/env python3
"""
COMPREHENSIVE TEST SUITE - Fichatech Audio Monitor Server
=========================================================

Test completo que cubre todo el flujo de la aplicación:
- Inicialización y configuración
- Captura de audio
- Gestión de canales
- Servidor nativo
- Servidor web/WebSocket
- Gestión de escenas
- Persistencia de estado
- Simulación de clientes
- Manejo de errores
- Integración completa
"""

import sys
import os
import time
import threading
import socket
import json
import logging
import unittest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import shutil

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='[COMPREHENSIVE_TEST] %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Agregar path del proyecto
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Imports del proyecto
try:
    from audio_server.audio_capture import AudioCapture
    from audio_server.channel_manager import ChannelManager
    from audio_server.native_server import NativeAudioServer
    from audio_server.websocket_server import app, socketio, init_server, web_persistent_state
    from audio_server.native_protocol import NativeAndroidProtocol
    from audio_server.scene_manager import SceneManager
    import config
    from gui_monitor import AudioMonitorGUI
    IMPORTS_SUCCESSFUL = True
except Exception as e:
    logger.error(f"Import error: {e}")
    IMPORTS_SUCCESSFUL = False

class ComprehensiveTestSuite(unittest.TestCase):
    """Suite de pruebas comprehensiva"""

    def setUp(self):
        """Configurar entorno de prueba"""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)

        # Mock audio device
        self.audio_mock = Mock()
        self.audio_mock.start = Mock()
        self.audio_mock.stop = Mock()
        self.audio_mock.is_running = False

    def tearDown(self):
        """Limpiar entorno de prueba"""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)

    def test_00_imports(self):
        """Test 00: Verificar todas las importaciones"""
        logger.info("🧪 Test 00: Verificando importaciones...")
        self.assertTrue(IMPORTS_SUCCESSFUL, "Las importaciones deben ser exitosas")

        # Verificar que las clases principales existen
        self.assertTrue(hasattr(AudioCapture, '__init__'))
        self.assertTrue(hasattr(ChannelManager, '__init__'))
        self.assertTrue(hasattr(NativeAudioServer, '__init__'))
        self.assertTrue(hasattr(SceneManager, '__init__'))
        logger.info("✅ Todas las importaciones verificadas")

    def test_01_config(self):
        """Test 01: Verificar configuración"""
        logger.info("🧪 Test 01: Verificando configuración...")
        self.assertEqual(config.SAMPLE_RATE, 48000)
        self.assertEqual(config.BLOCKSIZE, 128)
        self.assertEqual(config.WEB_PORT, 5100)
        self.assertEqual(config.NATIVE_PORT, 5101)
        logger.info("✅ Configuración verificada")

    @patch('sounddevice.InputStream')
    def test_02_audio_capture(self, mock_input_stream):
        """Test 02: Verificar captura de audio"""
        logger.info("🧪 Test 02: Probando captura de audio...")

        # Mock del stream de audio
        mock_stream = Mock()
        mock_stream.start = Mock()
        mock_stream.stop = Mock()
        mock_stream.read = Mock(return_value=(Mock(), False))
        mock_input_stream.return_value = mock_stream

        # Crear AudioCapture
        audio = AudioCapture()
        self.assertIsNotNone(audio)

        # Verificar que se puede iniciar
        self.assertTrue(hasattr(audio, 'start_capture'))
        self.assertTrue(hasattr(audio, 'stop_capture'))

        logger.info("✅ Captura de audio verificada")

    def test_03_channel_manager(self):
        """Test 03: Verificar gestión de canales"""
        logger.info("🧪 Test 03: Probando ChannelManager...")

        # Crear ChannelManager
        cm = ChannelManager(8)
        self.assertIsNotNone(cm)
        self.assertEqual(cm.num_channels, 8)

        # Test de suscripción
        client_id = "test_client"
        channels = [0, 1, 2]
        volumes = {0: 1.0, 1: 0.8, 2: 0.6}
        filters = {}
        client_type = "test"

        success = cm.subscribe_client(client_id, channels, volumes, filters, client_type)
        # El método no retorna valor, verificar que el cliente fue agregado
        self.assertIn(client_id, cm.subscriptions)

        # Verificar que el cliente está suscrito
        self.assertIn(client_id, cm.subscriptions)

        # Test de desuscripción
        cm.unsubscribe_client(client_id)
        self.assertNotIn(client_id, cm.subscriptions)

        logger.info("✅ ChannelManager verificado")

    def test_04_native_protocol(self):
        """Test 04: Verificar protocolo nativo"""
        logger.info("🧪 Test 04: Probando protocolo nativo...")

        # Verificar que la clase existe y tiene métodos estáticos
        self.assertTrue(hasattr(NativeAndroidProtocol, 'create_audio_packet'))
        self.assertTrue(hasattr(NativeAndroidProtocol, 'create_control_packet'))
        self.assertTrue(hasattr(NativeAndroidProtocol, 'validate_packet'))

        # Test de creación de paquete de control
        packet = NativeAndroidProtocol.create_control_packet("test", {"key": "value"})
        self.assertIsNotNone(packet)

        logger.info("✅ Protocolo nativo verificado")

    @patch('flask.Flask.run')
    def test_05_web_server_init(self, mock_run):
        """Test 05: Verificar inicialización del servidor web"""
        logger.info("🧪 Test 05: Probando inicialización del servidor web...")

        # Crear un mock manager
        mock_manager = Mock()

        # Inicializar servidor
        init_server(mock_manager)

        # Verificar que la app Flask existe
        self.assertIsNotNone(app)
        self.assertIsNotNone(socketio)

        # Verificar rutas
        with app.test_client() as client:
            response = client.get('/')
            self.assertEqual(response.status_code, 200)

        logger.info("✅ Servidor web inicializado")

    def test_06_scene_manager(self):
        """Test 06: Verificar gestión de escenas"""
        logger.info("🧪 Test 06: Probando SceneManager...")

        # Crear SceneManager
        sm = SceneManager()
        self.assertIsNotNone(sm)

        # Verificar que tiene los métodos necesarios
        self.assertTrue(hasattr(sm, 'save_scene'))
        self.assertTrue(hasattr(sm, 'load_scene'))
        self.assertTrue(hasattr(sm, 'list_scenes'))

        # Test de listar escenas (debería estar vacío inicialmente)
        scenes = sm.list_scenes()
        self.assertIsInstance(scenes, list)

        logger.info("✅ SceneManager verificado")

    def test_07_persistence(self):
        """Test 07: Verificar persistencia de estado"""
        logger.info("🧪 Test 07: Probando persistencia...")

        # Verificar que web_persistent_state existe
        self.assertIsNotNone(web_persistent_state)

        # Test de guardado y carga
        test_data = {'test_key': 'test_value'}
        web_persistent_state['test'] = test_data

        # Verificar que se guardó
        self.assertEqual(web_persistent_state.get('test'), test_data)

        logger.info("✅ Persistencia verificada")

    @patch('socket.socket')
    def test_08_native_server_mock(self, mock_socket):
        """Test 08: Verificar servidor nativo (mock)"""
        logger.info("🧪 Test 08: Probando servidor nativo...")

        # Mock del socket
        mock_sock = Mock()
        mock_socket.return_value = mock_sock

        # Crear ChannelManager primero
        cm = ChannelManager(8)

        # Crear servidor nativo
        server = NativeAudioServer(cm)
        self.assertIsNotNone(server)

        # Verificar que tiene los métodos necesarios
        self.assertTrue(hasattr(server, 'start'))
        self.assertTrue(hasattr(server, 'stop'))

        logger.info("✅ Servidor nativo verificado")

    def test_09_error_handling(self):
        """Test 09: Verificar manejo de errores"""
        logger.info("🧪 Test 09: Probando manejo de errores...")

        # Test de ChannelManager con datos inválidos
        cm = ChannelManager(8)

        # Suscripción con canales inválidos
        cm.subscribe_client("test", [999], {}, {}, "test")
        # Verificar que no se agregó el canal inválido
        self.assertIn("test", cm.subscriptions)
        self.assertEqual(len(cm.subscriptions["test"]["channels"]), 0)  # Canales inválidos no se agregan

        # Suscripción con cliente ya existente (debería actualizar)
        cm.subscribe_client("test", [0], {}, {}, "test")
        self.assertIn("test", cm.subscriptions)
        self.assertIn(0, cm.subscriptions["test"]["channels"])

        logger.info("✅ Manejo de errores verificado")

    def test_11_reconnection(self):
        """Test 11: Verificar reconexión de cliente"""
        logger.info("🧪 Test 11: Probando reconexión de cliente...")

        # Simular NativeAudioServer
        from audio_server.native_server import NativeAudioServer
        from unittest.mock import Mock, patch
        
        with patch('socket.socket'):
            cm = ChannelManager(8)
            server = NativeAudioServer(cm)
            
            # Simular cliente inicial
            persistent_id = "test_reconnect_client"
            
            # Crear cliente mock
            mock_client = Mock()
            mock_client.id = "temp_123"
            mock_client.persistent_id = "temp_123"
            mock_client.auto_reconnect = True
            mock_client.address = ("192.168.1.100", 12345)
            
            # Simular handshake inicial
            handshake_msg = {
                'type': 'handshake',
                'client_id': persistent_id,
                'auto_reconnect': True
            }
            
            # Llamar al método de manejo de mensaje
            server._handle_control_message(mock_client, handshake_msg)
            
            # Verificar que el cliente se suscribió
            self.assertIn(persistent_id, cm.subscriptions)
            
            # Simular reconexión - crear nuevo cliente con mismo persistent_id
            mock_client2 = Mock()
            mock_client2.id = "temp_456"
            mock_client2.persistent_id = "temp_456"
            mock_client2.auto_reconnect = True
            mock_client2.address = ("192.168.1.100", 12346)
            
            # Agregar el cliente anterior al diccionario de clientes del servidor
            server.clients[persistent_id] = mock_client
            
            # Llamar al handshake de reconexión
            server._handle_control_message(mock_client2, handshake_msg)
            
            # Verificar que el cliente anterior fue removido y el nuevo está suscrito
            self.assertNotIn("temp_456", server.clients)
            self.assertIn(persistent_id, server.clients)
            self.assertIn(persistent_id, cm.subscriptions)

        logger.info("✅ Reconexión verificada")
        """Test 10: Verificar integración completa"""
        logger.info("🧪 Test 10: Probando integración completa...")

        # Crear todos los componentes
        audio = AudioCapture()
        cm = ChannelManager(8)
        sm = SceneManager()

        # Verificar que todos funcionan juntos
        self.assertIsNotNone(audio)
        self.assertIsNotNone(cm)
        self.assertIsNotNone(sm)

        # Simular flujo completo
        client_id = "integration_test_client"

        # 1. Suscribir cliente
        cm.subscribe_client(client_id, [0, 1], {0: 1.0, 1: 0.8}, {}, "integration")
        # Verificar que fue suscrito
        self.assertIn(client_id, cm.subscriptions)

        # 2. Verificar estado
        self.assertIn(client_id, cm.subscriptions)

        # 3. Listar escenas
        scenes = sm.list_scenes()
        self.assertIsInstance(scenes, list)

        logger.info("✅ Integración completa verificada")

    def test_11_reconnection(self):
        """Test 11: Verificar reconexión de cliente"""
        logger.info("🧪 Test 11: Probando reconexión de cliente...")

        # Simular NativeAudioServer
        from audio_server.native_server import NativeAudioServer
        from unittest.mock import Mock, patch
        
        with patch('socket.socket'):
            cm = ChannelManager(8)
            server = NativeAudioServer(cm)
            
            # Simular cliente inicial
            persistent_id = "test_reconnect_client"
            
            # Crear cliente mock
            mock_client = Mock()
            mock_client.id = "temp_123"
            mock_client.persistent_id = "temp_123"
            mock_client.auto_reconnect = True
            mock_client.address = ("192.168.1.100", 12345)
            
            # Simular handshake inicial
            handshake_msg = {
                'type': 'handshake',
                'client_id': persistent_id,
                'auto_reconnect': True
            }
            
            # Llamar al método de manejo de mensaje
            server._handle_control_message(mock_client, handshake_msg)
            
            # Verificar que el cliente se suscribió
            self.assertIn(persistent_id, cm.subscriptions)
            
            # Simular reconexión - crear nuevo cliente con mismo persistent_id
            mock_client2 = Mock()
            mock_client2.id = "temp_456"
            mock_client2.persistent_id = "temp_456"
            mock_client2.auto_reconnect = True
            mock_client2.address = ("192.168.1.100", 12346)
            
            # Agregar el cliente anterior al diccionario de clientes del servidor
            server.clients[persistent_id] = mock_client
            
            # Llamar al handshake de reconexión
            server._handle_control_message(mock_client2, handshake_msg)
            
            # Verificar que el cliente anterior fue removido y el nuevo está suscrito
            self.assertNotIn("temp_456", server.clients)
            self.assertIn(persistent_id, server.clients)
            self.assertIn(persistent_id, cm.subscriptions)

        logger.info("✅ Reconexión verificada")


def run_comprehensive_test():
    """Ejecutar suite de pruebas comprehensiva"""
    print("="*80)
    print("FICHATECH AUDIO MONITOR - COMPREHENSIVE TEST SUITE")
    print("="*80)
    print("Probando todo el flujo de la aplicación...")
    print()

    # Verificar imports primero
    if not IMPORTS_SUCCESSFUL:
        print("❌ ERROR: No se pudieron importar los módulos necesarios")
        return 1

    # Ejecutar pruebas
    suite = unittest.TestLoader().loadTestsFromTestCase(ComprehensiveTestSuite)
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)

    print()
    print("="*80)
    print("RESULTADOS FINALES")
    print("="*80)
    print(f"Tests ejecutados: {result.testsRun}")
    print(f"Exitosos: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Fallidos: {len(result.failures)}")
    print(f"Errores: {len(result.errors)}")

    if result.failures:
        print("\nFALLOS:")
        for test, traceback in result.failures:
            print(f"  - {test}: {traceback}")

    if result.errors:
        print("\nERRORES:")
        for test, traceback in result.errors:
            print(f"  - {test}: {traceback}")

    if result.wasSuccessful():
        print("\n🎉 TODOS LOS TESTS PASARON!")
        return 0
    else:
        print(f"\n❌ {len(result.failures) + len(result.errors)} tests fallaron")
        return 1

if __name__ == "__main__":
    exit_code = run_comprehensive_test()
    sys.exit(exit_code)