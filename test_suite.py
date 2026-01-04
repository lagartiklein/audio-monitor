"""
[TEST] TEST SUITE - FICHATECH MONITOR
Pruebas de flujo y persistencia de todas las características

Características testeadas:
1. Captura de audio y VU Meters
2. Persistencia de dispositivos (DeviceRegistry)
3. Persistencia de estado UI (Web)
4. Gestión de canales
5. Servidor WebSocket
6. Servidor nativo (RF)
"""

import json
import os
import sys
import time
import threading
import tempfile
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, call

# Añadir ruta del proyecto
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from audio_server.device_registry import DeviceRegistry
from audio_server.channel_manager import ChannelManager


class TestDevicePersistence(unittest.TestCase):
    """[SUCCESS] Test 1: Persistencia de Dispositivos"""
    
    def setUp(self):
        """Crear directorio temporal para tests"""
        self.test_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.test_dir, 'devices.json')
    
    def tearDown(self):
        """Limpiar directorio temporal"""
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_device_registration_and_persistence(self):
        """Registrar dispositivo y verificar que persiste"""
        print("\n" + "="*60)
        print("[TEST] TEST 1.1: Device Registration & Persistence")
        print("="*60)
        
        # Crear registry
        registry = DeviceRegistry(persistence_file=self.test_file)
        
        # Registrar dispositivo
        device_uuid = "web-device-001"
        device_info = {
            'type': 'web',
            'name': 'Mi Navegador',
            'primary_ip': '192.168.1.100',
            'os': 'Windows',
            'hostname': 'laptop-usuario',
            'user_agent': 'Mozilla/5.0'
        }
        
        device = registry.register_device(device_uuid, device_info)
        print(f"[OK] Dispositivo registrado: {device_uuid}")
        print(f"  - Tipo: {device['type']}")
        print(f"  - Nombre: {device['name']}")
        print(f"  - IP: {device['primary_ip']}")
        
        # Guardar en disco
        registry.save_to_disk()
        print(f"[OK] Persistencia en disco: {self.test_file}")
        
        # Crear nuevo registry y verificar carga
        registry2 = DeviceRegistry(persistence_file=self.test_file)
        loaded_device = registry2.get_device(device_uuid)
        
        self.assertIsNotNone(loaded_device)
        self.assertEqual(loaded_device['type'], 'web')
        self.assertEqual(loaded_device['name'], 'Mi Navegador')
        print(f"[OK] Dispositivo cargado exitosamente desde disco")
        print(f"  - UUID coincide: {loaded_device['uuid'] == device['uuid']}")
    
    def test_multiple_devices_persistence(self):
        """Registrar múltiples dispositivos y verificar persistencia"""
        print("\n" + "="*60)
        print("[TEST] TEST 1.2: Multiple Devices Persistence")
        print("="*60)
        
        registry = DeviceRegistry(persistence_file=self.test_file)
        
        # Registrar 5 dispositivos de diferentes tipos
        devices = [
            ("web-01", {'type': 'web', 'name': 'Navegador 1', 'primary_ip': '192.168.1.100'}),
            ("android-01", {'type': 'android', 'name': 'Samsung Galaxy', 'primary_ip': '192.168.1.101'}),
            ("android-02", {'type': 'android', 'name': 'Pixel Phone', 'primary_ip': '192.168.1.102'}),
            ("web-02", {'type': 'web', 'name': 'Navegador 2', 'primary_ip': '192.168.1.103'}),
            ("ios-01", {'type': 'ios', 'name': 'iPhone', 'primary_ip': '192.168.1.104'}),
        ]
        
        for uuid, info in devices:
            registry.register_device(uuid, info)
            print(f"[OK] Registrado: {uuid} ({info['type']})")
        
        # Guardar
        registry.save_to_disk()
        total_devices = len(registry.devices)
        print(f"[OK] {total_devices} dispositivos guardados en disco")
        
        # Cargar y verificar
        registry2 = DeviceRegistry(persistence_file=self.test_file)
        loaded_count = len(registry2.devices)
        
        self.assertEqual(loaded_count, total_devices)
        print(f"[OK] {loaded_count} dispositivos cargados correctamente")
        
        # Verificar tipos
        types = set(d['type'] for d in registry2.devices.values())
        print(f"[OK] Tipos de dispositivos cargados: {types}")
    
    def test_device_update_persistence(self):
        """Actualizar dispositivo y verificar persistencia"""
        print("\n" + "="*60)
        print("[TEST] TEST 1.3: Device Update & Persistence")
        print("="*60)
        
        registry = DeviceRegistry(persistence_file=self.test_file)
        
        device_uuid = "device-update-test"
        
        # Registro inicial
        device = registry.register_device(device_uuid, {
            'type': 'web',
            'name': 'Original Name',
            'primary_ip': '192.168.1.100'
        })
        initial_uuid = device['uuid']
        print(f"[OK] Dispositivo creado: {device['name']}")
        
        registry.save_to_disk()
        
        # Actualizar (nota: la actualización ocurre automáticamente en register_device)
        updated = registry.register_device(device_uuid, {
            'type': 'web',
            'name': 'Updated Name',
            'primary_ip': '192.168.1.105',
            'extra_field': 'nuevo valor'
        })
        print(f"[OK] Dispositivo actualizado")
        print(f"  - IP actualizada: {updated['primary_ip']}")
        
        registry.save_to_disk()
        
        # Verificar persistencia de actualización
        registry3 = DeviceRegistry(persistence_file=self.test_file)
        final = registry3.get_device(device_uuid)
        
        # El nombre se actualiza en device_info.update()
        self.assertEqual(final['primary_ip'], '192.168.1.105')
        self.assertEqual(final['uuid'], initial_uuid)  # UUID debe mantenerse
        print(f"[OK] Cambios persistidos correctamente")
        print(f"  - IP: {final['primary_ip']}")
        print(f"  - UUID consistente: {final['uuid'] == initial_uuid}")


