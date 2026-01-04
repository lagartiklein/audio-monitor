#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🧪 TEST SUITE SIMPLIFICADO: Flujo, Datos y Persistencia
Solo dependencias básicas
"""

import sys
import os
import json
import time
from pathlib import Path

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

TESTS_PASSED = 0
TESTS_FAILED = 0

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
# TESTS
# ============================================================================

def test_device_registry_exists():
    print_header("TEST 1: device_registry Existe")
    
    devices_file = Path("config/devices.json")
    if devices_file.exists():
        print_test("Archivo config/devices.json existe", "PASS")
        return True
    else:
        print_test("Archivo config/devices.json NO existe", "FAIL")
        return False

def test_device_registry_json_valido():
    print_header("TEST 2: device_registry JSON Válido")
    
    try:
        devices_file = Path("config/devices.json")
        with open(devices_file, 'r') as f:
            devices = json.load(f)
        print_test("✅ config/devices.json es JSON válido", "PASS")
        print_info(f"Total dispositivos registrados: {len(devices)}")
        return True
    except json.JSONDecodeError as e:
        print_test(f"❌ JSON inválido: {e}", "FAIL")
        return False
    except Exception as e:
        print_test(f"❌ Error: {e}", "FAIL")
        return False

def test_estructura_dispositivos():
    print_header("TEST 3: Estructura de Dispositivos")
    
    try:
        devices_file = Path("config/devices.json")
        with open(devices_file, 'r') as f:
            devices = json.load(f)
        
        required_fields = ['uuid', 'type', 'first_seen', 'last_seen']
        errors = 0
        
        for uuid, device in devices.items():
            for field in required_fields:
                if field not in device:
                    errors += 1
                    print_error(f"Campo '{field}' faltante en {uuid[:12]}")
        
        if errors == 0:
            print_test("✅ Todos los dispositivos tienen campos requeridos", "PASS")
            return True
        else:
            print_test(f"❌ {errors} errores encontrados", "FAIL")
            return False
    except Exception as e:
        print_test(f"❌ Error: {e}", "FAIL")
        return False

def test_unicidad_uuids():
    print_header("TEST 4: Unicidad de UUIDs")
    
    try:
        devices_file = Path("config/devices.json")
        with open(devices_file, 'r') as f:
            devices = json.load(f)
        
        uuids = list(devices.keys())
        unique_uuids = set(uuids)
        
        if len(uuids) == len(unique_uuids):
            print_test(f"✅ {len(unique_uuids)} UUIDs únicos - SIN DUPLICADOS", "PASS")
            return True
        else:
            duplicates = len(uuids) - len(unique_uuids)
            print_test(f"❌ {duplicates} UUIDs duplicados", "FAIL")
            return False
    except Exception as e:
        print_test(f"❌ Error: {e}", "FAIL")
        return False

def test_dispositivos_web():
    print_header("TEST 5: Dispositivos Web Registrados")
    
    try:
        devices_file = Path("config/devices.json")
        with open(devices_file, 'r') as f:
            devices = json.load(f)
        
        web_devices = [d for d in devices.values() if d.get('type') == 'web']
        
        if len(web_devices) > 0:
            print_test(f"✅ {len(web_devices)} web clients registrados", "PASS")
            
            # Mostrar algunos
            for device in web_devices[:3]:
                name = device.get('name', 'sin-nombre')
                reconnections = device.get('reconnections', 0)
                print_info(f"{name} - reconexiones: {reconnections}")
            
            return True
        else:
            print_test("❌ No hay web clients registrados", "FAIL")
            return False
    except Exception as e:
        print_test(f"❌ Error: {e}", "FAIL")
        return False

def test_dispositivos_android():
    print_header("TEST 6: Dispositivos Android Registrados")
    
    try:
        devices_file = Path("config/devices.json")
        with open(devices_file, 'r') as f:
            devices = json.load(f)
        
        android_devices = [d for d in devices.values() if d.get('type') == 'android']
        
        print_test(f"Android clients: {len(android_devices)}", "PASS")
        
        if len(android_devices) > 0:
            for device in android_devices[:3]:
                name = device.get('name', 'sin-nombre')
                active = device.get('active', False)
                print_info(f"{name} - activo: {active}")
        
        return True
    except Exception as e:
        print_test(f"❌ Error: {e}", "FAIL")
        return False

def test_persistencia_configuracion():
    print_header("TEST 7: Persistencia de Configuración")
    
    try:
        devices_file = Path("config/devices.json")
        with open(devices_file, 'r') as f:
            devices = json.load(f)
        
        devices_with_config = 0
        sample_configs = 0
        
        for uuid, device in devices.items():
            config = device.get('configuration', {})
            if config and len(config) > 0:
                devices_with_config += 1
                
                if sample_configs < 3:
                    channels = config.get('channels', [])
                    print_info(f"Config guardada: {len(channels)} canales")
                    sample_configs += 1
        
        if devices_with_config > 0:
            print_test(f"✅ {devices_with_config} dispositivos con configuración guardada", "PASS")
            return True
        else:
            print_test("⚠️ No hay dispositivos con configuración (puede ser normal)", "PASS")
            return True
    except Exception as e:
        print_test(f"❌ Error: {e}", "FAIL")
        return False

def test_timestamps_validos():
    print_header("TEST 8: Timestamps Válidos")
    
    try:
        devices_file = Path("config/devices.json")
        with open(devices_file, 'r') as f:
            devices = json.load(f)
        
        errors = 0
        current_time = time.time()
        
        for uuid, device in devices.items():
            first_seen = device.get('first_seen', 0)
            last_seen = device.get('last_seen', 0)
            
            # Verificar que sean números
            if not isinstance(first_seen, (int, float)):
                errors += 1
                continue
            
            # Verificar que sean timestamps razonables (últimos 30 días)
            if first_seen > current_time or first_seen < current_time - 30*24*3600:
                errors += 1
                continue
            
            # Verificar que last_seen >= first_seen
            if last_seen < first_seen:
                errors += 1
        
        if errors == 0:
            print_test("✅ Todos los timestamps son válidos", "PASS")
            return True
        else:
            print_test(f"❌ {errors} dispositivos con timestamps inválidos", "FAIL")
            return False
    except Exception as e:
        print_test(f"❌ Error: {e}", "FAIL")
        return False

def test_reconexiones():
    print_header("TEST 9: Contador de Reconexiones")
    
    try:
        devices_file = Path("config/devices.json")
        with open(devices_file, 'r') as f:
            devices = json.load(f)
        
        devices_with_reconnections = 0
        max_reconnections = 0
        
        for uuid, device in devices.items():
            reconnections = device.get('reconnections', 0)
            if reconnections > 0:
                devices_with_reconnections += 1
                max_reconnections = max(max_reconnections, reconnections)
        
        if devices_with_reconnections > 0:
            print_test(f"✅ {devices_with_reconnections} dispositivos se han reconectado", "PASS")
            print_info(f"Máximo de reconexiones: {max_reconnections}")
            return True
        else:
            print_test("⚠️ No hay dispositivos con reconexiones (puede ser normal)", "PASS")
            return True
    except Exception as e:
        print_test(f"❌ Error: {e}", "FAIL")
        return False

def test_dispositivos_activos():
    print_header("TEST 10: Estado Activo de Dispositivos")
    
    try:
        devices_file = Path("config/devices.json")
        with open(devices_file, 'r') as f:
            devices = json.load(f)
        
        active_devices = sum(1 for d in devices.values() if d.get('active'))
        total_devices = len(devices)
        
        print_test(f"Dispositivos activos: {active_devices}/{total_devices}", "PASS")
        
        # Mostrar resumen por tipo
        active_web = sum(1 for d in devices.values() if d.get('active') and d.get('type') == 'web')
        active_android = sum(1 for d in devices.values() if d.get('active') and d.get('type') == 'android')
        
        print_info(f"Web activos: {active_web}")
        print_info(f"Android activos: {active_android}")
        
        return True
    except Exception as e:
        print_test(f"❌ Error: {e}", "FAIL")
        return False

def test_integridad_global():
    print_header("TEST 11: Integridad Global")
    
    try:
        devices_file = Path("config/devices.json")
        with open(devices_file, 'r') as f:
            devices = json.load(f)
        
        # Verificar que cada UUID en clave existe en value
        mismatches = 0
        for key_uuid, device in devices.items():
            if device.get('uuid') != key_uuid:
                mismatches += 1
        
        if mismatches == 0:
            print_test("✅ UUID keys coinciden con uuid en values", "PASS")
        else:
            print_test(f"❌ {mismatches} UUID mismatches", "FAIL")
            return False
        
        # Verificar que no hay campos nulos inesperados
        null_fields = 0
        for uuid, device in devices.items():
            if device.get('type') is None:
                null_fields += 1
        
        if null_fields == 0:
            print_test("✅ No hay campos críticos nulos", "PASS")
            return True
        else:
            print_test(f"❌ {null_fields} campos críticos nulos", "FAIL")
            return False
    except Exception as e:
        print_test(f"❌ Error: {e}", "FAIL")
        return False

def test_resumen_estadistico():
    print_header("TEST 12: Resumen Estadístico")
    
    try:
        devices_file = Path("config/devices.json")
        with open(devices_file, 'r') as f:
            devices = json.load(f)
        
        total = len(devices)
        web = sum(1 for d in devices.values() if d.get('type') == 'web')
        android = sum(1 for d in devices.values() if d.get('type') == 'android')
        active = sum(1 for d in devices.values() if d.get('active'))
        with_config = sum(1 for d in devices.values() if d.get('configuration'))
        
        print_info(f"Total dispositivos: {total}")
        print_info(f"  - Web: {web} ({web/total*100:.1f}%)")
        print_info(f"  - Android: {android} ({android/total*100:.1f}%)")
        print_info(f"Dispositivos activos: {active} ({active/total*100:.1f}%)")
        print_info(f"Con configuración: {with_config} ({with_config/total*100:.1f}%)")
        
        print_test("✅ Estadísticas recopiladas", "PASS")
        return True
    except Exception as e:
        print_test(f"❌ Error: {e}", "FAIL")
        return False

# ============================================================================
# MAIN
# ============================================================================

def main():
    print(f"""
{Colors.BOLD}{Colors.OKBLUE}
╔══════════════════════════════════════════════════════════════════════╗
║                    🧪 TEST SUITE - PERSISTENCIA                      ║
║              Verificación de Datos en device_registry               ║
╚══════════════════════════════════════════════════════════════════════╝
{Colors.ENDC}
""")
    
    tests = [
        ("device_registry existe", test_device_registry_exists),
        ("JSON válido", test_device_registry_json_valido),
        ("Estructura dispositivos", test_estructura_dispositivos),
        ("Unicidad de UUIDs", test_unicidad_uuids),
        ("Dispositivos Web", test_dispositivos_web),
        ("Dispositivos Android", test_dispositivos_android),
        ("Persistencia configuración", test_persistencia_configuracion),
        ("Timestamps válidos", test_timestamps_validos),
        ("Contador reconexiones", test_reconexiones),
        ("Dispositivos activos", test_dispositivos_activos),
        ("Integridad global", test_integridad_global),
        ("Resumen estadístico", test_resumen_estadistico),
    ]
    
    for name, test_func in tests:
        try:
            test_func()
            time.sleep(0.5)
        except Exception as e:
            print_error(f"Excepción en {name}: {e}")
            import traceback
            traceback.print_exc()
    
    # Resumen
    print_header("📊 RESUMEN")
    
    total = TESTS_PASSED + TESTS_FAILED
    percentage = (TESTS_PASSED / total * 100) if total > 0 else 0
    
    print(f"  ✅ Tests pasados: {Colors.OKGREEN}{TESTS_PASSED}{Colors.ENDC}")
    print(f"  ❌ Tests fallidos: {Colors.FAIL}{TESTS_FAILED}{Colors.ENDC}")
    print(f"  📊 Total: {total}")
    print(f"  📈 Éxito: {Colors.OKGREEN}{percentage:.1f}%{Colors.ENDC}")
    
    print()
    
    if TESTS_FAILED == 0 and TESTS_PASSED > 0:
        print(f"{Colors.OKGREEN}{Colors.BOLD}✅ TODOS LOS TESTS PASARON ✅{Colors.ENDC}")
        print(f"{Colors.OKGREEN}   Persistencia y datos VERIFICADOS{Colors.ENDC}\n")
        return 0
    else:
        print(f"{Colors.FAIL}{Colors.BOLD}❌ {TESTS_FAILED} TESTS FALLARON{Colors.ENDC}\n")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
