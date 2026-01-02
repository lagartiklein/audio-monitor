# test_device_registry.py - Test del Sistema de Identificación de Dispositivos

import os
import sys
import json
import time
import uuid as uuid_module
import tempfile
import shutil

# Configurar path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from audio_server.device_registry import DeviceRegistry, init_device_registry

def test_basic_registration():
    """Test 1: Registro básico de dispositivo"""
    print("\n" + "="*70)
    print("TEST 1: Registro básico de dispositivo")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        registry = DeviceRegistry(os.path.join(tmpdir, "test_devices.json"))
        
        # Registrar dispositivo
        device_uuid = str(uuid_module.uuid4())
        device = registry.register_device(device_uuid, {
            'type': 'web',
            'name': 'Test Browser',
            'primary_ip': '192.168.1.100',
            'user_agent': 'Mozilla/5.0'
        })
        
        print(f"✅ Dispositivo registrado: {device_uuid[:12]}")
        print(f"   Nombre: {device['name']}")
        print(f"   Tipo: {device['type']}")
        print(f"   IP: {device['primary_ip']}")
        print(f"   Primera vez: {device['first_seen']}")
        
        # Verificar que se puede recuperar
        retrieved = registry.get_device(device_uuid)
        assert retrieved is not None, "No se pudo recuperar dispositivo"
        assert retrieved['uuid'] == device_uuid, "UUID no coincide"
        print(f"✅ Dispositivo recuperado correctamente")


def test_configuration_persistence():
    """Test 2: Persistencia de configuración"""
    print("\n" + "="*70)
    print("TEST 2: Persistencia de configuración")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        registry = DeviceRegistry(os.path.join(tmpdir, "test_devices.json"))
        
        device_uuid = str(uuid_module.uuid4())
        registry.register_device(device_uuid, {'type': 'web', 'name': 'Test'})
        
        # Guardar configuración
        config = {
            'channels': [0, 1, 2, 3],
            'gains': {0: 1.0, 1: 0.8, 2: 0.9, 3: 1.2},
            'pans': {0: 0.0, 1: -0.5, 2: 0.5, 3: 0.0},
            'master_gain': 1.0
        }
        
        registry.update_configuration(device_uuid, config)
        print(f"✅ Configuración guardada para {device_uuid[:12]}")
        print(f"   Canales: {config['channels']}")
        print(f"   Ganancia master: {config['master_gain']}")
        
        # Recuperar configuración
        retrieved_config = registry.get_configuration(device_uuid)
        assert retrieved_config == config, "Configuración no coincide"
        print(f"✅ Configuración recuperada correctamente")


def test_persistence_to_disk():
    """Test 3: Persistencia en archivo JSON"""
    print("\n" + "="*70)
    print("TEST 3: Persistencia en archivo JSON")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = os.path.join(tmpdir, "devices.json")
        
        # Crear registry y guardar datos
        registry1 = DeviceRegistry(file_path)
        device_uuid = str(uuid_module.uuid4())
        
        registry1.register_device(device_uuid, {
            'type': 'android',
            'name': 'Samsung S21',
            'mac_address': 'AA:BB:CC:DD:EE:FF'
        })
        
        config = {
            'channels': [0, 1],
            'gains': {0: 1.0, 1: 0.8}
        }
        registry1.update_configuration(device_uuid, config)
        
        print(f"✅ Datos guardados")
        print(f"   Device UUID: {device_uuid[:12]}")
        
        # Verificar archivo JSON
        assert os.path.exists(file_path), "Archivo no fue creado"
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        assert device_uuid in data, "Dispositivo no está en JSON"
        print(f"✅ Archivo JSON válido")
        print(f"   Dispositivos: {len(data)}")
        
        # Crear nuevo registry y cargar datos
        registry2 = DeviceRegistry(file_path)
        time.sleep(0.05)  # Permitir que cargue
        
        retrieved = registry2.get_device(device_uuid)
        assert retrieved is not None, "No se pudo cargar dispositivo"
        assert retrieved['name'] == 'Samsung S21', "Nombre no coincide"
        
        retrieved_config = registry2.get_configuration(device_uuid)
        # Verificar que los canales y ganancias están presentes (JSON convierte keys a strings)
        assert retrieved_config.get('channels') == config['channels'], "Canales no coinciden"
        print(f"✅ Datos cargados correctamente desde JSON")
        print(f"   Config persistida: canales={retrieved_config.get('channels')}")


