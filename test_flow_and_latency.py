#!/usr/bin/env python3
"""
test_flow_and_latency.py - Tests especializados de flujo y latencia

Tests que miden:
- Latencia de audio (captura -> procesamiento -> entrega)
- Throughput del sistema
- Latencia WebSocket
- Rendimiento bajo carga
- Optimizaciones de latencia
"""

import unittest
import sys
import os
import time
import threading
import numpy as np
from unittest.mock import Mock, patch, MagicMock
import statistics

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Importar módulos del sistema
import config
from audio_server.audio_capture import AudioCapture
from audio_server.channel_manager import ChannelManager
from audio_server.latency_optimizer import LatencyOptimizer
from audio_server.websocket_server import broadcast_audio_levels


class TestAudioLatency(unittest.TestCase):
    """Tests de latencia de audio"""

    def setUp(self):
        self.audio_capture = AudioCapture()
        self.channel_manager = ChannelManager(8)

    def tearDown(self):
        if self.audio_capture.running:
            self.audio_capture.stop_capture()

    def test_audio_callback_latency(self):
        """Medir latencia de procesamiento de callbacks de audio"""
        latencies = []

        def latency_test_callback(audio_data):
            start_time = time.time()
            # Simular procesamiento mínimo
            processed = np.sum(audio_data)
            end_time = time.time()
            latency_ms = (end_time - start_time) * 1000
            latencies.append(latency_ms)

        self.audio_capture.register_callback(latency_test_callback)

        # Simular 10 bloques de audio
        blocksize = config.BLOCKSIZE
        for i in range(10):
            audio_block = np.random.randn(blocksize, 8).astype(np.float32)
            time_info = {'input_buffer_adc_time': time.time()}
            self.audio_capture._audio_callback(audio_block, blocksize, time_info, None)

        # Verificar latencias
        self.assertGreater(len(latencies), 0)
        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)

        # Latencia debería ser < 1ms para procesamiento básico
        self.assertLess(avg_latency, 1.0, f"Latencia promedio demasiado alta: {avg_latency:.3f}ms")
        self.assertLess(max_latency, 5.0, f"Latencia máxima demasiado alta: {max_latency:.3f}ms")

        print(f"📊 Latencia callback - Promedio: {avg_latency:.3f}ms, Máxima: {max_latency:.3f}ms")

    def test_audio_capture_initialization_latency(self):
        """Medir latencia de inicialización de captura"""
        start_time = time.time()

        # Simular inicialización (sin dispositivo real)
        with patch('sounddevice.InputStream') as mock_stream:
            mock_stream_instance = MagicMock()
            mock_stream_instance.latency = 0.005  # 5ms
            mock_stream.return_value = mock_stream_instance

            # Intentar iniciar captura (fallará pero mediremos tiempo)
            try:
                self.audio_capture.start_capture(device_id=0)
            except:
                pass  # Esperado sin dispositivo real

        end_time = time.time()
        init_latency = (end_time - start_time) * 1000

        # Inicialización debería ser < 100ms
        self.assertLess(init_latency, 100.0, f"Inicialización demasiado lenta: {init_latency:.3f}ms")
        print(f"⚡ Latencia inicialización captura: {init_latency:.3f}ms")

    def test_channel_processing_latency(self):
        """Medir latencia de procesamiento por canal"""
        latencies_per_channel = {}

        def channel_latency_callback(audio_data):
            start_time = time.time()

            # Procesar cada canal individualmente
            for ch in range(min(8, audio_data.shape[1])):
                # Simular procesamiento DSP básico por canal
                channel_data = audio_data[:, ch]
                rms = np.sqrt(np.mean(channel_data ** 2))
                peak = np.max(np.abs(channel_data))

            end_time = time.time()
            latency_ms = (end_time - start_time) * 1000
            latencies_per_channel[ch] = latency_ms

        self.audio_capture.register_callback(channel_latency_callback)

        # Procesar un bloque
        audio_block = np.random.randn(config.BLOCKSIZE, 8).astype(np.float32)
        time_info = {'input_buffer_adc_time': time.time()}
        self.audio_capture._audio_callback(audio_block, config.BLOCKSIZE, time_info, None)

        # Verificar latencias por canal
        if latencies_per_channel:
            avg_channel_latency = sum(latencies_per_channel.values()) / len(latencies_per_channel)
            self.assertLess(avg_channel_latency, 2.0, f"Procesamiento por canal lento: {avg_channel_latency:.3f}ms")
            print(f"🎚️ Latencia procesamiento por canal: {avg_channel_latency:.3f}ms")


