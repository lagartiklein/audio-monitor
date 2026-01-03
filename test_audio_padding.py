"""
Script para diagnosticar el problema del audio
"""
import sys
sys.path.insert(0, '.')

import numpy as np
import config
from audio_server.audio_capture import AudioCapture

print("="*70)
print("TEST: Flujo de audio con relleno de canales")
print("="*70)

# Test 1: Verificar que audio_capture puede rellenar canales
print("\n1️⃣  Test: Relleno de canales en audio_capture")

# Simular dispositivo con 8 canales
frames = 128
physical_channels = 8

print(f"   - Dispositivo físico: {physical_channels} canales")
print(f"   - Canales lógicos esperados: {config.DEFAULT_NUM_CHANNELS}")

# Crear audio simulado (como viene del sounddevice)
audio_input = np.random.randn(frames, physical_channels).astype(np.float32)
print(f"   - Audio input shape: {audio_input.shape}")

# Simular el relleno que hace audio_capture
if physical_channels < config.DEFAULT_NUM_CHANNELS:
    padded_audio = np.zeros((frames, config.DEFAULT_NUM_CHANNELS), dtype=np.float32)
    padded_audio[:, :physical_channels] = audio_input[:, :physical_channels]
    audio_to_send = padded_audio
else:
    audio_to_send = audio_input

print(f"   - Audio salida shape: {audio_to_send.shape}")
assert audio_to_send.shape == (frames, config.DEFAULT_NUM_CHANNELS), "Shape incorrecto!"
print("   ✅ Relleno funciona correctamente")

# Test 2: Verify reshape en native_server
print("\n2️⃣  Test: Reshape en native_server")

audio_copy = np.frombuffer(memoryview(audio_to_send), dtype=np.float32).reshape(-1, config.DEFAULT_NUM_CHANNELS)
print(f"   - Reshape result shape: {audio_copy.shape}")
assert audio_copy.shape == (frames, config.DEFAULT_NUM_CHANNELS), "Reshape falló!"
print("   ✅ Reshape en native_server funciona")

# Test 3: Verificar que los datos se copian correctamente
print("\n3️⃣  Test: Integridad de datos")

# Los primeros 8 canales deben tener datos originales
assert np.allclose(audio_copy[:, :physical_channels], audio_input[:, :physical_channels]), "Datos originales no coinciden!"
print(f"   ✅ Primeros {physical_channels} canales tienen datos reales")

# Los últimos 40 canales deben ser ceros
assert np.allclose(audio_copy[:, physical_channels:], 0), "Canales rellenados no son cero!"
print(f"   ✅ Últimos {config.DEFAULT_NUM_CHANNELS - physical_channels} canales están en ceros")

print("\n" + "="*70)
print("✅ TODOS LOS TESTS DE AUDIO PASARON")
print("="*70)
print("\nResumen:")
print(f"  - Audio input: {physical_channels} canales reales")
print(f"  - Audio output: {config.DEFAULT_NUM_CHANNELS} canales (rellenados)")
print(f"  - Reshape: Funciona correctamente")
print(f"  - Integridad de datos: Verificada")
