#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test simplificado del mapeo de canales (sin emojis para Windows)
"""
import sys
sys.path.insert(0, '.')

import config
from audio_server.channel_manager import ChannelManager

print("="*60)
print("TEST: Mapeo de canales después de correcciones")
print("="*60)

# Test 1: Inicializar ChannelManager
try:
    cm = ChannelManager(48)
    print("[OK] ChannelManager inicializado con 48 canales")
except Exception as e:
    print(f"[FAIL] Error inicializando: {e}")
    sys.exit(1)

# Test 2: Mapear dispositivo servidor
try:
    mapping = cm.register_device_to_channels("audio-server-device", 8)
    print(f"[OK] Servidor mapeado a canales {mapping['start_channel']}-{mapping['start_channel'] + mapping['num_channels'] - 1}")
    assert mapping['operacional'] == True
except Exception as e:
    print(f"[FAIL] Error mapeando servidor: {e}")
    sys.exit(1)

# Test 3: Mapear dispositivo Android
try:
    mapping2 = cm.register_device_to_channels("android-uuid-123", 16)
    print(f"[OK] Android mapeado a canales {mapping2['start_channel']}-{mapping2['start_channel'] + mapping2['num_channels'] - 1}")
    assert mapping2['operacional'] == True
except Exception as e:
    print(f"[FAIL] Error mapeando Android: {e}")
    sys.exit(1)

# Test 4: Verificar canales operacionales
try:
    op_ch = cm.get_operational_channels()
    print(f"[OK] Canales operacionales: {len(op_ch)} de 48 ({list(op_ch)[:10]}...)")
    assert len(op_ch) == 24  # 8 + 16
except Exception as e:
    print(f"[FAIL] Error obteniendo canales operacionales: {e}")
    sys.exit(1)

print("="*60)
print("PASS: Todo funciona correctamente")
print("="*60)
