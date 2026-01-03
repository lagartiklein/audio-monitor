"""
Script de prueba para validar la lógica del mapeo de canales de 48 canales
Esto no requiere ejecutar el servidor completo
"""

import sys
sys.path.insert(0, '.')

# Test 1: Verificar que config.DEFAULT_NUM_CHANNELS existe
try:
    import config
    assert hasattr(config, 'DEFAULT_NUM_CHANNELS'), "DEFAULT_NUM_CHANNELS no existe en config"
    assert config.DEFAULT_NUM_CHANNELS == 48, f"DEFAULT_NUM_CHANNELS debe ser 48, es {config.DEFAULT_NUM_CHANNELS}"
    print("✅ Test 1 PASÓ: config.DEFAULT_NUM_CHANNELS = 48")
except Exception as e:
    print(f"❌ Test 1 FALLÓ: {e}")
    sys.exit(1)

# Test 2: Verificar que ChannelManager tiene los nuevos métodos
try:
    from audio_server.channel_manager import ChannelManager
    
    cm = ChannelManager(48)
    
    assert hasattr(cm, 'device_channel_map'), "device_channel_map no existe"
    assert hasattr(cm, 'next_available_channel'), "next_available_channel no existe"
    assert hasattr(cm, 'register_device_to_channels'), "register_device_to_channels no existe"
    assert hasattr(cm, 'get_device_channel_map'), "get_device_channel_map no existe"
    assert hasattr(cm, 'get_operational_channels'), "get_operational_channels no existe"
    
    print("✅ Test 2 PASÓ: ChannelManager tiene todos los nuevos métodos")
except Exception as e:
    print(f"❌ Test 2 FALLÓ: {e}")
    sys.exit(1)

# Test 3: Probar registro de dispositivos
try:
    cm = ChannelManager(48)
    
    # Registro de primer dispositivo (8 canales)
    mapping1 = cm.register_device_to_channels("device-001", 8)
    assert mapping1['start_channel'] == 0, f"Primer dispositivo debe empezar en 0, empezó en {mapping1['start_channel']}"
    assert mapping1['num_channels'] == 8, f"Primer dispositivo debe tener 8 canales, tiene {mapping1['num_channels']}"
    assert mapping1['operacional'] == True, "Primer dispositivo debe ser operacional"
    
    # Registro de segundo dispositivo (16 canales)
    mapping2 = cm.register_device_to_channels("device-002", 16)
    assert mapping2['start_channel'] == 8, f"Segundo dispositivo debe empezar en 8, empezó en {mapping2['start_channel']}"
    assert mapping2['num_channels'] == 16, f"Segundo dispositivo debe tener 16 canales, tiene {mapping2['num_channels']}"
    assert mapping2['operacional'] == True, "Segundo dispositivo debe ser operacional"
    
    # Registro de tercer dispositivo (30 canales - pero solo hay 24 disponibles)
    mapping3 = cm.register_device_to_channels("device-003", 30)
    assert mapping3['start_channel'] == 24, f"Tercer dispositivo debe empezar en 24, empezó en {mapping3['start_channel']}"
    assert mapping3['num_channels'] == 24, f"Tercer dispositivo debe tener 24 canales (max disponible), tiene {mapping3['num_channels']}"
    assert mapping3['operacional'] == True, "Tercer dispositivo debe ser operacional"
    
    # Registro de cuarto dispositivo (sin espacio disponible)
    mapping4 = cm.register_device_to_channels("device-004", 8)
    assert mapping4['start_channel'] == -1, f"Cuarto dispositivo sin espacio debe tener start_channel -1, tiene {mapping4['start_channel']}"
    assert mapping4['num_channels'] == 0, f"Cuarto dispositivo sin espacio debe tener 0 canales, tiene {mapping4['num_channels']}"
    assert mapping4['operacional'] == False, "Cuarto dispositivo sin espacio debe ser no operacional"
    
    print("✅ Test 3 PASÓ: Registro automático de dispositivos funciona correctamente")
except Exception as e:
    print(f"❌ Test 3 FALLÓ: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Probar get_operational_channels()
try:
    cm = ChannelManager(48)
    
    cm.register_device_to_channels("device-001", 8)
    cm.register_device_to_channels("device-002", 16)
    
    operational = cm.get_operational_channels()
    expected = set(range(0, 24))  # 0-23 son operacionales
    
    assert operational == expected, f"Canales operacionales incorrectos. Esperado {expected}, obtenido {operational}"
    
    print("✅ Test 4 PASÓ: get_operational_channels() retorna conjunto correcto")
except Exception as e:
    print(f"❌ Test 4 FALLÓ: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 5: Probar get_device_channel_map()
try:
    cm = ChannelManager(48)
    mapping = cm.register_device_to_channels("device-test", 12)
    
    retrieved = cm.get_device_channel_map("device-test")
    assert retrieved == mapping, "Mapeo recuperado no coincide con original"
    
    not_found = cm.get_device_channel_map("device-nonexistent")
    assert not_found['operacional'] == False, "Dispositivo inexistente debe retornar no operacional"
    
    print("✅ Test 5 PASÓ: get_device_channel_map() funciona correctamente")
except Exception as e:
    print(f"❌ Test 5 FALLÓ: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*60)
print("✅ TODOS LOS TESTS PASARON EXITOSAMENTE")
print("="*60)
print("\nResumen:")
print(f"  - DEFAULT_NUM_CHANNELS configurado en 48")
print(f"  - Nuevo sistema de mapeo de canales implementado")
print(f"  - ChannelManager puede mapear múltiples dispositivos")
print(f"  - Canales operacionales se rastrean correctamente")