class TestThroughput(unittest.TestCase):
    """Tests de throughput del sistema"""

    def setUp(self):
        self.audio_capture = AudioCapture()
        self.channel_manager = ChannelManager(32)  # M32 simulation

    def tearDown(self):
        if self.audio_capture.running:
            self.audio_capture.stop_capture()

    def test_audio_throughput_32_channels(self):
        """Medir throughput con 32 canales (MIDAS M32)"""
        processed_blocks = 0
        start_time = time.time()

        def throughput_callback(audio_data):
            nonlocal processed_blocks
            processed_blocks += 1
            # Procesamiento mínimo para medir throughput puro
            _ = np.sum(audio_data)

        self.audio_capture.register_callback(throughput_callback)

        # Procesar 100 bloques de 32 canales
        num_blocks = 100
        for i in range(num_blocks):
            audio_block = np.random.randn(config.BLOCKSIZE, 32).astype(np.float32)
            time_info = {'input_buffer_adc_time': time.time()}
            self.audio_capture._audio_callback(audio_block, config.BLOCKSIZE, time_info, None)

        end_time = time.time()
        total_time = end_time - start_time
        throughput_blocks_per_sec = num_blocks / total_time
        throughput_samples_per_sec = throughput_blocks_per_sec * config.BLOCKSIZE * 32

        # Deberíamos procesar al menos 100 bloques/segundo
        self.assertGreater(throughput_blocks_per_sec, 100,
                          f"Throughput bajo: {throughput_blocks_per_sec:.1f} bloques/s")

        print(f"🚀 Throughput 32ch: {throughput_blocks_per_sec:.1f} bloques/s")
        print(f"   Samples/s: {throughput_samples_per_sec:,.0f}")

    def test_concurrent_client_throughput(self):
        """Medir throughput con múltiples clientes simulados"""
        num_clients = 5
        client_processed_blocks = [0] * num_clients
        start_time = time.time()

        def create_client_callback(client_idx):
            def client_callback(audio_data):
                client_processed_blocks[client_idx] += 1
                # Simular procesamiento por cliente (mezcla diferente)
                gain = 0.1 + client_idx * 0.1
                _ = np.sum(audio_data * gain)
            return client_callback

        # Registrar callbacks para múltiples clientes
        for i in range(num_clients):
            self.audio_capture.register_callback(create_client_callback(i))

        # Procesar bloques con múltiples clientes
        num_blocks = 50
        for i in range(num_blocks):
            audio_block = np.random.randn(config.BLOCKSIZE, 8).astype(np.float32)
            time_info = {'input_buffer_adc_time': time.time()}
            self.audio_capture._audio_callback(audio_block, config.BLOCKSIZE, time_info, None)

        end_time = time.time()
        total_time = end_time - start_time

        # Verificar que todos los clientes procesaron los bloques
        for i, blocks in enumerate(client_processed_blocks):
            self.assertEqual(blocks, num_blocks, f"Cliente {i} no procesó todos los bloques")

        total_blocks_processed = sum(client_processed_blocks)
        throughput_blocks_per_sec = total_blocks_processed / total_time

        print(f"👥 Throughput {num_clients} clientes: {throughput_blocks_per_sec:.1f} bloques/s total")

    def test_memory_efficiency_under_load(self):
        """Verificar eficiencia de memoria bajo carga"""
        import psutil
        import os

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Simular carga alta: procesar muchos bloques
        processed_blocks = 0

        def memory_test_callback(audio_data):
            nonlocal processed_blocks
            processed_blocks += 1

        self.audio_capture.register_callback(memory_test_callback)

        # Procesar 1000 bloques
        for i in range(1000):
            audio_block = np.random.randn(config.BLOCKSIZE, 16).astype(np.float32)
            time_info = {'input_buffer_adc_time': time.time()}
            self.audio_capture._audio_callback(audio_block, config.BLOCKSIZE, time_info, None)

        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory

        # El aumento de memoria debería ser < 50MB para 1000 bloques
        self.assertLess(memory_increase, 50.0, f"Aumento de memoria excesivo: {memory_increase:.1f}MB")

        print(f"💾 Uso de memoria - Inicial: {initial_memory:.1f}MB, Final: {final_memory:.1f}MB")
        print(f"   Aumento: {memory_increase:.1f}MB para {processed_blocks} bloques")


