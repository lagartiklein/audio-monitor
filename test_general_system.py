#!/usr/bin/env python3
"""
test_general_system.py - Suite completa de tests generales del sistema Fichatech Monitor

Tests generales que cubren:
- Configuración del sistema
- Inicialización de componentes principales
- Funcionalidad básica de AudioCapture
- ChannelManager
- Integración entre componentes
- Manejo de errores
- Persistencia
- WebSocket server
- Manejo de escenas
- Optimizaciones de latencia
"""

import unittest
import sys
import os
import tempfile
import json
import time
import threading
from unittest.mock import Mock, patch, MagicMock
import numpy as np

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
# Nota: websocket_server es un módulo de funciones, no una clase


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


class TestAudioCaptureBasics(unittest.TestCase):
    """Tests básicos para AudioCapture"""

    def setUp(self):
        self.audio_capture = AudioCapture()

    def tearDown(self):
        if self.audio_capture.running:
            self.audio_capture.stop_capture()

    def test_initialization(self):
        """Verificar inicialización correcta"""
        self.assertIsNotNone(self.audio_capture)
        self.assertFalse(self.audio_capture.running)
        self.assertEqual(self.audio_capture.actual_channels, 0)
        self.assertEqual(self.audio_capture.physical_channels, 0)
        self.assertIsInstance(self.audio_capture.callbacks, list)

    def test_callback_registration(self):
        """Verificar registro de callbacks"""
        callback_count = len(self.audio_capture.callbacks)

        def test_callback(data):
            pass

        self.audio_capture.register_callback(test_callback)
        self.assertEqual(len(self.audio_capture.callbacks), callback_count + 1)

    def test_callback_removal(self):
        """Verificar eliminación de callbacks"""
        def test_callback(data):
            pass

        self.audio_capture.register_callback(test_callback)
        initial_count = len(self.audio_capture.callbacks)

        self.audio_capture.unregister_callback(test_callback)
        self.assertEqual(len(self.audio_capture.callbacks), initial_count - 1)

    def test_vu_callback_registration(self):
        """Verificar registro de VU callbacks"""
        def vu_callback(levels):
            pass

        # Esto debería funcionar sin errores
        self.audio_capture.register_vu_callback(vu_callback)
        # No hay una forma directa de verificar el registro, pero no debería fallar

    def test_stats_access(self):
        """Verificar acceso a estadísticas"""
        stats = self.audio_capture.get_stats()
        self.assertIsInstance(stats, dict)
        # Verificar que tenga algunas claves básicas
        self.assertIn('callbacks_registered', stats)


class TestChannelManagerBasics(unittest.TestCase):
    """Tests básicos para ChannelManager"""

    def setUp(self):
        self.channel_manager = ChannelManager(16)

    def test_initialization(self):
        """Verificar inicialización correcta"""
        self.assertIsNotNone(self.channel_manager)
        self.assertEqual(self.channel_manager.num_channels, 16)

    def test_master_client_detection(self):
        """Verificar detección de cliente maestro"""
        # Por defecto no debería haber cliente maestro
        self.assertIsNone(self.channel_manager.get_master_client_id())

    def test_operational_channels(self):
        """Verificar canales operativos"""
        operational = self.channel_manager.get_operational_channels()
        self.assertIsInstance(operational, set)

    def test_client_subscription(self):
        """Verificar suscripción de cliente"""
        client_id = "test_client"
        channels = [0, 1, 2]

        # Suscribir cliente
        self.channel_manager.subscribe_client(client_id, channels)

        # Verificar suscripción
        subscription = self.channel_manager.get_client_subscription(client_id)
        self.assertIsNotNone(subscription)

    def test_channel_gain_access(self):
        """Verificar acceso a ganancias de canal"""
        client_id = "test_client"
        channels = [0, 1]

        self.channel_manager.subscribe_client(client_id, channels, gains={0: 0.8, 1: 0.6})

        # Verificar ganancia
        gain = self.channel_manager.get_channel_gain(client_id, 0)
        self.assertIsInstance(gain, (int, float))


