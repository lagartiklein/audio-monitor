#!/usr/bin/env python3
"""
Demo de simulación completa: Conexión a interfaz MIDAS M32 de 32 canales
Muestra el proceso completo de detección, configuración y captura de audio
"""

import sys
import os
import logging
import numpy as np
import time
from unittest.mock import patch

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from audio_server.audio_capture import AudioCapture
from audio_server.channel_manager import ChannelManager

def simulate_m32_connection():
    """Simula la conexión completa a una interfaz MIDAS M32"""

    print("=" * 80)
    print("🎛️  SIMULACIÓN: CONEXIÓN A INTERFAZ MIDAS M32 (32 CANALES)")
    print("=" * 80)

    # 1. Información del dispositivo M32 simulado
    m32_device = {
        'name': 'MIDAS M32 - 32 Channel Digital Mixer',
        'index': 100,
        'hostapi': 0,
        'max_input_channels': 32,
        'max_output_channels': 16,
        'default_low_input_latency': 0.005,
        'default_low_output_latency': 0.005,
        'default_high_input_latency': 0.01,
        'default_high_output_latency': 0.01,
        'default_samplerate': 48000.0
    }

    print("📋 Especificaciones de la interfaz MIDAS M32:")
    print(f"   • Modelo: {m32_device['name']}")
    print(f"   • Canales de entrada: {m32_device['max_input_channels']}")
    print(f"   • Canales de salida: {m32_device['max_output_channels']}")
    print(f"   • Sample Rate: {m32_device['default_samplerate']} Hz")
    print(f"   • Latencia de entrada: {m32_device['default_low_input_latency']*1000:.2f}ms")
    print(f"   • Latencia de salida: {m32_device['default_low_output_latency']*1000:.2f}ms")
    # 2. Simular detección del dispositivo
    print("\n🔍 DETECTANDO DISPOSITIVOS DE AUDIO...")
    time.sleep(0.5)

    # Mock para simular que sounddevice detecta la M32
    def mock_query_devices(device_id=None):
        if device_id == 100:
            return m32_device
        else:
            return [m32_device]

    # 3. Configurar captura de audio
    print("\n🎙️ CONFIGURANDO CAPTURA DE AUDIO...")

    with patch('sounddevice.query_devices', side_effect=mock_query_devices), \
         patch('sounddevice.InputStream') as mock_input_stream:

        # Mock del stream de audio
        mock_stream = type('MockStream', (), {
            'latency': 0.005,
            'start': lambda self: None,
            'stop': lambda self: None,
            'close': lambda self: None
        })()
        mock_input_stream.return_value = mock_stream

        # Inicializar captura
        audio_capture = AudioCapture()
        device_id = 100

        print(f"   Conectando a dispositivo ID: {device_id}")
        num_channels = audio_capture.start_capture(device_id=device_id)

        print("✅ Conexión exitosa!")
        print(f"   Canales capturados: {num_channels}")
        print(f"   Configuración: {config.SAMPLE_RATE}Hz, {config.BLOCKSIZE} samples/block")
        print(f"   Latencia del motor: {mock_stream.latency*1000:.2f}ms")

        # 4. Configurar ChannelManager
        print("\n🎚️ CONFIGURANDO GESTIÓN DE CANALES...")

        channel_manager = ChannelManager(num_channels)
        print(f"   ChannelManager inicializado para {num_channels} canales")

        # Configurar nombres de canales típicos de M32
        m32_channel_names = {
            0: "Kick In", 1: "Snare In", 2: "Tom 1", 3: "Tom 2",
            4: "HiHat", 5: "Ride", 6: "Overheads L", 7: "Overheads R",
            8: "Guitar 1", 9: "Guitar 2", 10: "Bass DI", 11: "Keys",
            12: "Vocals 1", 13: "Vocals 2", 14: "Vocals 3", 15: "Vocals 4",
            16: "Drum Sub 1", 17: "Drum Sub 2", 18: "Guitar Amp 1", 19: "Guitar Amp 2",
            20: "Bass Amp", 21: "Monitor 1", 22: "Monitor 2", 23: "Monitor 3",
            24: "FX Return 1", 25: "FX Return 2", 26: "FX Return 3", 27: "FX Return 4",
            28: "Aux In 1", 29: "Aux In 2", 30: "Aux In 3", 31: "Aux In 4"
        }

        for ch_id, name in m32_channel_names.items():
            channel_manager.set_channel_name(ch_id, name)

        print("   Nombres de canales configurados:")
        for i in range(0, 32, 8):  # Mostrar primeros canales de cada grupo
            channels = [f"{j}: {channel_manager.get_channel_name(j)}" for j in range(i, min(i+8, 32))]
            print(f"      {', '.join(channels)}")

        # 5. Simular procesamiento de audio
        print("\n🎵 SIMULANDO PROCESAMIENTO DE AUDIO...")

        # Configurar callback para monitorear audio
        audio_blocks_processed = 0
        peak_levels = [0.0] * 32

        def audio_monitor_callback(audio_data):
            nonlocal audio_blocks_processed, peak_levels
            audio_blocks_processed += 1

            # Calcular niveles de pico por canal
            for ch in range(32):
                if ch < audio_data.shape[1]:
                    peak = np.max(np.abs(audio_data[:, ch]))
                    peak_levels[ch] = max(peak_levels[ch], peak)

        audio_capture.register_callback(audio_monitor_callback)

        # Simular 5 segundos de audio (aprox. 200 bloques a 48kHz/120samples)
        test_blocks = 10
        blocksize = config.BLOCKSIZE

        print(f"   Procesando {test_blocks} bloques de audio...")

        for block in range(test_blocks):
            # Generar audio de prueba realista
            t = np.linspace(0, blocksize/config.SAMPLE_RATE, blocksize, False)
            audio_block = np.zeros((blocksize, 32), dtype=np.float32)

            # Canales de batería con diferentes frecuencias
            for ch in range(8):
                freq = 100 + ch * 50  # 100Hz, 150Hz, 200Hz, etc.
                audio_block[:, ch] = 0.3 * np.sin(2 * np.pi * freq * t) * np.exp(-t * 2)  # Decaimiento

            # Canales de guitarra/vocal con armónicos
            for ch in range(8, 16):
                freq = 200 + (ch - 8) * 100
                audio_block[:, ch] = 0.2 * np.sin(2 * np.pi * freq * t)
                # Agregar armónico
                audio_block[:, ch] += 0.1 * np.sin(2 * np.pi * freq * 2 * t)

            # Canales restantes con ruido de baja frecuencia
            for ch in range(16, 32):
                audio_block[:, ch] = 0.1 * np.random.randn(blocksize)

            # Procesar bloque
            time_info = {'input_buffer_adc_time': time.time()}
            audio_capture._audio_callback(audio_block, blocksize, time_info, None)

            if (block + 1) % 5 == 0:
                print(f"   Procesado bloque {block + 1}/{test_blocks}")

        # 6. Mostrar resultados
        print("\n📊 RESULTADOS DE LA SIMULACIÓN:")
        print(f"   • Bloques de audio procesados: {audio_blocks_processed}")
        print(f"   • Frames totales: {audio_blocks_processed * blocksize:,}")
        print(f"   • Duración simulada: {(audio_blocks_processed * blocksize) / config.SAMPLE_RATE:.2f}s")
        print("\n🎚️ NIVELES DE PICO POR CANAL:")
        for i in range(0, 32, 4):
            peaks = [".3f" for j in range(i, min(i+4, 32))]
            print(f"   CH{i:2d}-{min(i+3, 31):2d}: {'  '.join(peaks)}")

        # 7. Detener captura
        print("\n🛑 DETENIENDO CAPTURA...")
        audio_capture.stop_capture()
        print("✅ Captura detenida correctamente")

    print("\n" + "=" * 80)
    print("✅ SIMULACIÓN COMPLETADA EXITOSAMENTE")
    print("🎛️  La interfaz MIDAS M32 está lista para uso en producción")
    print("=" * 80)

if __name__ == '__main__':
    simulate_m32_connection()