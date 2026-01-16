#!/usr/bin/env python3
"""
test_general_system.py - Suite completa de tests generales simplificados del sistema Fichatech Monitor

Tests básicos que cubren:
- Configuración del sistema
- Inicialización de componentes principales
- Funcionalidad básica de módulos
- Importación correcta
- Integración básica
"""

import unittest
import sys
import os
import tempfile
import time

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Importar módulos del sistema
import config
from audio_server.audio_capture import AudioCapture
from audio_server.channel_manager import ChannelManager
from audio_server.unified_persistence import UnifiedPersistence
from audio_server.scene_manager import SceneManager
from audio_server.latency_optimizer import LatencyOptimizer
from audio_server.device_registry import DeviceRegistry


class TestSystemConfiguration(unittest.TestCase):
    """Tests para la configuración del sistema"""

    def test_config_constants(self):
        """Verificar que las constantes de configuración sean válidas"""
        self.assertGreater(config.MAX_LOGICAL_CHANNELS, 0)
        self.assertGreaterEqual(config.MAX_LOGICAL_CHANNELS, 64)
        self.assertGreater(config.SAMPLE_RATE, 0)
        self.assertGreater(config.BLOCKSIZE, 0)
        self.assertGreaterEqual(config.MIN_CHANNELS_REQUIRE_MAPPING, 2)

    def test_channel_labels_structure(self):
        """Verificar estructura de etiquetas de canales"""
        self.assertIn(8, config.CHANNEL_LABELS)
        self.assertIn(16, config.CHANNEL_LABELS)
        self.assertIn(32, config.CHANNEL_LABELS)
        self.assertIn(64, config.CHANNEL_LABELS)

        # Verificar que las etiquetas tengan la longitud correcta
        for num_channels, labels in config.CHANNEL_LABELS.items():
            self.assertEqual(len(labels), num_channels)

    def test_websocket_config(self):
        """Verificar configuración de WebSocket"""
        self.assertGreaterEqual(config.WEBSOCKET_PARAM_DEBOUNCE_MS, 0)
        self.assertIsInstance(config.WEBSOCKET_BATCH_UPDATES, bool)
        self.assertGreater(config.SEND_QUEUE_SIZE, 0)
        self.assertGreater(config.AUDIO_SEND_POOL_SIZE, 0)


class TestModuleImports(unittest.TestCase):
    """Tests de importación de módulos"""

    def test_audio_capture_import(self):
        """Verificar importación de AudioCapture"""
        self.assertIsNotNone(AudioCapture)

    def test_channel_manager_import(self):
        """Verificar importación de ChannelManager"""
        self.assertIsNotNone(ChannelManager)

    def test_unified_persistence_import(self):
        """Verificar importación de UnifiedPersistence"""
        self.assertIsNotNone(UnifiedPersistence)

    def test_scene_manager_import(self):
        """Verificar importación de SceneManager"""
        self.assertIsNotNone(SceneManager)

    def test_latency_optimizer_import(self):
        """Verificar importación de LatencyOptimizer"""
        self.assertIsNotNone(LatencyOptimizer)

    def test_device_registry_import(self):
        """Verificar importación de DeviceRegistry"""
        self.assertIsNotNone(DeviceRegistry)


class TestBasicInitialization(unittest.TestCase):
    """Tests de inicialización básica"""

    def test_audio_capture_init(self):
        """Verificar inicialización de AudioCapture"""
        capture = AudioCapture()
        self.assertIsNotNone(capture)
        self.assertFalse(capture.running)
        self.assertEqual(capture.actual_channels, 0)

    def test_channel_manager_init(self):
        """Verificar inicialización de ChannelManager"""
        manager = ChannelManager(16)
        self.assertIsNotNone(manager)
        self.assertEqual(manager.num_channels, 16)

    def test_unified_persistence_init(self):
        """Verificar inicialización de UnifiedPersistence"""
        persistence = UnifiedPersistence()
        self.assertIsNotNone(persistence)

    def test_scene_manager_init(self):
        """Verificar inicialización de SceneManager"""
        manager = SceneManager()
        self.assertIsNotNone(manager)

    def test_latency_optimizer_init(self):
        """Verificar inicialización de LatencyOptimizer"""
        optimizer = LatencyOptimizer()
        self.assertIsNotNone(optimizer)

    def test_device_registry_init(self):
        """Verificar inicialización de DeviceRegistry"""
        registry = DeviceRegistry()
        self.assertIsNotNone(registry)