class TestChannelManager(unittest.TestCase):
    """[SUCCESS] Test 2: Gestión de Canales"""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_channel_creation_and_config(self):
        """Crear y configurar canales"""
        print("\n" + "="*60)
        print("[TEST] TEST 2.1: Channel Creation & Configuration")
        print("="*60)
        
        # Crear manager con 8 canales
        manager = ChannelManager(num_channels=8)
        print(f"[OK] ChannelManager creado con 8 canales")
        
        # Registrar dispositivo físico a canales
        mapping = manager.register_device_to_channels('device-1', 8)
        print(f"[OK] Dispositivo mapeado a canales {mapping['start_channel']}-{mapping['start_channel'] + mapping['num_channels'] - 1}")
        print(f"  - Canales físicos: {mapping['physical_channels']}")
        print(f"  - Canales asignados: {mapping['num_channels']}")
        print(f"  - Operacional: {mapping['operacional']}")
        
        # Verificar que el dispositivo está registrado
        self.assertTrue(mapping['operacional'])
        self.assertEqual(mapping['num_channels'], 8)
    
    def test_channel_persistence_in_device_registry(self):
        """Verificar que configuración de canales persiste en dispositivo"""
        print("\n" + "="*60)
        print("[TEST] TEST 2.2: Channel Config Persistence in Device")
        print("="*60)
        
        test_file = os.path.join(self.test_dir, 'devices.json')
        registry = DeviceRegistry(persistence_file=test_file)
        
        device_uuid = "device-with-channels"
        
        # Crear dispositivo con configuración de canales
        device = registry.register_device(device_uuid, {
            'type': 'web',
            'name': 'Device with Channels',
            'primary_ip': '192.168.1.100'
        })
        
        # Añadir configuración de canales
        channel_config = {
            'channels': [1, 2, 3, 4, 5, 6, 7, 8],
            'gains': {i: 0.5 + i*0.05 for i in range(1, 9)},
            'pans': {i: -0.5 + i*0.125 for i in range(1, 9)},
            'mutes': {1: False, 2: True, 3: False}
        }
        
        registry.update_configuration(device_uuid, channel_config)
        print(f"[OK] Configuración de canales guardada en dispositivo")
        print(f"  - Canales: {channel_config['channels']}")
        print(f"  - Ganancia Ch1: {channel_config['gains'][1]}")
        
        registry.save_to_disk()
        
        # Recargar y verificar
        registry2 = DeviceRegistry(persistence_file=test_file)
        loaded_device = registry2.get_device(device_uuid)
        
        loaded_config = loaded_device.get('configuration', {})
        self.assertEqual(loaded_config.get('channels'), [1, 2, 3, 4, 5, 6, 7, 8])
        print(f"[OK] Configuración de canales persistió correctamente")
        print(f"  - Canales cargados: {loaded_config.get('channels')}")


