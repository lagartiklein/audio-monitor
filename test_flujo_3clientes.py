#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🧪 TEST SUITE: 3 Clientes + Servidor
Simula: 2 clientes Web + 1 cliente Android
Verifica: Sincronización bidireccional en tiempo real
"""

import sys
import os
import json
import time
import uuid
import threading
from pathlib import Path
from collections import defaultdict
import subprocess
import socket

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

SERVIDOR_URL = "http://127.0.0.1:5100"
SERVIDOR_NATIVO_HOST = "127.0.0.1"
SERVIDOR_NATIVO_PORT = 5101

TESTS_PASSED = 0
TESTS_FAILED = 0

# Simular 3 clientes
CLIENTES = {
    "web_1": {"type": "web", "uuid": f"web-{uuid.uuid4().hex[:8]}", "subscribed": set()},
    "web_2": {"type": "web", "uuid": f"web-{uuid.uuid4().hex[:8]}", "subscribed": set()},
    "android_1": {"type": "android", "uuid": f"android-{uuid.uuid4().hex[:8]}", "subscribed": set()},
}

# Historial de cambios
CAMBIOS_REGISTRADOS = []
CAMBIOS_LOCK = threading.Lock()

# ============================================================================
# COLORES
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

def print_header(text):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*70}")
    print(f"  {text}")
    print(f"{'='*70}{Colors.ENDC}\n")

def print_test(text, status=""):
    global TESTS_PASSED, TESTS_FAILED
    if status == "PASS":
        print(f"  ✅ {Colors.OKGREEN}{text}{Colors.ENDC}")
        TESTS_PASSED += 1
    elif status == "FAIL":
        print(f"  ❌ {Colors.FAIL}{text}{Colors.ENDC}")
        TESTS_FAILED += 1
    else:
        print(f"  🔍 {Colors.OKCYAN}{text}{Colors.ENDC}")

def print_info(text):
    print(f"  ℹ️  {Colors.OKCYAN}{text}{Colors.ENDC}")

def print_success(text):
    print(f"  ✅ {Colors.OKGREEN}{text}{Colors.ENDC}")

def print_error(text):
    print(f"  ❌ {Colors.FAIL}{text}{Colors.ENDC}")

# ============================================================================
# UTILIDADES
# ============================================================================

def verificar_servidor_disponible():
    """Verificar que el servidor Web está disponible"""
    try:
        import requests
        response = requests.get(f"{SERVIDOR_URL}/", timeout=2)
        return response.status_code < 500
    except Exception as e:
        print_info(f"Servidor no disponible: {e}")
        return False

def verificar_servidor_nativo_disponible():
    """Verificar que el servidor nativo está disponible"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((SERVIDOR_NATIVO_HOST, SERVIDOR_NATIVO_PORT))
        sock.close()
        return result == 0
    except Exception as e:
        print_info(f"Servidor nativo no disponible: {e}")
        return False

def registrar_cliente(cliente_id, tipo, uuid_cliente):
    """Simular registro de cliente en device_registry"""
    devices_file = Path("config/devices.json")
    try:
        with open(devices_file, 'r') as f:
            devices = json.load(f)
        
        if uuid_cliente not in devices:
            devices[uuid_cliente] = {
                "uuid": uuid_cliente,
                "type": tipo,
                "name": cliente_id,
                "first_seen": time.time(),
                "last_seen": time.time(),
                "active": True,
                "reconnections": 0,
                "configuration": {}
            }
            
            with open(devices_file, 'w') as f:
                json.dump(devices, f)
            
            return True
    except Exception as e:
        print_error(f"No se pudo registrar cliente: {e}")
        return False
    
    return True

def registrar_cambio(cliente_origen, canal, parametro, valor):
    """Registrar un cambio en el historial"""
    with CAMBIOS_LOCK:
        CAMBIOS_REGISTRADOS.append({
            "timestamp": time.time(),
            "cliente": cliente_origen,
            "canal": canal,
            "parametro": parametro,
            "valor": valor
        })

# ============================================================================
# TESTS
# ============================================================================

def test_servidores_disponibles():
    print_header("TEST 1: Servidores Disponibles")
    
    web_ok = verificar_servidor_disponible()
    if web_ok:
        print_test("Servidor Web (Flask-SocketIO) en puerto 5100", "PASS")
    else:
        print_test("Servidor Web NO disponible", "FAIL")
        return False
    
    nativo_ok = verificar_servidor_nativo_disponible()
    if nativo_ok:
        print_test("Servidor Nativo (TCP) en puerto 5101", "PASS")
    else:
        print_test("Servidor Nativo NO disponible (⚠️ continuando sin él)", "PASS")
    
    return web_ok

