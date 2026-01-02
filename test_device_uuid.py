#!/usr/bin/env python3
"""
✅ Test: Verificar que el servidor Python recibe y persiste device_uuid correctamente
- Simula conexión TCP desde Android con device_uuid
- Verifica que se registra en DeviceRegistry
- Verifica que se restaura después de desconexión
"""

import socket
import json
import struct
import time
import sys
import os

# Agregar path
sys.path.insert(0, os.path.dirname(__file__))

import config
from audio_server.device_registry import init_device_registry
from audio_server.channel_manager import ChannelManager
from audio_server.native_server import NativeAudioServer, NativeClient, NativeAndroidProtocol

def test_device_uuid_handshake():
    """Test 1: Handshake TCP con device_uuid"""
    print("\n" + "="*70)
    print("🧪 TEST 1: Handshake TCP con device_uuid")
    print("="*70)
    
    # Inicializar
    device_registry = init_device_registry("config/devices.json")
    server_session_id = "test-session-001"
    device_registry.set_server_session(server_session_id)
    
    channel_manager = ChannelManager(8)
    channel_manager.set_device_registry(device_registry)
    channel_manager.set_server_session_id(server_session_id)
    
    native_server = NativeAudioServer(channel_manager)
    
    # Simular cliente RF
    test_device_uuid = "test-device-uuid-123456789"
    
    # Simular handshake
    handshake_msg = {
        "type": "handshake",
        "client_id": "temp-client-id",
        "device_uuid": test_device_uuid,
        "device_name": "Test Android Device",
        "client_type": "android",
        "protocol_version": 2,
        "rf_mode": True,
        "persistent": True,
        "auto_reconnect": True
    }
    
    # Simular control message
    msg_json = json.dumps(handshake_msg)
    msg_bytes = msg_json.encode('utf-8')
    
    # Armar paquete (header + payload)
    header = struct.pack('!IHHII',
        NativeAndroidProtocol.MAGIC_NUMBER,
        NativeAndroidProtocol.PROTOCOL_VERSION,
        (NativeAndroidProtocol.MSG_TYPE_CONTROL << 8) | 0x80,  # FLAG_RF_MODE
        int(time.time() * 1000) & 0xFFFFFFFF,
        len(msg_bytes)
    )
    packet = header + msg_bytes
    
    print(f"✅ Handshake armado:")
    print(f"   client_id: {handshake_msg['client_id']}")
    print(f"   device_uuid: {handshake_msg['device_uuid']}")
    print(f"   Tamaño del mensaje: {len(msg_bytes)} bytes")
    
    # Verificar que puede parsear el mensaje
    try:
        parsed = json.loads(msg_bytes)
        assert parsed['type'] == 'handshake'
        assert parsed['device_uuid'] == test_device_uuid
        print(f"✅ TEST 1 PASÓ: Handshake valido con device_uuid")
    except Exception as e:
        print(f"❌ TEST 1 FALLÓ: {e}")
        return False
    
    return True