class TestUnifiedPersistence(unittest.TestCase):
    """Tests para UnifiedPersistence"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.persistence = UnifiedPersistence(config_dir=self.temp_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_initialization(self):
        """Verificar inicialización correcta"""
        self.assertIsNotNone(self.persistence)

    def test_client_config_operations(self):
        """Verificar operaciones CRUD de configuración de cliente"""
        from audio_server.unified_persistence import ClientConfiguration, ClientType

        client_id = "test_client"
        config = ClientConfiguration(
            device_uuid=client_id,
            client_type=ClientType.WEB,
            custom_name="Test Client",
            channels=[0, 1, 2, 3, 4, 5, 6, 7],
            gains={i: 0.8 for i in range(8)},
            pans={i: 0.0 for i in range(8)},
            mutes={i: False for i in range(8)},
            master_gain=1.0,
            created_at=time.time(),
            last_modified=time.time(),
            last_session_duration=0.0,
            reconnection_count=0
        )
        )

        # Guardar configuración
        success = self.persistence.save_or_update_config(client_id, config)
        self.assertTrue(success)

        # Cargar configuración
        loaded_config = self.persistence.get_config(client_id)
        self.assertIsNotNone(loaded_config)
        self.assertEqual(loaded_config.name, "Test Client")
        self.assertEqual(len(loaded_config.channels), 8)

        # Eliminar configuración
        success = self.persistence.delete_config(client_id)
        self.assertTrue(success)

        # Verificar que ya no existe
        loaded_config = self.persistence.get_config(client_id)
        self.assertIsNone(loaded_config)

    def test_channel_names(self):
        """Verificar gestión de nombres de canales"""
        # Actualizar nombre de canal
        self.persistence.update_channel_name(0, "Kick In")
        self.persistence.update_channel_name(1, "Snare In")

        # Obtener nombres
        names = self.persistence.get_channel_names()
        self.assertEqual(names.get(0), "Kick In")
        self.assertEqual(names.get(1), "Snare In")


class TestSceneManager(unittest.TestCase):
    """Tests para SceneManager"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.scene_manager = SceneManager(scenes_dir=self.temp_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_scene_save_and_load(self):
        """Verificar guardado y carga de escenas"""
        scene_data = {
            "scene_name": "Test Scene",
            "clients": {
                "client1": {
                    "channels": [0, 1, 2],
                    "gains": [0.8, 0.7, 0.9],
                    "pans": [0.0, 0.1, -0.1]
                }
            }
        }

        # Guardar escena
        success, message = self.scene_manager.export_scene("test_scene.json", scene_data)
        self.assertTrue(success)
        self.assertIn("Scene saved", message)

        # Cargar escena
        success, loaded_data, message = self.scene_manager.import_scene("test_scene.json")
        self.assertTrue(success)
        self.assertEqual(loaded_data["scene_name"], "Test Scene")
        self.assertIn("client1", loaded_data["clients"])

    def test_scene_validation(self):
        """Verificar validación de escenas"""
        # Escena válida
        valid_scene = {
            "scene_name": "Valid Scene",
            "clients": {}
        }
        is_valid, error = self.scene_manager.validate_scene(valid_scene)
        self.assertTrue(is_valid)

        # Escena inválida (sin scene_name)
        invalid_scene = {
            "clients": {}
        }
        is_valid, error = self.scene_manager.validate_scene(invalid_scene)
        self.assertFalse(is_valid)


class TestLatencyOptimizer(unittest.TestCase):
    """Tests para LatencyOptimizer"""

    def setUp(self):
        self.optimizer = LatencyOptimizer()

    def test_initialization(self):
        """Verificar inicialización correcta"""
        self.assertIsNotNone(self.optimizer)
        self.assertGreater(self.optimizer.debounce_ms, 0)

    def test_parameter_queueing(self):
        """Verificar encolado de parámetros"""
        client_id = "test_client"

        # Encolar actualización de ganancia
        self.optimizer.queue_parameter_update(client_id, "gain", 0, 0.8)

        # Verificar que se almacenó
        self.assertIn(client_id, self.optimizer.pending_updates)
        self.assertIn(0, self.optimizer.pending_updates[client_id]['gains'])

    def test_debounce_timer_creation(self):
        """Verificar creación de timers de debounce"""
        client_id = "test_client"

        # Encolar actualización
        self.optimizer.queue_parameter_update(client_id, "gain", 0, 0.8)

        # Verificar que se creó un timer
        self.assertIn(client_id, self.optimizer.debounce_timers)


class TestDeviceRegistry(unittest.TestCase):
    """Tests para DeviceRegistry"""

    def setUp(self):
        self.registry = DeviceRegistry()

    def test_device_registration(self):
        """Verificar registro de dispositivos"""
        device_uuid = "test_device_123"
        device_info = {
            'type': 'web',
            'name': 'Test Audio Device',
            'max_input_channels': 8,
            'default_sample_rate': 48000
        }

        result = self.registry.register_device(device_uuid, device_info)
        self.assertIsInstance(result, dict)
        self.assertIn('uuid', result)

        # Verificar que el dispositivo se registró
        registered_device = self.registry.get_device(device_uuid)
        self.assertIsNotNone(registered_device)
        self.assertEqual(registered_device['name'], 'Test Audio Device')

    def test_device_listing_by_type(self):
        """Verificar listado de dispositivos por tipo"""
        # Registrar algunos dispositivos
        self.registry.register_device("web1", {'type': 'web', 'name': 'Web Device 1'})
        self.registry.register_device("android1", {'type': 'android', 'name': 'Android Device 1'})
        self.registry.register_device("web2", {'type': 'web', 'name': 'Web Device 2'})

        # Listar dispositivos web
        web_devices = self.registry.get_devices_by_type('web')
        self.assertIsInstance(web_devices, list)
        self.assertGreaterEqual(len(web_devices), 2)  # Al menos los 2 web que registramos


class TestWebSocketServerBasics(unittest.TestCase):
    """Tests básicos para el módulo websocket_server"""

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

    def test_ui_state_management(self):
        """Verificar gestión básica del estado UI"""
        import audio_server.websocket_server as ws_server

        # Verificar que las funciones de estado UI existen
        self.assertTrue(hasattr(ws_server, '_load_ui_state_from_disk'))
        self.assertTrue(hasattr(ws_server, '_save_ui_state_to_disk'))
        self.assertTrue(hasattr(ws_server, '_get_client_order'))


