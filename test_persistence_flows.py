#!/usr/bin/env python3
"""
Test de flujos de persistencia y datos de clientes
Pruebas integrales del sistema UnifiedPersistence
"""

import sys
import os
import logging
import json
import tempfile
import shutil
import time
import unittest
from pathlib import Path

# Configurar logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from audio_server.unified_persistence import UnifiedPersistence, ClientConfiguration, ClientType, init_unified_persistence

class TestPersistenceFlows(unittest.TestCase):
    """Pruebas de flujos de persistencia"""

    def setUp(self):
        """Configurar entorno de test"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config_dir = self.temp_dir / "config"
        self.config_dir.mkdir()

        # Inicializar persistencia en directorio temporal
        self.persistence = UnifiedPersistence(str(self.config_dir))

    def tearDown(self):
        """Limpiar después del test"""
        self.persistence.shutdown()
        shutil.rmtree(self.temp_dir)

    def test_create_and_save_client_config(self):
        """Test: Crear y guardar configuración de cliente"""
        logger.info("Test: Crear y guardar configuracion de cliente")

        # Crear configuración de prueba
        config = ClientConfiguration(
            device_uuid="test-uuid-123",
            client_type=ClientType.NATIVE,
            custom_name="Test Client",
            channels=[0, 1],
            gains={0: 1.0, 1: 0.8},
            pans={0: 0.0, 1: -0.5},
            mutes={0: False, 1: True},
            master_gain=1.2,
            created_at=time.time(),
            last_modified=time.time(),
            last_session_duration=0.0,
            reconnection_count=0
        )

        # Guardar configuración
        success = self.persistence.save_or_update_config("test-uuid-123", config)
        self.assertTrue(success, "Debe guardar la configuración exitosamente")

        # Verificar que se guardó
        saved_config = self.persistence.get_config("test-uuid-123")
        self.assertIsNotNone(saved_config, "Debe poder recuperar la configuración")
        self.assertEqual(saved_config.device_uuid, "test-uuid-123")
        self.assertEqual(saved_config.client_type, ClientType.NATIVE)
        self.assertEqual(saved_config.custom_name, "Test Client")
        self.assertEqual(saved_config.channels, [0, 1])
        self.assertEqual(saved_config.gains[0], 1.0)
        self.assertEqual(saved_config.master_gain, 1.2)

        logger.info("Configuracion creada y guardada correctamente")

    def test_load_and_validate_integrity(self):
        """Test: Cargar y validar integridad de datos"""
        logger.info("Test: Cargar y validar integridad")

        # Crear y guardar configuración
        config = ClientConfiguration(
            device_uuid="test-uuid-456",
            client_type=ClientType.WEB,
            custom_name=None,
            channels=[0],
            gains={0: 2.0},
            pans={0: 0.0},
            mutes={0: False},
            master_gain=1.0,
            created_at=time.time(),
            last_modified=time.time(),
            last_session_duration=0.0,
            reconnection_count=0
        )

        self.persistence.save_or_update_config("test-uuid-456", config)

        # Simular recarga desde disco (reinicializar persistencia)
        self.persistence._save_to_disk()
        new_persistence = UnifiedPersistence(str(self.config_dir))

        # Verificar que se cargó correctamente
        loaded_config = new_persistence.get_config("test-uuid-456")
        self.assertIsNotNone(loaded_config, "Debe cargar la configuración desde disco")
        self.assertTrue(loaded_config.validate_integrity(), "Debe validar la integridad")

        new_persistence.shutdown()
        logger.info("Integridad validada correctamente")

    def test_update_client_config(self):
        """Test: Actualizar configuración de cliente"""
        logger.info("Test: Actualizar configuracion de cliente")

        # Crear configuración inicial
        config = ClientConfiguration(
            device_uuid="test-uuid-789",
            client_type=ClientType.NATIVE,
            custom_name="Initial Name",
            channels=[0],
            gains={0: 1.0},
            pans={0: 0.0},
            mutes={0: False},
            master_gain=1.0,
            created_at=time.time(),
            last_modified=time.time(),
            last_session_duration=0.0,
            reconnection_count=0
        )

        self.persistence.save_or_update_config("test-uuid-789", config)

        # Actualizar canales
        success = self.persistence.update_channels(
            "test-uuid-789",
            channels=[0, 1, 2],
            gains={0: 1.5, 1: 0.5, 2: 2.0},
            master_gain=1.3
        )
        self.assertTrue(success, "Debe actualizar los canales")

        # Verificar actualización
        updated_config = self.persistence.get_config("test-uuid-789")
        self.assertEqual(updated_config.channels, [0, 1, 2])
        self.assertEqual(updated_config.gains[0], 1.5)
        self.assertEqual(updated_config.master_gain, 1.3)
        self.assertEqual(updated_config.reconnection_count, 1, "Debe incrementar reconexiones")

        logger.info("✅ Configuración actualizada correctamente")

    def test_delete_client_config(self):
        """Test: Eliminar configuración de cliente"""
        logger.info("🧪 Test: Eliminar configuración de cliente")

        # Crear configuración
        config = ClientConfiguration(
            device_uuid="test-uuid-del",
            client_type=ClientType.WEB,
            custom_name="To Delete",
            channels=[0],
            gains={0: 1.0},
            pans={0: 0.0},
            mutes={0: False},
            master_gain=1.0,
            created_at=time.time(),
            last_modified=time.time(),
            last_session_duration=0.0,
            reconnection_count=0
        )

        self.persistence.save_or_update_config("test-uuid-del", config)

        # Verificar que existe
        self.assertIsNotNone(self.persistence.get_config("test-uuid-del"))

        # Eliminar
        success = self.persistence.delete_config("test-uuid-del")
        self.assertTrue(success, "Debe eliminar la configuración")

        # Verificar que no existe
        self.assertIsNone(self.persistence.get_config("test-uuid-del"))

        logger.info("✅ Configuración eliminada correctamente")

    def test_backup_and_restore(self):
        """Test: Backup y restauración"""
        logger.info("🧪 Test: Backup y restauración")

        # Crear configuración
        config = ClientConfiguration(
            device_uuid="test-uuid-backup",
            client_type=ClientType.NATIVE,
            custom_name="Backup Test",
            channels=[0],
            gains={0: 1.0},
            pans={0: 0.0},
            mutes={0: False},
            master_gain=1.0,
            created_at=time.time(),
            last_modified=time.time(),
            last_session_duration=0.0,
            reconnection_count=0
        )

        self.persistence.save_or_update_config("test-uuid-backup", config)

        # Forzar backup
        self.persistence._backup_current()

        # Verificar que existe backup
        backups = list(self.persistence.backup_dir.glob("client_configs_*.json"))
        self.assertGreater(len(backups), 0, "Debe crear al menos un backup")

        # Corromper archivo principal
        main_file = self.persistence.main_config_file
        with open(main_file, 'w') as f:
            f.write("{invalid json")

        # Crear nueva instancia (debe restaurar desde backup)
        new_persistence = UnifiedPersistence(str(self.config_dir))

        # Verificar que se restauró
        restored_config = new_persistence.get_config("test-uuid-backup")
        self.assertIsNotNone(restored_config, "Debe restaurar desde backup")
        self.assertEqual(restored_config.custom_name, "Backup Test")

        new_persistence.shutdown()
        logger.info("✅ Backup y restauración funcionan correctamente")

    def test_channel_names_persistence(self):
        """Test: Persistencia de nombres de canales"""
        logger.info("🧪 Test: Persistencia de nombres de canales")

        # Actualizar nombres de canales
        self.persistence.update_channel_name(0, "Voz Principal")
        self.persistence.update_channel_name(1, "Guitarra")
        self.persistence.update_channel_name(2, "Bajo")

        # Verificar
        names = self.persistence.get_channel_names()
        self.assertEqual(names[0], "Voz Principal")
        self.assertEqual(names[1], "Guitarra")
        self.assertEqual(names[2], "Bajo")

        # Recargar y verificar persistencia
        self.persistence._save_channel_names()
        new_persistence = UnifiedPersistence(str(self.config_dir))

        new_names = new_persistence.get_channel_names()
        self.assertEqual(new_names[0], "Voz Principal")
        self.assertEqual(new_names[1], "Guitarra")

        new_persistence.shutdown()
        logger.info("✅ Nombres de canales persistidos correctamente")

    def test_stats_and_multiple_clients(self):
        """Test: Estadísticas y múltiples clientes"""
        logger.info("🧪 Test: Estadísticas y múltiples clientes")

        # Crear múltiples configuraciones
        configs = [
            ("uuid1", ClientType.NATIVE),
            ("uuid2", ClientType.WEB),
            ("uuid3", ClientType.NATIVE),
        ]

        for uuid, client_type in configs:
            config = ClientConfiguration(
                device_uuid=uuid,
                client_type=client_type,
                custom_name=f"Client {uuid}",
                channels=[0],
                gains={0: 1.0},
                pans={0: 0.0},
                mutes={0: False},
                master_gain=1.0,
                created_at=time.time(),
                last_modified=time.time(),
                last_session_duration=0.0,
                reconnection_count=0
            )
            self.persistence.save_or_update_config(uuid, config)

        # Verificar estadísticas
        stats = self.persistence.get_stats()
        self.assertEqual(stats['total_configs'], 3)
        self.assertEqual(stats['by_type']['native'], 2)
        self.assertEqual(stats['by_type']['web'], 1)

        # Verificar filtrado por tipo
        native_configs = self.persistence.get_all_configs(ClientType.NATIVE)
        self.assertEqual(len(native_configs), 2)

        web_configs = self.persistence.get_all_configs(ClientType.WEB)
        self.assertEqual(len(web_configs), 1)

        logger.info("OK: Estadisticas y filtrado funcionan correctamente")

if __name__ == '__main__':
    unittest.main()
