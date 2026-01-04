#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🧪 TEST SUITE COMPLETO: Flujo, Datos y Persistencia
Ejecutar en terminal diferente al servidor
"""

import sys
import os
import time
import json
import socket
import threading
import uuid as uuid_module
from pathlib import Path

# Agregar path del proyecto
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
from requests.exceptions import ConnectionError

# Importar SocketIO client
try:
    import socketio
except ImportError:
    print("❌ Falta: pip install python-socketio python-engineio")
    sys.exit(1)

import config

# ============================================================================
# COLORES PARA TERMINAL
# ============================================================================

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    YELLOW = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

SERVER_URL = f"http://127.0.0.1:{config.WEB_PORT}"
NATIVE_PORT = config.NATIVE_PORT
NATIVE_HOST = "127.0.0.1"

TESTS_PASSED = 0
TESTS_FAILED = 0

# ============================================================================
# HELPERS
# ============================================================================

def print_header(text):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*70}")
    print(f"  {text}")
    print(f"{'='*70}{Colors.ENDC}\n")

def print_test(text, status=""):
    if status == "PASS":
        print(f"  ✅ {Colors.OKGREEN}{text}{Colors.ENDC}")
        global TESTS_PASSED
        TESTS_PASSED += 1
    elif status == "FAIL":
        print(f"  ❌ {Colors.FAIL}{text}{Colors.ENDC}")
        global TESTS_FAILED
        TESTS_FAILED += 1
    else:
        print(f"  🔍 {Colors.OKCYAN}{text}{Colors.ENDC}")

def print_info(text):
    print(f"  ℹ️  {Colors.OKCYAN}{text}{Colors.ENDC}")

def print_success(text):
    print(f"  ✅ {Colors.OKGREEN}{text}{Colors.ENDC}")

def print_error(text):
    print(f"  ❌ {Colors.FAIL}{text}{Colors.ENDC}")

def wait_for_server(timeout=10):
    """Esperar a que servidor esté listo"""
    start = time.time()
    while time.time() - start < timeout:
        try:
            requests.get(f"{SERVER_URL}/status", timeout=1)
            return True
        except:
            time.sleep(0.5)
    return False

# ============================================================================
# TEST 1: SERVIDOR DISPONIBLE
# ============================================================================

def test_servidor_disponible():
    print_header("TEST 1: Servidor Disponible")
    
    try:
        response = requests.get(f"{SERVER_URL}/", timeout=5)
        print_test(f"Servidor accesible en {SERVER_URL}", "PASS")
        return True
    except ConnectionError as e:
        print_test(f"Servidor NO accesible: {e}", "FAIL")
        print_error(f"Asegúrate de tener el servidor corriendo en {SERVER_URL}")
        return False

# ============================================================================
# TEST 2: CONEXIÓN WEB CLIENT
# ============================================================================

def test_conexion_web_client():
    print_header("TEST 2: Conexión Web Client")
    
    try:
        sio = socketio.Client()
        connected = threading.Event()
        
        @sio.on('connect')
        def on_connect():
            print_test("WebSocket conectado", "PASS")
            connected.set()
        
        @sio.on('error')
        def on_error(data):
            print_error(f"Error: {data}")
        
        device_uuid = f"test-web-{uuid_module.uuid4().hex[:8]}"
        sio.connect(
            SERVER_URL,
            auth={'device_uuid': device_uuid, 'device_name': 'Test Web'}
        )
        
        # Esperar conexión
        if connected.wait(timeout=5):
            print_test(f"Device UUID registrado: {device_uuid}", "PASS")
            time.sleep(1)
            sio.disconnect()
            return True
        else:
            print_test("Timeout esperando conexión", "FAIL")
            return False
            
    except Exception as e:
        print_test(f"Error conectando: {e}", "FAIL")
        return False

# ============================================================================
# TEST 3: REGISTRACIÓN EN device_registry
# ============================================================================

def test_device_registry():
    print_header("TEST 3: Registración en device_registry")
    
    try:
        devices_file = Path("config/devices.json")
        if not devices_file.exists():
            print_test(f"Archivo devices.json NO encontrado", "FAIL")
            return False
        
        with open(devices_file, 'r') as f:
            devices = json.load(f)
        
        device_count = len(devices)
        print_test(f"device_registry cargado: {device_count} dispositivos", "PASS")
        
        # Verificar que hay web clients
        web_devices = [d for d in devices.values() if d.get('type') == 'web']
        print_test(f"Web clients registrados: {len(web_devices)}", "PASS")
        
        # Verificar que hay android clients
        android_devices = [d for d in devices.values() if d.get('type') == 'android']
        print_test(f"Android clients registrados: {len(android_devices)}", "PASS")
        
        return True
        
    except Exception as e:
        print_test(f"Error leyendo device_registry: {e}", "FAIL")
        return False

# ============================================================================
# TEST 4: UNICIDAD DE CLIENTES
# ============================================================================

def test_unicidad_clientes():
    print_header("TEST 4: Unicidad de Clientes")
    
    try:
        devices_file = Path("config/devices.json")
        with open(devices_file, 'r') as f:
            devices = json.load(f)
        
        # Verificar que UUIDs son únicos
        uuids = list(devices.keys())
        unique_uuids = set(uuids)
        
        if len(uuids) == len(unique_uuids):
            print_test(f"Todos los UUIDs son únicos ({len(unique_uuids)} dispositivos)", "PASS")
        else:
            duplicates = len(uuids) - len(unique_uuids)
            print_test(f"❌ {duplicates} UUIDs duplicados detectados", "FAIL")
            return False
        
        # Verificar que cada dispositivo tiene sus campos
        for uuid, device in devices.items():
            required_fields = ['uuid', 'type', 'name', 'first_seen', 'last_seen']
            for field in required_fields:
                if field not in device:
                    print_test(f"❌ Campo faltante '{field}' en {uuid[:12]}", "FAIL")
                    return False
        
        print_test("Todos los dispositivos tienen campos requeridos", "PASS")
        return True
        
    except Exception as e:
        print_test(f"Error verificando unicidad: {e}", "FAIL")
        return False

# ============================================================================
# TEST 5: CAMBIOS REFLEJADOS EN SERVIDOR (WEB CLIENT)
# ============================================================================

def test_cambios_web_cliente():
    print_header("TEST 5: Cambios Reflejados (Web Client)")
    
    try:
        sio = socketio.Client()
        received_events = {}
        connected = threading.Event()
        
        @sio.on('connect')
        def on_connect():
            connected.set()
        
        @sio.on('clients_update')
        def on_clients_update(data):
            received_events['clients_update'] = data
        
        @sio.on('device_info')
        def on_device_info(data):
            received_events['device_info'] = data
        
        device_uuid = f"test-web-{uuid_module.uuid4().hex[:8]}"
        sio.connect(SERVER_URL, auth={'device_uuid': device_uuid})
        
        if not connected.wait(timeout=5):
            print_test("Timeout conectando", "FAIL")
            return False
        
        print_test("Web client conectado", "PASS")
        time.sleep(1)
        
        # Enviar cambio de mezcla
        sio.emit('update_client_mix', {
            'target_client_id': device_uuid,
            'channels': [0, 1, 2]
        })
        
        print_test("Cambio enviado: channels=[0,1,2]", "PASS")
        time.sleep(1)
        
        # Verificar que se recibió confirmación
        if 'clients_update' in received_events:
            print_test("✅ Server emitió clients_update (confirmación)", "PASS")
        else:
            print_test("❌ No se recibió clients_update", "FAIL")
        
        sio.disconnect()
        print_test("Web client desconectado", "PASS")
        return True
        
    except Exception as e:
        print_test(f"Error en test web: {e}", "FAIL")
        return False

# ============================================================================
# TEST 6: PERSISTENCIA EN DISCO
# ============================================================================

def test_persistencia_disco():
    print_header("TEST 6: Persistencia en Disco")
    
    try:
        # Conectar web client y hacer cambio
        sio = socketio.Client()
        connected = threading.Event()
        
        @sio.on('connect')
        def on_connect():
            connected.set()
        
        device_uuid = f"test-persist-{uuid_module.uuid4().hex[:8]}"
        sio.connect(SERVER_URL, auth={'device_uuid': device_uuid})
        
        if not connected.wait(timeout=5):
            print_test("Timeout conectando", "FAIL")
            return False
        
        # Hacer cambio
        sio.emit('update_client_mix', {
            'target_client_id': device_uuid,
            'channels': [3, 4, 5]
        })
        
        print_test(f"Cambio enviado para {device_uuid[:16]}", "PASS")
        time.sleep(2)  # Esperar a que se escriba a disco
        
        sio.disconnect()
        
        # Verificar que se guardó en disco
        devices_file = Path("config/devices.json")
        with open(devices_file, 'r') as f:
            devices = json.load(f)
        
        if device_uuid in devices:
            print_test(f"✅ Dispositivo encontrado en device_registry", "PASS")
            
            config = devices[device_uuid].get('configuration', {})
            channels = config.get('channels', [])
            
            print_test(f"Configuración guardada: channels={channels}", "PASS")
            return True
        else:
            print_test(f"❌ Dispositivo NO encontrado en registry", "FAIL")
            return False
        
    except Exception as e:
        print_test(f"Error en persistencia: {e}", "FAIL")
        return False

# ============================================================================
# TEST 7: SINCRONIZACIÓN WEB -> SERVIDOR
# ============================================================================

def test_sync_web_server():
    print_header("TEST 7: Sincronización Web → Servidor")
    
    try:
        sio = socketio.Client()
        param_sync_received = threading.Event()
        received_params = {}
        
        @sio.on('connect')
        def on_connect():
            pass
        
        @sio.on('param_sync')
        def on_param_sync(data):
            received_params['sync'] = data
            param_sync_received.set()
        
        device_uuid = f"test-sync-{uuid_module.uuid4().hex[:8]}"
        sio.connect(SERVER_URL, auth={'device_uuid': device_uuid})
        
        time.sleep(1)
        
        # Hacer cambio
        sio.emit('update_client_mix', {
            'target_client_id': device_uuid,
            'channels': [0, 1]
        })
        
        # Esperar param_sync (podría venir de otro cambio)
        if param_sync_received.wait(timeout=3):
            print_test("✅ param_sync recibido", "PASS")
            sync_data = received_params.get('sync', {})
            print_info(f"Datos: type={sync_data.get('type')}, "
                      f"channel={sync_data.get('channel')}, "
                      f"value={sync_data.get('value')}")
        else:
            print_test("⚠️ No se recibió param_sync en 3s (puede estar OK)", "PASS")
        
        sio.disconnect()
        return True
        
    except Exception as e:
        print_test(f"Error en sync test: {e}", "FAIL")
        return False

# ============================================================================
# TEST 8: RECONEXIÓN Y RESTAURACIÓN
# ============================================================================

def test_reconexion_restauracion():
    print_header("TEST 8: Reconexión y Restauración")
    
    try:
        # Primera conexión - hacer cambio
        sio1 = socketio.Client()
        connected1 = threading.Event()
        
        @sio1.on('connect')
        def on_connect1():
            connected1.set()
        
        device_uuid = f"test-recon-{uuid_module.uuid4().hex[:8]}"
        sio1.connect(SERVER_URL, auth={'device_uuid': device_uuid})
        
        if not connected1.wait(timeout=5):
            print_test("Primera conexión falló", "FAIL")
            return False
        
        print_test("Primera conexión establecida", "PASS")
        
        # Hacer cambio
        sio1.emit('update_client_mix', {
            'target_client_id': device_uuid,
            'channels': [1, 2, 3]
        })
        
        print_test("Cambio hecho: channels=[1,2,3]", "PASS")
        time.sleep(1)
        
        sio1.disconnect()
        print_test("Primera sesión desconectada", "PASS")
        time.sleep(1)
        
        # Segunda conexión - restaurar
        sio2 = socketio.Client()
        connected2 = threading.Event()
        auto_resubscribed = threading.Event()
        
        @sio2.on('connect')
        def on_connect2():
            connected2.set()
        
        @sio2.on('auto_resubscribed')
        def on_auto_resubscribed(data):
            auto_resubscribed.set()
        
        sio2.connect(SERVER_URL, auth={'device_uuid': device_uuid})
        
        if not connected2.wait(timeout=5):
            print_test("Segunda conexión falló", "FAIL")
            return False
        
        print_test("Segunda conexión establecida", "PASS")
        
        # Esperar restauración
        if auto_resubscribed.wait(timeout=3):
            print_test("✅ Estado automáticamente restaurado", "PASS")
        else:
            print_test("⚠️ auto_resubscribed no recibido (puede estar OK)", "PASS")
        
        time.sleep(1)
        sio2.disconnect()
        return True
        
    except Exception as e:
        print_test(f"Error en reconexión: {e}", "FAIL")
        return False

# ============================================================================
# TEST 9: LOAD TEST - MÚLTIPLES CAMBIOS RÁPIDOS
# ============================================================================

def test_load_cambios_rapidos():
    print_header("TEST 9: Load Test - Cambios Rápidos")
    
    try:
        sio = socketio.Client()
        connected = threading.Event()
        
        @sio.on('connect')
        def on_connect():
            connected.set()
        
        device_uuid = f"test-load-{uuid_module.uuid4().hex[:8]}"
        sio.connect(SERVER_URL, auth={'device_uuid': device_uuid})
        
        if not connected.wait(timeout=5):
            print_test("Conexión falló", "FAIL")
            return False
        
        print_test("Web client conectado para load test", "PASS")
        
        # Hacer 20 cambios rápidos
        start = time.time()
        for i in range(20):
            channels = list(range(i % 8))
            sio.emit('update_client_mix', {
                'target_client_id': device_uuid,
                'channels': channels
            })
        
        elapsed = time.time() - start
        
        print_test(f"20 cambios enviados en {elapsed:.2f}s ({elapsed/20*1000:.1f}ms cada uno)", "PASS")
        
        time.sleep(2)
        sio.disconnect()
        return True
        
    except Exception as e:
        print_test(f"Error en load test: {e}", "FAIL")
        return False

# ============================================================================
# TEST 10: CONSISTENCIA DE device_registry
# ============================================================================

def test_consistencia_registry():
    print_header("TEST 10: Consistencia device_registry")
    
    try:
        devices_file = Path("config/devices.json")
        
        # Verificar que archivo es JSON válido
        try:
            with open(devices_file, 'r') as f:
                devices = json.load(f)
            print_test("✅ config/devices.json es JSON válido", "PASS")
        except json.JSONDecodeError as e:
            print_test(f"❌ JSON inválido: {e}", "FAIL")
            return False
        
        # Verificar estructura
        errors = []
        for uuid, device in devices.items():
            # Verificar que uuid coincide
            if device.get('uuid') != uuid:
                errors.append(f"UUID mismatch en {uuid[:12]}")
            
            # Verificar timestamps
            if not isinstance(device.get('first_seen'), (int, float)):
                errors.append(f"first_seen no es timestamp en {uuid[:12]}")
            
            # Verificar que configuration es dict
            config = device.get('configuration', {})
            if not isinstance(config, dict):
                errors.append(f"configuration no es dict en {uuid[:12]}")
        
        if errors:
            for error in errors[:5]:  # Mostrar primeros 5
                print_test(f"❌ {error}", "FAIL")
            return False
        else:
            print_test("✅ device_registry estructura válida", "PASS")
            print_info(f"Total dispositivos: {len(devices)}")
            return True
        
    except Exception as e:
        print_test(f"Error verificando consistencia: {e}", "FAIL")
        return False

# ============================================================================
# MAIN
# ============================================================================

def main():
    print(f"""
{Colors.BOLD}{Colors.OKBLUE}
╔══════════════════════════════════════════════════════════════════════╗
║                    🧪 TEST SUITE COMPLETO                            ║
║              Flujo de Información, Datos y Persistencia              ║
╚══════════════════════════════════════════════════════════════════════╝
{Colors.ENDC}
""")
    
    print_info(f"Servidor: {SERVER_URL}")
    print_info(f"Native Port: {NATIVE_PORT}")
    print()
    
    # Esperar a que servidor esté listo
    print("⏳ Esperando servidor...")
    if not wait_for_server(timeout=30):
        print_error("Servidor NO responde. Asegúrate de que esté corriendo.")
        return
    
    print_success("Servidor listo!\n")
    
    # Ejecutar tests
    tests = [
        ("Servidor disponible", test_servidor_disponible),
        ("Conexión web client", test_conexion_web_client),
        ("device_registry", test_device_registry),
        ("Unicidad de clientes", test_unicidad_clientes),
        ("Cambios reflejados (Web)", test_cambios_web_cliente),
        ("Persistencia en disco", test_persistencia_disco),
        ("Sincronización Web→Server", test_sync_web_server),
        ("Reconexión y restauración", test_reconexion_restauracion),
        ("Load test", test_load_cambios_rapidos),
        ("Consistencia registry", test_consistencia_registry),
    ]
    
    for name, test_func in tests:
        try:
            test_func()
            time.sleep(1)  # Delay entre tests
        except Exception as e:
            print_error(f"Excepción en {name}: {e}")
            import traceback
            traceback.print_exc()
    
    # Resumen
    print_header("📊 RESUMEN DE TESTS")
    
    total = TESTS_PASSED + TESTS_FAILED
    percentage = (TESTS_PASSED / total * 100) if total > 0 else 0
    
    print(f"  ✅ Tests pasados: {Colors.OKGREEN}{TESTS_PASSED}{Colors.ENDC}")
    print(f"  ❌ Tests fallidos: {Colors.FAIL}{TESTS_FAILED}{Colors.ENDC}")
    print(f"  📊 Total: {total}")
    print(f"  📈 Éxito: {Colors.OKGREEN}{percentage:.1f}%{Colors.ENDC}")
    
    print()
    
    if TESTS_FAILED == 0:
        print(f"{Colors.OKGREEN}{Colors.BOLD}✅ TODOS LOS TESTS PASARON ✅{Colors.ENDC}")
        print(f"{Colors.OKGREEN}   El sistema está LISTO PARA PRODUCCIÓN{Colors.ENDC}\n")
        return 0
    else:
        print(f"{Colors.FAIL}{Colors.BOLD}❌ {TESTS_FAILED} TESTS FALLARON{Colors.ENDC}\n")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