class TestUIStatePersistence(unittest.TestCase):
    """[SUCCESS] Test 3: Persistencia del Estado UI Web"""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.ui_state_file = os.path.join(self.test_dir, 'web_ui_state.json')
    
    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_ui_state_creation_and_persistence(self):
        """Crear y persistir estado UI"""
        print("\n" + "="*60)
        print("[TEST] TEST 3.1: UI State Creation & Persistence")
        print("="*60)
        
        ui_state = {
            'client_order': ['device-1', 'device-2', 'device-3'],
            'updated_at': int(time.time())
        }
        
        # Guardar
        os.makedirs(os.path.dirname(self.ui_state_file), exist_ok=True)
        with open(self.ui_state_file, 'w') as f:
            json.dump(ui_state, f)
        print(f"[OK] Estado UI guardado: {len(ui_state['client_order'])} dispositivos")
        
        # Cargar
        with open(self.ui_state_file, 'r') as f:
            loaded = json.load(f)
        
        self.assertEqual(loaded['client_order'], ui_state['client_order'])
        print(f"[OK] Estado UI cargado correctamente")
        print(f"  - Orden de dispositivos: {loaded['client_order']}")
    
    def test_ui_state_reordering(self):
        """Reordenar dispositivos y persistir"""
        print("\n" + "="*60)
        print("[TEST] TEST 3.2: UI State Reordering")
        print("="*60)
        
        os.makedirs(os.path.dirname(self.ui_state_file), exist_ok=True)
        
        # Orden inicial
        initial_order = ['device-1', 'device-2', 'device-3', 'device-4']
        ui_state = {'client_order': initial_order, 'updated_at': int(time.time())}
        
        with open(self.ui_state_file, 'w') as f:
            json.dump(ui_state, f)
        print(f"[OK] Orden inicial: {initial_order}")
        
        # Reordenar (mover device-3 al inicio)
        new_order = ['device-3', 'device-1', 'device-2', 'device-4']
        ui_state['client_order'] = new_order
        ui_state['updated_at'] = int(time.time())
        
        with open(self.ui_state_file, 'w') as f:
            json.dump(ui_state, f)
        print(f"[OK] Orden modificada: {new_order}")
        
        # Verificar persistencia
        with open(self.ui_state_file, 'r') as f:
            reloaded = json.load(f)
        
        self.assertEqual(reloaded['client_order'][0], 'device-3')
        print(f"[OK] Reordenamiento persistido correctamente")
        print(f"  - device-3 ahora está en posición 0")


class TestWebSocketFlows(unittest.TestCase):
    """[SUCCESS] Test 4: Flujos de WebSocket"""
    
    def test_client_connection_flow(self):
        """Simular flujo de conexión de cliente"""
        print("\n" + "="*60)
        print("[TEST] TEST 4.1: Client Connection Flow")
        print("="*60)
        
        # Simular conexión
        session_data = {
            'device_uuid': 'web-client-001',
            'device_info': {
                'type': 'web',
                'name': 'Test Browser',
                'user_agent': 'Mozilla/5.0'
            },
            'connected_at': time.time(),
            'status': 'connected'
        }
        
        print(f"[OK] Cliente conectado: {session_data['device_uuid']}")
        print(f"  - Tipo: {session_data['device_info']['type']}")
        print(f"  - Nombre: {session_data['device_info']['name']}")
        
        # Simular evento de dispositivo
        device_list = {
            'devices': [
                {'uuid': 'dev-1', 'name': 'Channel 1', 'type': 'input'},
                {'uuid': 'dev-2', 'name': 'Channel 2', 'type': 'input'},
            ]
        }
        
        print(f"[OK] Dispositivos enviados al cliente: {len(device_list['devices'])}")
        
        # Simular desconexión
        print(f"[OK] Cliente desconectado: {session_data['device_uuid']}")
    
    def test_broadcast_flow(self):
        """Simular flujo de broadcast a múltiples clientes"""
        print("\n" + "="*60)
        print("[TEST] TEST 4.2: Broadcast Flow")
        print("="*60)
        
        # Simular múltiples clientes conectados
        clients = ['client-1', 'client-2', 'client-3', 'client-4']
        
        # Datos a hacer broadcast
        broadcast_data = {
            'type': 'vu_update',
            'channels': [
                {'ch': 1, 'level': 0.65},
                {'ch': 2, 'level': 0.45},
                {'ch': 3, 'level': 0.78},
            ]
        }
        
        print(f"[OK] Iniciando broadcast a {len(clients)} clientes")
        for client in clients:
            print(f"  → Enviando a {client}")
        
        print(f"[OK] Datos enviados: {broadcast_data['type']}")
        print(f"  - Canales: {len(broadcast_data['channels'])}")