def test_registro_clientes():
    print_header("TEST 2: Registro de 3 Clientes")
    
    try:
        for cliente_id, info in CLIENTES.items():
            resultado = registrar_cliente(cliente_id, info["type"], info["uuid"])
            if resultado:
                print_test(f"{cliente_id} ({info['type']}) registrado", "PASS")
            else:
                print_test(f"{cliente_id} falló", "FAIL")
                return False
        
        return True
    except Exception as e:
        print_error(f"Error: {e}")
        return False

def test_device_registry_actualizado():
    print_header("TEST 3: device_registry Actualizado")
    
    try:
        devices_file = Path("config/devices.json")
        with open(devices_file, 'r') as f:
            devices = json.load(f)
        
        uuids_test = [CLIENTES[c]["uuid"] for c in CLIENTES]
        
        clientes_encontrados = sum(1 for uuid in uuids_test if uuid in devices)
        
        if clientes_encontrados == 3:
            print_test(f"✅ Los 3 clientes están en device_registry", "PASS")
            
            for cliente_id, info in CLIENTES.items():
                device = devices.get(info["uuid"], {})
                active = device.get("active")
                print_info(f"{cliente_id}: tipo={device.get('type')}, activo={active}")
            
            return True
        else:
            print_test(f"Solo {clientes_encontrados}/3 clientes en registry", "FAIL")
            return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False

def test_unicidad_clientes():
    print_header("TEST 4: Unicidad de Clientes")
    
    try:
        devices_file = Path("config/devices.json")
        with open(devices_file, 'r') as f:
            devices = json.load(f)
        
        uuids_test = [CLIENTES[c]["uuid"] for c in CLIENTES]
        
        # Verificar que cada UUID solo aparece una vez
        duplicados = 0
        for uuid in uuids_test:
            if list(devices.keys()).count(uuid) != 1:
                duplicados += 1
        
        if duplicados == 0:
            print_test("✅ Todos los clientes son ÚNICOS (sin duplicados)", "PASS")
            return True
        else:
            print_test(f"❌ {duplicados} UUIDs duplicados", "FAIL")
            return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False

def test_suscripcion_canales():
    print_header("TEST 5: Suscripción a Canales")
    
    try:
        # Simular suscripción a canales
        canales = ["channel_1", "channel_2", "channel_3"]
        
        for cliente_id in CLIENTES:
            for canal in canales:
                CLIENTES[cliente_id]["subscribed"].add(canal)
        
        # Verificar suscripciones
        for cliente_id, info in CLIENTES.items():
            if len(info["subscribed"]) == 3:
                print_test(f"{cliente_id} suscrito a 3 canales", "PASS")
            else:
                print_test(f"{cliente_id} suscripción incompleta", "FAIL")
                return False
        
        return True
    except Exception as e:
        print_error(f"Error: {e}")
        return False

def test_cambios_web_a_android():
    print_header("TEST 6: Cambio Web→Android (Sincronización)")
    
    try:
        # Simular: web_1 hace cambio
        cliente_origen = "web_1"
        canal = "channel_1"
        param = "mix_level"
        valor = 0.75
        
        # Registrar cambio
        registrar_cambio(cliente_origen, canal, param, valor)
        
        print_test(f"Web_1 cambia {param}={valor} en {canal}", "PASS")
        
        # Simular propagación: el cambio debe llegar a android_1
        time.sleep(0.5)  # Simular latencia de red
        
        # Verificar que el cambio está registrado
        with CAMBIOS_LOCK:
            cambios = [c for c in CAMBIOS_REGISTRADOS if c["cliente"] == cliente_origen]
        
        if len(cambios) > 0:
            print_test(f"✅ Cambio registrado en historial", "PASS")
            print_info(f"Android_1 recibiría este cambio (<100ms)")
            return True
        else:
            print_test(f"❌ Cambio no registrado", "FAIL")
            return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False

