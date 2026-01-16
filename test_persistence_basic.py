#!/usr/bin/env python3
"""
Test simple de persistencia
"""

import sys
import os
import logging
import tempfile
import shutil
import time
import unittest
from pathlib import Path

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from audio_server.unified_persistence import UnifiedPersistence, ClientConfiguration, ClientType

class TestPersistenceBasic(unittest.TestCase):
    """Pruebas básicas de persistencia"""

    def setUp(self):
        """Configurar entorno de test"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config_dir = self.temp_dir / "config"
        self.config_dir.mkdir()
        self.persistence = UnifiedPersistence(str(self.config_dir))

    def tearDown(self):
        """Limpiar después del test"""
        self.persistence.shutdown()
        shutil.rmtree(self.temp_dir)

    def test_create_and_save(self):
        """Test básico: Crear y guardar configuración"""
        logger.info("Test: Crear y guardar configuracion")

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

        success = self.persistence.save_or_update_config("test-uuid-123", config)
        self.assertTrue(success)

        saved_config = self.persistence.get_config("test-uuid-123")
        self.assertIsNotNone(saved_config)
        self.assertEqual(saved_config.device_uuid, "test-uuid-123")

    def test_integrity_validation(self):
        """Test: Validación de integridad"""
        logger.info("Test: Validacion de integridad")

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

        # Forzar guardado
        self.persistence._save_to_disk()

        # Recargar
        new_persistence = UnifiedPersistence(str(self.config_dir))
        loaded_config = new_persistence.get_config("test-uuid-456")

        self.assertIsNotNone(loaded_config)
        self.assertTrue(loaded_config.validate_integrity())

        new_persistence.shutdown()
        logger.info("OK: Integridad validada")

    def test_update_channels(self):
        """Test: Actualizar canales"""
        logger.info("Test: Actualizar canales")

        config = ClientConfiguration(
            device_uuid="test-uuid-789",
            client_type=ClientType.NATIVE,
            custom_name="Initial",
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

        success = self.persistence.update_channels(
            "test-uuid-789",
            channels=[0, 1, 2],
            gains={0: 1.5, 1: 0.5, 2: 2.0},
            master_gain=1.3
        )
        self.assertTrue(success)

        updated = self.persistence.get_config("test-uuid-789")
        self.assertEqual(updated.channels, [0, 1, 2])
        self.assertEqual(updated.gains[0], 1.5)
        self.assertEqual(updated.master_gain, 1.3)

        logger.info("OK: Canales actualizados")

    def test_backup_restore(self):
        """Test: Backup y restauración"""
        logger.info("Test: Backup y restauracion")

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
        self.persistence._save_to_disk()  # Forzar guardado antes de backup
        self.persistence._backup_current()

        # Verificar que backup existe
        backups = list(self.persistence.backup_dir.glob("client_configs_*.json"))
        self.assertGreater(len(backups), 0, "Debe crear backup")

        # Corromper archivo principal
        with open(self.persistence.main_config_file, 'w') as f:
            f.write("{invalid json")

        # Nueva instancia debe restaurar
        new_persistence = UnifiedPersistence(str(self.config_dir))
        restored = new_persistence.get_config("test-uuid-backup")
        self.assertIsNotNone(restored, "Debe restaurar desde backup")
        self.assertEqual(restored.custom_name, "Backup Test")

        new_persistence.shutdown()
        logger.info("OK: Backup y restauracion funcionan")

if __name__ == '__main__':
    unittest.main()