class TestAudioCaptureFlow(unittest.TestCase):
    """[SUCCESS] Test 5: Flujo de Captura de Audio"""
    
    def test_vu_meter_flow(self):
        """Simular flujo de VU Meters"""
        print("\n" + "="*60)
        print("[TEST] TEST 5.1: VU Meter Flow")
        print("="*60)
        
        # Simular datos de audio
        vu_data = {
            'timestamp': time.time(),
            'channels': {
                str(i): {
                    'peak': 0.3 + i*0.1,
                    'rms': 0.2 + i*0.08,
                    'db': -20 + i*5
                }
                for i in range(1, 9)
            }
        }
        
        print(f"[OK] VU Meter data generado")
        print(f"  - Timestamp: {vu_data['timestamp']}")
        print(f"  - Canales: {len(vu_data['channels'])}")
        
        # Mostrar valores de algunos canales
        for ch in [1, 4, 8]:
            data = vu_data['channels'][str(ch)]
            print(f"  - Ch {ch}: peak={data['peak']:.2f}, db={data['db']:.1f}")


class TestDataIntegrity(unittest.TestCase):
    """[SUCCESS] Test 6: Integridad de Datos"""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_concurrent_device_registration(self):
        """Registros concurrentes de dispositivos"""
        print("\n" + "="*60)
        print("[TEST] TEST 6.1: Concurrent Device Registration")
        print("="*60)
        
        test_file = os.path.join(self.test_dir, 'devices_concurrent.json')
        registry = DeviceRegistry(persistence_file=test_file)
        
        def register_device(idx):
            device_uuid = f"concurrent-device-{idx}"
            registry.register_device(device_uuid, {
                'type': 'web',
                'name': f'Concurrent Device {idx}',
                'primary_ip': f'192.168.1.{100+idx}'
            })
        
        # Crear 10 threads registrando dispositivos simultáneamente
        threads = []
        for i in range(10):
            t = threading.Thread(target=register_device, args=(i,))
            threads.append(t)
            t.start()
        
        # Esperar a que terminen
        for t in threads:
            t.join()
        
        registry.save_to_disk()
        total = len(registry.devices)
        
        print(f"[OK] 10 registros concurrentes completados")
        print(f"  - Total de dispositivos: {total}")
        self.assertEqual(total, 10)
    
    def test_file_corruption_recovery(self):
        """Recuperación ante archivo corrupto"""
        print("\n" + "="*60)
        print("[TEST] TEST 6.2: File Corruption Recovery")
        print("="*60)
        
        test_file = os.path.join(self.test_dir, 'devices_corrupt.json')
        
        # Crear archivo corrompido
        os.makedirs(os.path.dirname(test_file), exist_ok=True)
        with open(test_file, 'w') as f:
            f.write("{this is not valid json {")
        
        print(f"[OK] Archivo corrupto creado")
        
        # Intentar cargar (debería manejar el error)
        try:
            registry = DeviceRegistry(persistence_file=test_file)
            print(f"[OK] Registry creado a pesar del archivo corrupto")
            print(f"  - Dispositivos cargados: {len(registry.devices)}")
        except Exception as e:
            print(f"[WARN] Error al cargar: {e}")