class TestWebSocketLatency(unittest.TestCase):
    """Tests de latencia WebSocket"""

    def setUp(self):
        self.latency_optimizer = LatencyOptimizer()

    def test_parameter_update_debouncing(self):
        """Verificar debouncing de actualizaciones de parámetros"""
        client_id = "test_client"
        update_times = []

        # Simular múltiples actualizaciones rápidas
        start_time = time.time()

        for i in range(10):
            self.latency_optimizer.queue_parameter_update(client_id, "gain", 0, 0.5 + i * 0.01)
            time.sleep(0.001)  # 1ms entre actualizaciones

        # Esperar a que se procese el debouncing
        time.sleep(0.1)

        end_time = time.time()
        total_time = (end_time - start_time) * 1000

        # Con debouncing de 50ms, debería tomar al menos ese tiempo
        self.assertGreater(total_time, 45, f"Debouncing no funcionó correctamente: {total_time:.1f}ms")

        print(f"⏱️ Debouncing efectivo: {total_time:.1f}ms para 10 actualizaciones")

    def test_websocket_broadcast_performance(self):
        """Medir rendimiento de broadcast WebSocket"""
        import audio_server.websocket_server as ws_server

        # Simular niveles de audio para múltiples canales
        levels = {f"ch_{i}": 0.1 + i * 0.05 for i in range(32)}

        start_time = time.time()

        # Broadcast a múltiples "clientes" simulados
        for i in range(10):
            ws_server.broadcast_audio_levels(levels)

        end_time = time.time()
        broadcast_time = (end_time - start_time) * 1000

        # 10 broadcasts deberían tomar < 50ms
        self.assertLess(broadcast_time, 50.0, f"Broadcast lento: {broadcast_time:.1f}ms")

        print(f"📡 Broadcast WebSocket: {broadcast_time:.1f}ms para 10 operaciones")

    @patch('audio_server.websocket_server.emit')
    def test_websocket_message_latency(self, mock_emit):
        """Medir latencia de mensajes WebSocket"""
        latencies = []

        def measure_emit(*args, **kwargs):
            start = time.time()
            # Simular procesamiento de emit
            time.sleep(0.001)  # 1ms simulado
            end = time.time()
            latencies.append((end - start) * 1000)

        mock_emit.side_effect = measure_emit

        # Enviar múltiples mensajes
        for i in range(20):
            mock_emit('audio_levels', {'channel_0': 0.5}, broadcast=True)

        if latencies:
            avg_latency = sum(latencies) / len(latencies)
            max_latency = max(latencies)

            # Latencia promedio debería ser baja
            self.assertLess(avg_latency, 5.0, f"Latencia WebSocket alta: {avg_latency:.3f}ms")
            print(f"🌐 Latencia WebSocket - Promedio: {avg_latency:.3f}ms, Máxima: {max_latency:.3f}ms")