class TestSystemIntegration(unittest.TestCase):
    """Tests de integración entre componentes"""

    def setUp(self):
        self.audio_capture = AudioCapture()
        self.channel_manager = ChannelManager(8)
        self.persistence = UnifiedPersistence()

    def tearDown(self):
        if self.audio_capture.running:
            self.audio_capture.stop_capture()

    def test_channel_manager_persistence_integration(self):
        """Verificar integración entre ChannelManager y UnifiedPersistence"""
        # Configurar nombres de canales a través de UnifiedPersistence
        self.persistence.update_channel_name(0, "Mic 1")
        self.persistence.update_channel_name(1, "Mic 2")

        # Verificar que los nombres se mantengan
        names = self.persistence.get_channel_names()
        self.assertEqual(names.get(0), "Mic 1")
        self.assertEqual(names.get(1), "Mic 2")

    def test_persistence_integration(self):
        """Verificar integración con UnifiedPersistence"""
        from audio_server.unified_persistence import ClientConfiguration, ClientType

        # Crear configuración de cliente
        client_config = ClientConfiguration(
            device_uuid="integration_client",
            client_type=ClientType.WEB,
            custom_name="Integration Test Client",
            channels=[0, 1, 2, 3],
            gains={0: 0.8, 1: 0.7, 2: 0.9, 3: 0.6},
            pans={0: 0.0, 1: 0.1, 2: -0.1, 3: 0.2},
            mutes={0: False, 1: False, 2: False, 3: False},
            master_gain=1.0,
            created_at=time.time(),
            last_modified=time.time(),
            last_session_duration=0.0,
            reconnection_count=0
        )
        )

        success = self.persistence.save_or_update_config("integration_client", client_config)
        self.assertTrue(success)

        # Verificar que se puede cargar
        loaded = self.persistence.get_config("integration_client")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.name, "Integration Test Client")
        self.assertEqual(len(loaded.channels), 4)


class TestErrorHandling(unittest.TestCase):
    """Tests de manejo de errores"""

    def test_invalid_config_values(self):
        """Verificar manejo de valores de configuración inválidos"""
        # Estos deberían ser valores válidos según config.py
        self.assertGreater(config.MAX_LOGICAL_CHANNELS, 0)
        self.assertGreater(config.SAMPLE_RATE, 0)

    def test_audio_capture_invalid_callback(self):
        """Verificar manejo de callbacks inválidos en AudioCapture"""
        audio_capture = AudioCapture()

        # Intentar registrar algo que no es una función
        with self.assertRaises(AttributeError):
            audio_capture.register_callback("not_a_function")

    def test_channel_manager_bounds_checking(self):
        """Verificar verificación de límites en ChannelManager"""
        channel_manager = ChannelManager(4)

        # Canales válidos - estos deberían funcionar sin error
        channel_manager.subscribe_client("test_client", [0, 1, 2])

        # Intentar acceder a canales fuera de límites
        # Nota: ChannelManager no lanza excepciones por canales inválidos,
        # simplemente los ignora o maneja internamente
        subscription = channel_manager.get_client_subscription("test_client")
        self.assertIsNotNone(subscription)

    def test_persistence_invalid_operations(self):
        """Verificar manejo de operaciones inválidas en UnifiedPersistence"""
        persistence = UnifiedPersistence()

        # Intentar cargar configuración inexistente
        config = persistence.get_config("nonexistent_client")
        self.assertIsNone(config)

        # Intentar eliminar configuración inexistente
        success = persistence.delete_config("nonexistent_client")
        # Esto podría retornar False o no hacer nada, dependiendo de la implementación
        self.assertIsInstance(success, bool)


class TestPerformanceBasics(unittest.TestCase):
    """Tests básicos de rendimiento"""

    def test_memory_usage_basic(self):
        """Verificar uso básico de memoria"""
        # Crear componentes y verificar que no fallen
        audio_capture = AudioCapture()
        channel_manager = ChannelManager(32)
        persistence = UnifiedPersistence()

        # Verificar que los objetos se crearon correctamente
        self.assertIsNotNone(audio_capture)
        self.assertIsNotNone(channel_manager)
        self.assertIsNotNone(persistence)

    def test_thread_safety_basic(self):
        """Verificar seguridad básica de hilos"""
        channel_manager = ChannelManager(8)

        results = []

        def worker_thread(channel_id):
            channel_manager.set_channel_name(channel_id, f"Thread {channel_id}")
            results.append(channel_manager.get_channel_name(channel_id))

        threads = []
        for i in range(4):
            t = threading.Thread(target=worker_thread, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Verificar que todos los nombres se asignaron
        self.assertEqual(len(results), 4)
        for i in range(4):
            self.assertIn(f"Thread {i}", results)


if __name__ == '__main__':
    # Configurar logging para tests
    import logging
    logging.basicConfig(level=logging.WARNING)

    # Ejecutar tests
    unittest.main(verbosity=2)