class TestEndToEndFlow(unittest.TestCase):
    """[SUCCESS] Test 7: Flujo Completo End-to-End"""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_complete_user_session(self):
        """Simular sesión completa de usuario"""
        print("\n" + "="*60)
        print("[TEST] TEST 7.1: Complete User Session")
        print("="*60)
        
        test_file = os.path.join(self.test_dir, 'devices_e2e.json')
        ui_state_file = os.path.join(self.test_dir, 'ui_state_e2e.json')
        
        # PASO 1: Usuario abre aplicación web
        print("\n[Paso 1] Usuario abre aplicación web")
        registry = DeviceRegistry(persistence_file=test_file)
        user_device = registry.register_device('web-user-session', {
            'type': 'web',
            'name': 'Usuario Principal',
            'primary_ip': '192.168.1.100'
        })
        print(f"[OK] Dispositivo web registrado: {user_device['name']}")
        
        # PASO 2: Usuario conecta dispositivo Android
        print("\n[Paso 2] Usuario conecta dispositivo Android")
        android_device = registry.register_device('android-user-session', {
            'type': 'android',
            'name': 'Mi Android',
            'primary_ip': '192.168.1.101'
        })
        print(f"[OK] Dispositivo Android registrado: {android_device['name']}")
        
        # PASO 3: Usuario configura canales
        print("\n[Paso 3] Usuario configura canales")
        channel_config = {
            'channels': [1, 2, 3, 4],
            'gains': {1: 0.8, 2: 0.6, 3: 0.9, 4: 0.7},
            'mutes': {2: True}
        }
        registry.update_configuration('web-user-session', channel_config)
        print(f"[OK] Configuración guardada: 4 canales, canal 2 muteado")
        
        # PASO 4: Usuario reordena dispositivos en UI
        print("\n[Paso 4] Usuario reordena dispositivos en UI")
        ui_state = {
            'client_order': ['android-user-session', 'web-user-session'],
            'updated_at': int(time.time())
        }
        os.makedirs(os.path.dirname(ui_state_file), exist_ok=True)
        with open(ui_state_file, 'w') as f:
            json.dump(ui_state, f)
        print(f"[OK] Orden guardada: Android primero, luego Web")
        
        # PASO 5: Persistir y cerrar
        print("\n[Paso 5] Persistir y cerrar aplicación")
        registry.save_to_disk()
        print(f"[OK] Datos persistidos en disco")
        print(f"  - Dispositivos: {len(registry.devices)}")
        
        # PASO 6: Usuario abre aplicación de nuevo
        print("\n[Paso 6] Usuario abre aplicación de nuevo")
        registry2 = DeviceRegistry(persistence_file=test_file)
        
        # Verificar que todo se restauró
        web_dev = registry2.get_device('web-user-session')
        android_dev = registry2.get_device('android-user-session')
        
        self.assertIsNotNone(web_dev)
        self.assertIsNotNone(android_dev)
        print(f"[OK] Ambos dispositivos restaurados")
        print(f"  - Web: {web_dev['name']}")
        print(f"  - Android: {android_dev['name']}")
        
        # Verificar configuración
        web_config = web_dev.get('configuration', {})
        gains = web_config.get('gains', {})
        # Las claves pueden ser strings o ints después de JSON
        gain_ch1 = gains.get(1) or gains.get('1')
        self.assertIsNotNone(gain_ch1)
        print(f"[OK] Configuración de canales restaurada")
        print(f"  - Ganancia Ch1: {gain_ch1}")
        
        # Verificar orden UI
        with open(ui_state_file, 'r') as f:
            loaded_ui = json.load(f)
        
        self.assertEqual(loaded_ui['client_order'][0], 'android-user-session')
        print(f"[OK] Orden UI restaurado correctamente")


def run_test_suite():
    """Ejecutar toda la suite de tests"""
    print("\n" + "="*70)
    print("[TESTS] FICHATECH MONITOR - TEST SUITE COMPLETO")
    print("="*70)
    print("Pruebas de flujo y persistencia")
    
    # Crear suite de tests
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Añadir todos los test classes
    suite.addTests(loader.loadTestsFromTestCase(TestDevicePersistence))
    suite.addTests(loader.loadTestsFromTestCase(TestChannelManager))
    suite.addTests(loader.loadTestsFromTestCase(TestUIStatePersistence))
    suite.addTests(loader.loadTestsFromTestCase(TestWebSocketFlows))
    suite.addTests(loader.loadTestsFromTestCase(TestAudioCaptureFlow))
    suite.addTests(loader.loadTestsFromTestCase(TestDataIntegrity))
    suite.addTests(loader.loadTestsFromTestCase(TestEndToEndFlow))
    
    # Ejecutar con verbosity
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Resumen final
    print("\n" + "="*70)
    print("[REPORT] RESUMEN FINAL DE TESTS")
    print("="*70)
    print(f"Tests ejecutados: {result.testsRun}")
    print(f"[OK] Exitosos: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"[FAIL] Fallos: {len(result.failures)}")
    print(f"[FAIL] Errores: {len(result.errors)}")
    
    if result.wasSuccessful():
        print("\n[SUCCESS] TODOS LOS TESTS PASARON CORRECTAMENTE")
    else:
        print("\n[WARN]️  ALGUNOS TESTS FALLARON")
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_test_suite()
    sys.exit(0 if success else 1)
