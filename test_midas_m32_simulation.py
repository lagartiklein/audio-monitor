#!/usr/bin/env python3
"""
Prueba de conexión simulada a interfaz MIDAS M32 de 32 canales
Simula la detección, configuración y captura de audio de una interfaz profesional
"""

import sys
import os
import logging
import numpy as np
import time
import unittest
from unittest.mock import Mock, patch, MagicMock

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from audio_server.audio_capture import AudioCapture
from audio_server.channel_manager import ChannelManager

class TestMIDAS_M32_Simulation(unittest.TestCase):
    """Pruebas de simulación de interfaz MIDAS M32"""

    def setUp(self):
        """Configurar entorno de test"""
        self.audio_capture = AudioCapture()

        # Simular dispositivo MIDAS M32 con 32 canales
        self.m32_device_info = {
            'name': 'MIDAS M32 - 32 Channel Digital Mixer',
            'index': 100,  # ID simulado
            'hostapi': 0,
            'max_input_channels': 32,
            'max_output_channels': 16,
            'default_low_input_latency': 0.005,  # Baja latencia típica de interfaces profesionales
            'default_low_output_latency': 0.005,
            'default_high_input_latency': 0.01,
            'default_high_output_latency': 0.01,
            'default_samplerate': 48000.0  # Sample rate típico de M32
        }

    def test_detect_m32_device(self):
        """Test: Detección de dispositivo MIDAS M32"""
        logger.info("Test: Deteccion de dispositivo MIDAS M32")

        # Simular que sounddevice detecta el dispositivo M32
        with patch('sounddevice.query_devices') as mock_query:
            mock_query.return_value = [self.m32_device_info]

            devices = mock_query()
            m32_device = None
            for device in devices:
                if 'MIDAS M32' in device.get('name', '') and device.get('max_input_channels', 0) >= 32:
                    m32_device = device
                    break

            self.assertIsNotNone(m32_device, "Debe detectar dispositivo M32")
            self.assertEqual(m32_device['max_input_channels'], 32)
            self.assertEqual(m32_device['name'], 'MIDAS M32 - 32 Channel Digital Mixer')

        logger.info("OK: Dispositivo M32 detectado correctamente")

    @patch('sounddevice.query_devices')
    @patch('sounddevice.InputStream')
    def test_configure_m32_capture(self, mock_input_stream, mock_query_devices):
        """Test: Configuración de captura para M32"""
        logger.info("Test: Configuracion de captura para M32")

        # Configurar mocks para que retornen el dispositivo M32
        def mock_query(device_id=None):
            if device_id == 100:
                return self.m32_device_info
            else:
                return [self.m32_device_info]

        mock_query_devices.side_effect = mock_query

        # Mock del stream
        mock_stream = Mock()
        mock_stream.latency = 0.005  # 5ms latencia
        mock_input_stream.return_value = mock_stream

        # Intentar iniciar captura con el dispositivo M32
        device_id = 100  # ID del dispositivo simulado
        num_channels = self.audio_capture.start_capture(device_id=device_id)

        # Verificar que se configuró correctamente
        self.assertEqual(num_channels, 32, "Debe capturar 32 canales")

        # Verificar que InputStream se llamó con los parámetros correctos
        mock_input_stream.assert_called_once()
        call_args = mock_input_stream.call_args
        self.assertEqual(call_args[1]['device'], device_id)
        self.assertEqual(call_args[1]['channels'], 32)
        self.assertEqual(call_args[1]['samplerate'], config.SAMPLE_RATE)
        self.assertEqual(call_args[1]['blocksize'], config.BLOCKSIZE)
        self.assertEqual(call_args[1]['dtype'], 'float32')
        self.assertEqual(call_args[1]['latency'], 'low')

        # Verificar que el stream se inició
        mock_stream.start.assert_called_once()

        logger.info("OK: Captura M32 configurada correctamente")

    def test_m32_channel_manager_integration(self):
        """Test: Integración con ChannelManager para 32 canales"""
        logger.info("Test: Integracion con ChannelManager para 32 canales")

        # Crear ChannelManager con 32 canales
        channel_manager = ChannelManager(32)

        # Verificar configuración inicial
        self.assertEqual(channel_manager.num_channels, 32)

        # Verificar que puede manejar 32 canales (nombres se generan dinámicamente)
        for i in range(32):
            name = channel_manager.get_channel_name(i)
            self.assertIsInstance(name, str)
            self.assertTrue(len(name) > 0)

        # Configurar algunos nombres personalizados típicos de M32
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

        # Verificar nombres configurados
        for ch_id, expected_name in m32_channel_names.items():
            self.assertEqual(channel_manager.get_channel_name(ch_id), expected_name)

        logger.info("OK: ChannelManager integrado correctamente con 32 canales M32")

    @patch('sounddevice.query_devices')
    @patch('sounddevice.InputStream')
    def test_m32_audio_callback_simulation(self, mock_input_stream, mock_query_devices):
        """Test: Simulación de callback de audio M32"""
        logger.info("Test: Simulacion de callback de audio M32")

        # Configurar mocks
        def mock_query(device_id=None):
            if device_id == 100:
                return self.m32_device_info
            else:
                return [self.m32_device_info]

        mock_query_devices.side_effect = mock_query

        mock_stream = Mock()
        mock_stream.latency = 0.005
        mock_input_stream.return_value = mock_stream

        # Configurar callback de prueba
        audio_data_received = []
        def test_callback(audio_data):
            audio_data_received.append(audio_data.copy() if hasattr(audio_data, 'copy') else audio_data)

        self.audio_capture.register_callback(test_callback)

        # Iniciar captura
        device_id = 100
        num_channels = self.audio_capture.start_capture(device_id=device_id)

        # Simular callback con datos de 32 canales
        blocksize = config.BLOCKSIZE
        audio_data_32ch = np.random.randn(blocksize, 32).astype(np.float32) * 0.1  # Señal de prueba

        # Llamar al callback interno
        time_info = {'input_buffer_adc_time': time.time()}
        self.audio_capture._audio_callback(audio_data_32ch, blocksize, time_info, None)

        # Verificar que el callback recibió los datos
        self.assertEqual(len(audio_data_received), 1)
        received_data = audio_data_received[0]
        self.assertEqual(received_data.shape, (blocksize, 32))

        logger.info("OK: Callback de audio M32 simulado correctamente")

    def test_m32_performance_requirements(self):
        """Test: Verificación de requisitos de rendimiento M32"""
        logger.info("Test: Verificacion de requisitos de rendimiento M32")

        # Requisitos típicos de una interfaz profesional como M32
        m32_specs = {
            'sample_rates': [44100, 48000, 96000],  # Sample rates soportados
            'bit_depth': 24,  # Bit depth
            'latency_target': 5.0,  # Latencia objetivo en ms
            'channels': 32
        }

        # Verificar configuración del sistema
        self.assertIn(config.SAMPLE_RATE, m32_specs['sample_rates'],
                     f"Sample rate {config.SAMPLE_RATE} no soportado por M32")

        # Calcular latencia teórica
        block_latency_ms = (config.BLOCKSIZE / config.SAMPLE_RATE) * 1000
        self.assertLess(block_latency_ms, m32_specs['latency_target'],
                       f"Latencia de bloque {block_latency_ms:.2f}ms excede objetivo M32")

        # Verificar capacidad de canales
        self.assertGreaterEqual(config.MAX_LOGICAL_CHANNELS, m32_specs['channels'],
                               f"Sistema no soporta {m32_specs['channels']} canales requeridos por M32")

        logger.info("OK: Requisitos de rendimiento M32 verificados")

    @patch('sounddevice.query_devices')
    @patch('sounddevice.InputStream')
    def test_m32_full_system_simulation(self, mock_input_stream, mock_query_devices):
        """Test: Simulación completa del sistema con M32"""
        logger.info("Test: Simulacion completa del sistema con M32")

        # Configurar dispositivo M32
        def mock_query(device_id=None):
            if device_id == 100:
                return self.m32_device_info
            else:
                return [self.m32_device_info]

        mock_query_devices.side_effect = mock_query

        mock_stream = Mock()
        mock_stream.latency = 0.005
        mock_input_stream.return_value = mock_stream

        # Simular flujo completo:
        # 1. Detección de dispositivo
        devices = mock_query_devices()
        m32_found = any('MIDAS M32' in d.get('name', '') for d in devices)
        self.assertTrue(m32_found, "M32 no detectado")

        # 2. Configuración de captura
        device_id = 100
        num_channels = self.audio_capture.start_capture(device_id=device_id)
        self.assertEqual(num_channels, 32)

        # 3. Configuración de ChannelManager
        channel_manager = ChannelManager(num_channels)

        # 4. Simulación de procesamiento de audio
        blocksize = config.BLOCKSIZE
        audio_frames_processed = 0
        test_duration_blocks = 10  # Procesar 10 bloques

        for _ in range(test_duration_blocks):
            # Generar audio de prueba (señal de seno en diferentes frecuencias por canal)
            t = np.linspace(0, blocksize/config.SAMPLE_RATE, blocksize, False)
            audio_block = np.zeros((blocksize, 32), dtype=np.float32)

            for ch in range(32):
                # Frecuencia diferente por canal (100Hz + 10Hz * canal)
                freq = 100 + 10 * ch
                audio_block[:, ch] = 0.1 * np.sin(2 * np.pi * freq * t)

            # Procesar bloque
            time_info = {'input_buffer_adc_time': time.time()}
            self.audio_capture._audio_callback(audio_block, blocksize, time_info, None)
            audio_frames_processed += blocksize

        # Verificaciones finales
        total_frames_expected = test_duration_blocks * blocksize
        self.assertEqual(audio_frames_processed, total_frames_expected)

        # Verificar que el stream sigue activo
        self.assertTrue(self.audio_capture.running)
        mock_stream.start.assert_called_once()

        # Detener captura
        self.audio_capture.stop_capture()
        mock_stream.stop.assert_called_once()
        mock_stream.close.assert_called_once()

        logger.info(f"OK: Sistema completo simulado - {audio_frames_processed} frames procesados")

if __name__ == '__main__':
    unittest.main()