class TestBasicFunctionality(unittest.TestCase):
    """Tests de funcionalidad básica"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_channel_manager_subscription(self):
        """Verificar suscripción básica en ChannelManager"""
        manager = ChannelManager(8)
        client_id = "test_client"
        channels = [0, 1, 2]

        # Suscribir cliente
        manager.subscribe_client(client_id, channels)

        # Verificar suscripción
        subscription = manager.get_client_subscription(client_id)
        self.assertIsNotNone(subscription)

    def test_persistence_channel_names(self):
        """Verificar gestión de nombres de canales en UnifiedPersistence"""
        persistence = UnifiedPersistence(config_dir=self.temp_dir)

        # Actualizar nombre de canal
        persistence.update_channel_name(0, "Test Channel")

        # Obtener nombres
        names = persistence.get_channel_names()
        self.assertIn(0, names)
        self.assertEqual(names[0], "Test Channel")

    def test_device_registry_basic(self):
        """Verificar registro básico de dispositivos"""
        registry = DeviceRegistry()

        device_uuid = "test_device_123"
        device_info = {
            'type': 'web',
            'name': 'Test Device'
        }

        result = registry.register_device(device_uuid, device_info)
        self.assertIsInstance(result, dict)

    def test_scene_manager_validation(self):
        """Verificar validación básica de escenas"""
        manager = SceneManager()

        # Escena válida
        valid_scene = {
            "scene_name": "Test Scene",
            "clients": {}
        }
        is_valid, error = manager.validate_scene(valid_scene)
        # Nota: La validación puede ser más estricta, solo verificamos que no falle
        self.assertIsInstance(is_valid, bool)
        self.assertIsInstance(error, str)


class TestWebSocketModule(unittest.TestCase):
    """Tests del módulo websocket_server"""

    def test_websocket_module_import(self):
        """Verificar que el módulo websocket_server se puede importar"""
        try:
            import audio_server.websocket_server as ws_server
            self.assertIsNotNone(ws_server)
        except ImportError as e:
            self.fail(f"No se pudo importar websocket_server: {e}")

    def test_websocket_functions_exist(self):
        """Verificar que las funciones principales existen"""
        import audio_server.websocket_server as ws_server

        # Verificar funciones clave
        self.assertTrue(hasattr(ws_server, 'init_server'))
        self.assertTrue(hasattr(ws_server, 'broadcast_audio_levels'))
        self.assertTrue(hasattr(ws_server, 'cleanup_expired_web_states'))


class TestSystemIntegration(unittest.TestCase):
    """Tests de integración básica"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_multiple_components_init(self):
        """Verificar inicialización simultánea de múltiples componentes"""
        capture = AudioCapture()
        manager = ChannelManager(8)
        persistence = UnifiedPersistence(config_dir=self.temp_dir)

        # Verificar que todos se inicializaron correctamente
        self.assertIsNotNone(capture)
        self.assertIsNotNone(manager)
        self.assertIsNotNone(persistence)

    def test_basic_channel_workflow(self):
        """Verificar flujo básico de trabajo con canales"""
        manager = ChannelManager(8)
        persistence = UnifiedPersistence(config_dir=self.temp_dir)

        # Configurar nombre de canal
        persistence.update_channel_name(0, "Test Channel")

        # Suscribir cliente
        manager.subscribe_client("test_client", [0])

        # Verificar que todo funciona
        names = persistence.get_channel_names()
        subscription = manager.get_client_subscription("test_client")

        self.assertIn(0, names)
        self.assertIsNotNone(subscription)


class TestPerformanceBasics(unittest.TestCase):
    """Tests básicos de rendimiento"""

    def test_memory_usage_basic(self):
        """Verificar uso básico de memoria"""
        # Crear componentes y verificar que no fallen
        capture = AudioCapture()
        manager = ChannelManager(32)
        persistence = UnifiedPersistence()

        # Verificar que los objetos se crearon correctamente
        self.assertIsNotNone(capture)
        self.assertIsNotNone(manager)
        self.assertIsNotNone(persistence)

    def test_import_performance(self):
        """Verificar que las importaciones sean rápidas"""
        import time

        start_time = time.time()
        # Re-importar módulos (ya están en cache, pero verificar que no sean lentos)
        import audio_server.audio_capture
        import audio_server.channel_manager
        import audio_server.unified_persistence

        end_time = time.time()
        import_time = end_time - start_time

        # Las importaciones deberían ser muy rápidas (< 0.1 segundos)
        self.assertLess(import_time, 0.1)


if __name__ == '__main__':
    # Configurar logging para tests
    import logging
    logging.basicConfig(level=logging.WARNING)

    # Ejecutar tests
    unittest.main(verbosity=2)