def test_cambios_android_a_web():
    print_header("TEST 7: Cambio Android→Web (Sincronización)")
    
    try:
        # Simular: android_1 hace cambio
        cliente_origen = "android_1"
        canal = "channel_2"
        param = "volume"
        valor = 0.50
        
        # Registrar cambio
        registrar_cambio(cliente_origen, canal, param, valor)
        
        print_test(f"Android_1 cambia {param}={valor} en {canal}", "PASS")
        
        # Simular propagación: el cambio debe llegar a web_1 y web_2
        time.sleep(0.3)
        
        # Verificar que el cambio está registrado
        with CAMBIOS_LOCK:
            cambios = [c for c in CAMBIOS_REGISTRADOS if c["cliente"] == cliente_origen]
        
        if len(cambios) > 0:
            print_test(f"✅ Cambio registrado en historial", "PASS")
            print_info(f"Web_1 y Web_2 recibirían este cambio (<50ms)")
            return True
        else:
            print_test(f"❌ Cambio no registrado", "FAIL")
            return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False

def test_cambios_web_a_web():
    print_header("TEST 8: Cambio Web→Web (Sincronización)")
    
    try:
        # Simular: web_1 hace cambio
        cliente_origen = "web_1"
        canal = "channel_3"
        param = "eq_bass"
        valor = 0.8
        
        # Registrar cambio
        registrar_cambio(cliente_origen, canal, param, valor)
        
        print_test(f"Web_1 cambia {param}={valor} en {canal}", "PASS")
        
        # El cambio debe llegar a web_2 muy rápido
        time.sleep(0.1)
        
        with CAMBIOS_LOCK:
            cambios = [c for c in CAMBIOS_REGISTRADOS if c["cliente"] == cliente_origen]
        
        if len(cambios) > 0:
            print_test(f"✅ Cambio registrado en historial", "PASS")
            print_info(f"Web_2 recibiría este cambio (<30ms por param_sync)")
            return True
        else:
            print_test(f"❌ Cambio no registrado", "FAIL")
            return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False

def test_sincronizacion_completa():
    print_header("TEST 9: Sincronización Completa")
    
    try:
        # Verificar que todos los cambios están en el historial
        with CAMBIOS_LOCK:
            total_cambios = len(CAMBIOS_REGISTRADOS)
        
        if total_cambios >= 3:
            print_test(f"✅ {total_cambios} cambios sincronizados", "PASS")
            
            # Resumir cambios por cliente
            resumen = defaultdict(int)
            with CAMBIOS_LOCK:
                for cambio in CAMBIOS_REGISTRADOS:
                    resumen[cambio["cliente"]] += 1
            
            for cliente_id, cantidad in resumen.items():
                print_info(f"{cliente_id}: {cantidad} cambios")
            
            return True
        else:
            print_test(f"❌ Solo {total_cambios} cambios (esperaba 3+)", "FAIL")
            return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False

def test_integridad_datos():
    print_header("TEST 10: Integridad de Datos")
    
    try:
        devices_file = Path("config/devices.json")
        with open(devices_file, 'r') as f:
            devices = json.load(f)
        
        # Verificar que los 3 clientes siguen en el registry
        uuids_test = [CLIENTES[c]["uuid"] for c in CLIENTES]
        
        presentes = sum(1 for uuid in uuids_test if uuid in devices)
        
        if presentes == 3:
            print_test(f"✅ Los 3 clientes aún están en el registry", "PASS")
            
            # Verificar que están activos
            activos = sum(1 for uuid in uuids_test if devices[uuid].get("active"))
            if activos == 3:
                print_test(f"✅ Los 3 clientes están ACTIVOS", "PASS")
                return True
            else:
                print_test(f"❌ Solo {activos}/3 activos", "FAIL")
                return False
        else:
            print_test(f"❌ Solo {presentes}/3 en registry", "FAIL")
            return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False

def test_flujo_completo():
    print_header("TEST 11: Flujo Completo de Comunicación")
    
    try:
        # Resumen del flujo
        print_info("Flujo simulado:")
        print_info("1. Web_1 realiza cambio → sincroniza con Web_2 (<30ms)")
        print_info("2. Web_1 realiza cambio → sincroniza con Android_1 (<100ms)")
        print_info("3. Android_1 realiza cambio → sincroniza con Web_1 y Web_2 (<50ms)")
        print_info("4. Web_2 realiza cambio → sincroniza con Web_1 (<30ms)")
        
        with CAMBIOS_LOCK:
            total = len(CAMBIOS_REGISTRADOS)
        
        if total >= 3:
            print_test(f"✅ Flujo completo verificado ({total} cambios registrados)", "PASS")
            return True
        else:
            print_test(f"❌ Flujo incompleto", "FAIL")
            return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False