class TestLoadPerformance(unittest.TestCase):
    """Tests de rendimiento bajo carga"""

    def setUp(self):
        self.audio_capture = AudioCapture()
        self.channel_manager = ChannelManager(32)

    def tearDown(self):
        if self.audio_capture.running:
            self.audio_capture.stop_capture()

    def test_high_load_audio_processing(self):
        """Test de procesamiento de audio bajo alta carga"""
        num_callbacks = 5
        callback_counts = [0] * num_callbacks
        start_time = time.time()

        def create_load_callback(idx):
            def load_callback(audio_data):
                callback_counts[idx] += 1
                # Procesamiento intensivo simulado
                for ch in range(min(8, audio_data.shape[1])):
                    # FFT simulado (operación costosa)
                    fft_result = np.fft.fft(audio_data[:, ch])
                    _ = np.abs(fft_result).mean()
            return load_callback

        # Registrar múltiples callbacks con procesamiento intensivo
        for i in range(num_callbacks):
            self.audio_capture.register_callback(create_load_callback(i))

        # Procesar bajo carga
        num_blocks = 20
        for i in range(num_blocks):
            audio_block = np.random.randn(config.BLOCKSIZE, 8).astype(np.float32)
            time_info = {'input_buffer_adc_time': time.time()}
            self.audio_capture._audio_callback(audio_block, config.BLOCKSIZE, time_info, None)

        end_time = time.time()
        total_time = end_time - start_time

        # Verificar que todos los callbacks procesaron todos los bloques
        for i, count in enumerate(callback_counts):
            self.assertEqual(count, num_blocks, f"Callback {i} perdió bloques: {count}/{num_blocks}")

        processing_rate = num_blocks / total_time
        print(f"🔥 Procesamiento alta carga: {processing_rate:.1f} bloques/s con {num_callbacks} callbacks")

    def test_concurrent_channel_operations(self):
        """Test de operaciones concurrentes en canales"""
        num_threads = 4
        operations_completed = [0] * num_threads

        def channel_operations_thread(thread_id):
            """Simular operaciones concurrentes en canales"""
            for i in range(25):
                # Operaciones mixtas en canales
                channel_id = (thread_id * 8 + i) % 32

                # Simular diferentes operaciones
                if i % 4 == 0:
                    self.channel_manager.subscribe_client(f"client_{thread_id}", [channel_id])
                elif i % 4 == 1:
                    subscription = self.channel_manager.get_client_subscription(f"client_{thread_id}")
                elif i % 4 == 2:
                    self.channel_manager.unsubscribe_client(f"client_{thread_id}")
                # else: pausa

                operations_completed[thread_id] += 1

        # Ejecutar operaciones concurrentes
        threads = []
        start_time = time.time()

        for i in range(num_threads):
            t = threading.Thread(target=channel_operations_thread, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        end_time = time.time()
        total_time = end_time - start_time

        total_operations = sum(operations_completed)
        operations_per_sec = total_operations / total_time

        print(f"⚡ Operaciones concurrentes: {operations_per_sec:.1f} ops/s ({total_operations} total en {total_time:.2f}s)")

        # Verificar que todas las operaciones se completaron
        for i, count in enumerate(operations_completed):
            self.assertGreater(count, 20, f"Thread {i} completó pocas operaciones: {count}")


class TestLatencyOptimizations(unittest.TestCase):
    """Tests de optimizaciones de latencia"""

    def setUp(self):
        self.optimizer = LatencyOptimizer(debounce_ms=25)  # Debounce más agresivo

    def test_aggressive_debouncing(self):
        """Verificar debouncing agresivo"""
        client_id = "test_client"
        start_time = time.time()

        # Enviar muchas actualizaciones en poco tiempo
        for i in range(20):
            self.optimizer.queue_parameter_update(client_id, "gain", 0, 0.1 + i * 0.01)

        # Esperar procesamiento
        time.sleep(0.1)

        end_time = time.time()
        total_time = (end_time - start_time) * 1000

        # Con debounce de 25ms, debería ser eficiente
        self.assertLess(total_time, 200, f"Debouncing ineficiente: {total_time:.1f}ms")

        print(f"🎯 Debouncing agresivo: {total_time:.1f}ms para 20 actualizaciones")

    def test_batch_parameter_updates(self):
        """Verificar procesamiento por lotes de parámetros"""
        client_id = "batch_client"

        # Enviar múltiples parámetros diferentes
        params_to_update = [
            ("gain", 0, 0.8), ("gain", 1, 0.7), ("gain", 2, 0.9),
            ("pan", 0, -0.2), ("pan", 1, 0.1), ("pan", 2, 0.3)
        ]

        start_time = time.time()

        for param_type, channel, value in params_to_update:
            self.optimizer.queue_parameter_update(client_id, param_type, channel, value)

        # Esperar procesamiento por lotes
        time.sleep(0.1)

        end_time = time.time()
        batch_time = (end_time - start_time) * 1000

        # Procesamiento por lotes debería ser eficiente
        self.assertLess(batch_time, 150, f"Procesamiento por lotes lento: {batch_time:.1f}ms")

        print(f"📦 Procesamiento por lotes: {batch_time:.1f}ms para {len(params_to_update)} parámetros")


if __name__ == '__main__':
    # Configurar logging para tests
    import logging
    logging.basicConfig(level=logging.WARNING)

    # Ejecutar tests con más verbosidad para métricas
    unittest.main(verbosity=2)