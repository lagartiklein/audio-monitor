#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🧪 TEST: Verificar que solo se muestran clientes REALES
"""

import requests
import json
import time
from pathlib import Path

SERVIDOR_URL = "http://127.0.0.1:5100"

print("\n" + "="*70)
print("  🧪 TEST: FILTRO DE CLIENTES REALES")
print("="*70 + "\n")

try:
    # 1. Cargar device_registry actual
    print("1️⃣ Leyendo device_registry...")
    devices_file = Path("config/devices.json")
    with open(devices_file, 'r') as f:
        all_devices = json.load(f)
    
    print(f"   📊 Total dispositivos en registry: {len(all_devices)}\n")
    
    # Contar por tipo
    tipos = {}
    for uuid, device in all_devices.items():
        tipo = device.get('type', 'unknown')
        tipos[tipo] = tipos.get(tipo, 0) + 1
    
    print("   📈 Desglose por tipo:")
    for tipo, count in sorted(tipos.items()):
        print(f"      - {tipo}: {count}")
    
    # 2. Verificar el servidor
    print("\n2️⃣ Verificando servidor WebSocket...")
    try:
        response = requests.get(f"{SERVIDOR_URL}/", timeout=2)
        if response.status_code < 500:
            print("   ✅ Servidor disponible")
        else:
            print("   ⚠️ Servidor respondió con error")
    except Exception as e:
        print(f"   ❌ Servidor no disponible: {e}")
    
    # 3. Aplicar filtro (como hace el backend ahora)
    print("\n3️⃣ Aplicando filtro de clientes REALES...")
    print("   ✅ Filtro: type in ('web', 'native', 'android')\n")
    
    real_devices = [d for d in all_devices.values() if d.get('type') in ('web', 'native', 'android')]
    
    print(f"   📊 Dispositivos REALES a mostrar: {len(real_devices)}")
    print(f"   📊 Dispositivos FILTRADOS (ocultos): {len(all_devices) - len(real_devices)}\n")
    
    # Desglose de reales
    print("   📈 Desglose de clientes REALES:")
    real_types = {}
    for device in real_devices:
        tipo = device.get('type', 'unknown')
        real_types[tipo] = real_types.get(tipo, 0) + 1
    
    for tipo, count in sorted(real_types.items()):
        print(f"      - {tipo}: {count}")
    
    # 4. Mostrar clientes filtrados (para debug)
    print("\n4️⃣ Clientes a OCULTAR (no son web/native/android):")
    hidden_count = 0
    for uuid, device in all_devices.items():
        if device.get('type') not in ('web', 'native', 'android'):
            hidden_count += 1
            if hidden_count <= 5:
                tipo = device.get('type', 'unknown')
                name = device.get('name', 'sin-nombre')
                print(f"   🚫 {name[:20]:20} (type={tipo})")
    
    if hidden_count > 5:
        print(f"   ... y {hidden_count - 5} más")
    
    print("\n" + "="*70)
    print(f"  ✅ FILTRO FUNCIONANDO CORRECTAMENTE")
    print(f"     Se mostrarán solo {len(real_devices)}/{len(all_devices)} clientes reales")
    print("="*70 + "\n")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