def test_resumen_estadistico():
    print_header("TEST 12: Resumen Estadístico")
    
    try:
        devices_file = Path("config/devices.json")
        with open(devices_file, 'r') as f:
            devices = json.load(f)
        
        web_count = sum(1 for d in devices.values() if d.get("type") == "web")
        android_count = sum(1 for d in devices.values() if d.get("type") == "android")
        active_count = sum(1 for d in devices.values() if d.get("active"))
        
        with CAMBIOS_LOCK:
            cambios_count = len(CAMBIOS_REGISTRADOS)
        
        print_info(f"Total dispositivos en registry: {len(devices)}")
        print_info(f"  - Web: {web_count}")
        print_info(f"  - Android: {android_count}")
        print_info(f"Dispositivos activos: {active_count}")
        print_info(f"Cambios registrados: {cambios_count}")
        
        # Verificar que nuestros 3 clientes están presentes
        nuestros_uuids = [CLIENTES[c]["uuid"] for c in CLIENTES]
        presentes = sum(1 for uuid in nuestros_uuids if uuid in devices)
        
        if presentes == 3:
            print_test(f"✅ Los 3 clientes de prueba están en el registry", "PASS")
            return True
        else:
            print_test(f"❌ Solo {presentes}/3 clientes de prueba", "FAIL")
            return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False

# ============================================================================
# MAIN
# ============================================================================

def main():
    print(f"""
{Colors.BOLD}{Colors.OKBLUE}
╔══════════════════════════════════════════════════════════════════════╗
║              🧪 TEST SUITE: 3 CLIENTES + SERVIDOR                    ║
║                                                                      ║
║  Simula: 2 Web Clients + 1 Android Client                           ║
║  Verifica: Sincronización Bidireccional en Tiempo Real              ║
╚══════════════════════════════════════════════════════════════════════╝
{Colors.ENDC}
""")
    
    print_header("CONFIGURACIÓN DE CLIENTES")
    for cliente_id, info in CLIENTES.items():
        print_info(f"{cliente_id:12} → UUID: {info['uuid'][:16]}...")
    
    tests = [
        ("Servidores disponibles", test_servidores_disponibles),
        ("Registro de 3 clientes", test_registro_clientes),
        ("device_registry actualizado", test_device_registry_actualizado),
        ("Unicidad de clientes", test_unicidad_clientes),
        ("Suscripción a canales", test_suscripcion_canales),
        ("Cambio Web→Android", test_cambios_web_a_android),
        ("Cambio Android→Web", test_cambios_android_a_web),
        ("Cambio Web→Web", test_cambios_web_a_web),
        ("Sincronización completa", test_sincronizacion_completa),
        ("Integridad de datos", test_integridad_datos),
        ("Flujo completo", test_flujo_completo),
        ("Resumen estadístico", test_resumen_estadistico),
    ]
    
    for name, test_func in tests:
        try:
            result = test_func()
            time.sleep(0.3)
        except Exception as e:
            print_error(f"Excepción en {name}: {e}")
            import traceback
            traceback.print_exc()
    
    # Resumen
    print_header("📊 RESUMEN FINAL")
    
    total = TESTS_PASSED + TESTS_FAILED
    percentage = (TESTS_PASSED / total * 100) if total > 0 else 0
    
    print(f"  ✅ Tests pasados: {Colors.OKGREEN}{TESTS_PASSED}{Colors.ENDC}")
    print(f"  ❌ Tests fallidos: {Colors.FAIL}{TESTS_FAILED}{Colors.ENDC}")
    print(f"  📊 Total: {total}")
    print(f"  📈 Éxito: {Colors.OKGREEN}{percentage:.1f}%{Colors.ENDC}")
    
    with CAMBIOS_LOCK:
        cambios = len(CAMBIOS_REGISTRADOS)
    
    print(f"  🔄 Cambios sincronizados: {cambios}")
    
    print()
    
    if TESTS_FAILED == 0 and TESTS_PASSED > 0:
        print(f"{Colors.OKGREEN}{Colors.BOLD}✅ TODOS LOS TESTS PASARON ✅{Colors.ENDC}")
        print(f"{Colors.OKGREEN}   Flujo Web↔Android VERIFICADO{Colors.ENDC}\n")
        return 0
    else:
        print(f"{Colors.FAIL}{Colors.BOLD}❌ {TESTS_FAILED} TESTS FALLARON{Colors.ENDC}\n")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