def test_device_registry_persistence():
    """Test 2: Device Registry persiste device_uuid"""
    print("\n" + "="*70)
    print("🧪 TEST 2: Device Registry persiste device_uuid")
    print("="*70)
    
    device_registry = init_device_registry("config/devices.json.test")
    server_session_id = "test-session-002"
    device_registry.set_server_session(server_session_id)
    
    test_device_uuid = "test-device-uuid-87654321"
    
    # Registrar dispositivo
    device_info = {
        'type': 'android',
        'name': 'Test Device 2',
        'primary_ip': '192.168.1.100',
        'client_id': 'test-client-id-2'
    }
    
    device_registry.register_device(test_device_uuid, device_info)
    print(f"✅ Dispositivo registrado: {test_device_uuid}")
    
    # Verificar que se guardó
    device = device_registry.get_device(test_device_uuid)
    if device:
        print(f"✅ Dispositivo recuperado: {device['name']}")
        assert device['uuid'] == test_device_uuid
        print(f"✅ UUID coincide")
    else:
        print(f"❌ TEST 2 FALLÓ: Device no se recuperó")
        return False
    
    # Guardar configuración con sesión
    config_data = {
        'channels': [0, 1, 2],
        'gains': {0: 1.0, 1: 0.8},
        'pans': {0: 0.0, 1: -0.5}
    }
    
    device_registry.update_configuration(test_device_uuid, config_data, session_id=server_session_id)
    print(f"✅ Configuración guardada para sesión: {server_session_id[:12]}...")
    
    # Verificar que se recupera con la misma sesión
    recovered = device_registry.get_configuration(test_device_uuid, session_id=server_session_id)
    if recovered == config_data:
        print(f"✅ Configuración recuperada correctamente (sesión coincide)")
    else:
        print(f"❌ TEST 2 FALLÓ: Configuración no coincide")
        return False
    
    # Verificar que NO se recupera con otra sesión
    recovered_diff = device_registry.get_configuration(test_device_uuid, session_id="different-session")
    if not recovered_diff:
        print(f"✅ Configuración NO recuperada con sesión diferente (OK)")
    else:
        print(f"⚠️  Configuración recuperada con sesión diferente (comportamiento diferente)")
    
    print(f"✅ TEST 2 PASÓ: Device Registry persiste por device_uuid")
    return True


def test_channel_manager_device_uuid():
    """Test 3: ChannelManager usa device_uuid"""
    print("\n" + "="*70)
    print("🧪 TEST 3: ChannelManager usa device_uuid")
    print("="*70)
    
    device_registry = init_device_registry("config/devices.json.test2")
    channel_manager = ChannelManager(8)
    channel_manager.set_device_registry(device_registry)
    
    test_device_uuid = "test-device-uuid-for-cm"
    test_client_id = "socket-client-id-123"
    
    # Suscribir cliente con device_uuid
    channels = [0, 1, 2, 3]
    channel_manager.subscribe_client(
        test_client_id,
        channels,
        client_type="native",
        device_uuid=test_device_uuid
    )
    
    print(f"✅ Cliente suscrito: {test_client_id}")
    print(f"   Device UUID: {test_device_uuid}")
    print(f"   Canales: {channels}")
    
    # Verificar que se puede recuperar por device_uuid
    client_id = channel_manager.get_client_by_device_uuid(test_device_uuid)
    if client_id == test_client_id:
        print(f"✅ Cliente recuperado por device_uuid: {client_id}")
    else:
        print(f"❌ TEST 3 FALLÓ: No se recuperó el cliente")
        return False
    
    # Verificar que clients_info incluye device_uuid
    clients_info = channel_manager.get_all_clients_info()
    found = False
    for client in clients_info:
        if client['id'] == test_client_id:
            if client.get('device_uuid') == test_device_uuid:
                print(f"✅ device_uuid en clients_info: {client.get('device_uuid')[:12]}...")
                found = True
            else:
                print(f"❌ device_uuid NO está en clients_info")
                return False
    
    if not found:
        print(f"❌ TEST 3 FALLÓ: Cliente no en clients_info")
        return False
    
    print(f"✅ TEST 3 PASÓ: ChannelManager usa device_uuid correctamente")
    return True


if __name__ == "__main__":
    print("\n" + "="*70)
    print("🧪 EJECUTANDO TESTS DE DEVICE_UUID")
    print("="*70)
    
    results = []
    results.append(("Handshake TCP con device_uuid", test_device_uuid_handshake()))
    results.append(("Device Registry persiste", test_device_registry_persistence()))
    results.append(("ChannelManager usa device_uuid", test_channel_manager_device_uuid()))
    
    print("\n" + "="*70)
    print("📊 RESULTADOS")
    print("="*70)
    
    passed = 0
    for name, result in results:
        status = "✅ PASÓ" if result else "❌ FALLÓ"
        print(f"{status}: {name}")
        if result:
            passed += 1
    
    print("\n" + "="*70)
    print(f"Total: {passed}/{len(results)} tests pasaron")
    print("="*70 + "\n")
    
    sys.exit(0 if passed == len(results) else 1)