def test_reconnection_scenario():
    """Test 4: Escenario de reconexión"""
    print("\n" + "="*70)
    print("TEST 4: Escenario de reconexión")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        registry = DeviceRegistry(os.path.join(tmpdir, "test_devices.json"))
        
        device_uuid = str(uuid_module.uuid4())
        
        # 1. Conexión inicial
        print("\n1️⃣ Conexión inicial...")
        registry.register_device(device_uuid, {
            'type': 'web',
            'primary_ip': '192.168.1.100'
        })
        
        initial_config = {
            'channels': [0, 1, 2],
            'gains': {0: 1.0, 1: 0.8, 2: 0.9},
            'pans': {0: 0.0, 1: -0.5, 2: 0.5}
        }
        registry.update_configuration(device_uuid, initial_config)
        print(f"   Config guardada: {initial_config}")
        
        # 2. Cambio de red
        print("\n2️⃣ Cambio de red (reconexión)...")
        time.sleep(0.1)  # Simular paso de tiempo
        
        registry.register_device(device_uuid, {
            'type': 'web',
            'primary_ip': '192.168.2.50'  # ¡IP diferente!
        })
        print(f"   Reconexión registrada desde IP diferente")
        
        # 3. Verificar que config se recupera
        print("\n3️⃣ Verificar configuración...")
        device = registry.get_device(device_uuid)
        retrieved_config = registry.get_configuration(device_uuid)
        
        assert retrieved_config == initial_config, "Config se perdió en reconexión"
        assert device['reconnections'] == 1, "Contador de reconexiones incorrecto"
        assert device['primary_ip'] == '192.168.2.50', "IP no se actualizó"
        
        print(f"   ✅ Configuración restaurada: {retrieved_config}")
        print(f"   ✅ Reconexiones: {device['reconnections']}")
        print(f"   ✅ IP actualizada: {device['primary_ip']}")
        print(f"\n✅ Escenario de reconexión completado exitosamente")


def test_multiple_devices():
    """Test 5: Múltiples dispositivos"""
    print("\n" + "="*70)
    print("TEST 5: Múltiples dispositivos")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        registry = DeviceRegistry(os.path.join(tmpdir, "test_devices.json"))
        
        # Registrar múltiples dispositivos
        devices = []
        for i in range(3):
            uuid_str = str(uuid_module.uuid4())
            registry.register_device(uuid_str, {
                'type': ['web', 'android', 'web'][i],
                'name': f'Device {i+1}',
                'primary_ip': f'192.168.1.{100+i}'
            })
            devices.append(uuid_str)
            print(f"   ✅ Dispositivo {i+1} registrado: {uuid_str[:12]}")
        
        # Verificar lista
        all_devices = registry.get_all_devices()
        assert len(all_devices) == 3, "No se registraron todos los dispositivos"
        print(f"\n✅ Total de dispositivos: {len(all_devices)}")
        
        # Verificar estadísticas
        stats = registry.get_stats()
        print(f"✅ Estadísticas:")
        print(f"   Total: {stats['total_devices']}")
        print(f"   Por tipo: {stats['by_type']}")


def test_cleanup():
    """Test 6: Limpieza de dispositivos expirados"""
    print("\n" + "="*70)
    print("TEST 6: Limpieza de dispositivos expirados (simulado)")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        registry = DeviceRegistry(os.path.join(tmpdir, "test_devices.json"))
        
        # Registrar dispositivo
        device_uuid = str(uuid_module.uuid4())
        registry.register_device(device_uuid, {'type': 'web', 'name': 'Old Device'})
        
        # Simular envejecimiento manual (para test)
        with registry.device_lock:
            registry.devices[device_uuid]['last_seen'] = time.time() - (registry.device_cache_timeout + 100)
        
        print(f"✅ Dispositivo envejecido manualmente")
        print(f"   UUID: {device_uuid[:12]}")
        print(f"   Timeout: {registry.device_cache_timeout}s")
        
        # Limpiar
        cleaned = registry.cleanup_expired()
        print(f"✅ Dispositivos eliminados: {cleaned}")
        
        # Verificar que se eliminó
        retrieved = registry.get_device(device_uuid)
        assert retrieved is None, "Dispositivo no fue eliminado"
        print(f"✅ Dispositivo eliminado correctamente")


def run_all_tests():
    """Ejecutar todos los tests"""
    print("\n" + "="*70)
    print("TESTS DEL DEVICE REGISTRY")
    print("="*70)
    
    tests = [
        test_basic_registration,
        test_configuration_persistence,
        test_persistence_to_disk,
        test_reconnection_scenario,
        test_multiple_devices,
        test_cleanup
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"\n❌ TEST FALLIDO: {test.__name__}")
            print(f"   Error: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    # Resumen
    print("\n" + "="*70)
    print("RESUMEN DE TESTS")
    print("="*70)
    print(f"Pasados: {passed}/{len(tests)}")
    print(f"Fallidos: {failed}/{len(tests)}")
    
    if failed == 0:
        print("\nTODOS LOS TESTS PASARON!")
        return 0
    else:
        print(f"\n{failed} tests fallaron")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)

