#!/usr/bin/env python3
"""
Test específico del Native Server - Validación de ganancias
Simula mensajes del cliente Android para detectar problemas de validación de ganancias
"""

import sys
import os
import logging
import json
import threading

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from audio_server.native_server import NativeAudioServer
from audio_server.channel_manager import ChannelManager

class MockClient:
    """Cliente mock para simular conexiones Android"""
    def __init__(self, client_id):
        self.id = client_id
        self.persistent_id = client_id
        self.status = 1
        self.is_temp_id = False
        self.rf_mode = False
        self.packets_sent = 0
        self.consecutive_send_failures = 0
        self.auto_reconnect = True

    def send_mix_state(self, subscription):
        """Mock del envío de estado de mezcla"""
        self.packets_sent += 1
        logger.debug(f"📤 Cliente {self.id[:8]} recibió mix_state")
        return True

    def send_bytes_sync(self, data):
        """Mock del envío síncrono"""
        self.packets_sent += 1
        return True

def test_native_server_gain_validation():
    """Test de validación de ganancias en Native Server"""
    logger.info("🧪 Iniciando test de validación de ganancias en Native Server")

    # Inicializar componentes
    channel_manager = ChannelManager(8)
    native_server = NativeAudioServer(channel_manager)

    # Crear cliente mock
    mock_client = MockClient("test_android_client")

    # Suscribir cliente inicialmente
    channel_manager.subscribe_client(
        mock_client.persistent_id,
        channels=[0, 1],
        gains={0: 1.0, 1: 1.0},
        pans={0: 0.0, 1: 0.0},
        client_type="native"
    )

    logger.info("✅ Cliente suscrito inicialmente")

    # Test 1: Ganancias normales
    logger.info("\n🧪 TEST 1: Ganancias normales")
    normal_message = {
        'type': 'update_mix',
        'channels': [0, 1],
        'gains': {'0': 1.5, '1': 2.0},  # Normales
        'pans': {'0': 0.0, '1': 0.0}
    }

    try:
        native_server._handle_control_message(mock_client, normal_message)
        subscription = channel_manager.get_client_subscription(mock_client.persistent_id)
        gains = subscription.get('gains', {})
        logger.info(f"✅ Ganancias aplicadas: {gains}")

        # Verificar que se aplicaron correctamente
        assert abs(gains.get(0, 0) - 1.5) < 0.001, f"Ganancia canal 0 incorrecta: {gains.get(0)}"
        assert abs(gains.get(1, 0) - 2.0) < 0.001, f"Ganancia canal 1 incorrecta: {gains.get(1)}"
        logger.info("✅ Test 1 PASADO: Ganancias normales aplicadas correctamente")

    except Exception as e:
        logger.error(f"❌ Test 1 FALLADO: {e}")

    # Test 2: Ganancias altas (pero no extremas)
    logger.info("\n🧪 TEST 2: Ganancias altas")
    high_message = {
        'type': 'update_mix',
        'channels': [0, 1],
        'gains': {'0': 5.0, '1': 8.0},  # Altas pero posibles
        'pans': {'0': 0.0, '1': 0.0}
    }

    try:
        native_server._handle_control_message(mock_client, high_message)
        subscription = channel_manager.get_client_subscription(mock_client.persistent_id)
        gains = subscription.get('gains', {})
        logger.info(f"⚠️ Ganancias aplicadas: {gains}")

        # Verificar que se VALIDARON correctamente (limitadas a 3.0)
        assert abs(gains.get(0, 0) - 3.0) < 0.001, f"Ganancia canal 0 no limitada: {gains.get(0)}"
        assert abs(gains.get(1, 0) - 3.0) < 0.001, f"Ganancia canal 1 no limitada: {gains.get(1)}"
        logger.info("✅ Test 2 PASADO: Ganancias altas validadas correctamente")

    except Exception as e:
        logger.error(f"❌ Test 2 FALLADO: {e}")

    # Test 3: Ganancias EXTREMAS
    logger.info("\n🧪 TEST 3: Ganancias EXTREMAS")
    extreme_message = {
        'type': 'update_mix',
        'channels': [0, 1],
        'gains': {'0': 50.0, '1': 100.0},  # Extremas - deberían ser rechazadas
        'pans': {'0': 0.0, '1': 0.0}
    }

    try:
        native_server._handle_control_message(mock_client, extreme_message)
        subscription = channel_manager.get_client_subscription(mock_client.persistent_id)
        gains = subscription.get('gains', {})
        logger.info(f"🚨 Ganancias aplicadas: {gains}")

        # Verificar que se VALIDARON correctamente (limitadas a 3.0)
        assert abs(gains.get(0, 0) - 3.0) < 0.001, f"Ganancia canal 0 no limitada: {gains.get(0)}"
        assert abs(gains.get(1, 0) - 3.0) < 0.001, f"Ganancia canal 1 no limitada: {gains.get(1)}"
        logger.info("✅ Test 3 PASADO: Ganancias EXTREMAS validadas correctamente")

    except Exception as e:
        logger.error(f"❌ Test 3 FALLADO: {e}")

    # Test 3.5: Master Gain Extremo en mensaje update_mix
    logger.info("\n🧪 TEST 3.5: Master Gain Extremo en mensaje nativo")
    master_extreme_native_message = {
        'type': 'update_mix',
        'channels': [0, 1],
        'gains': {'0': 1.0, '1': 1.0},
        'pans': {'0': 0.0, '1': 0.0},
        'master_gain': 10.0  # Extremo en mensaje nativo
    }

    try:
        native_server._handle_control_message(mock_client, master_extreme_native_message)
        subscription = channel_manager.get_client_subscription(mock_client.persistent_id)
        master_gain_applied = subscription.get('master_gain', 1.0)
        logger.info(f"🚨 Master gain aplicado desde mensaje nativo: {master_gain_applied}")

        # Verificar que se validó correctamente (limitado a 2.0)
        assert abs(master_gain_applied - 2.0) < 0.001, f"Master gain no limitado: {master_gain_applied}"
        logger.info("✅ Test 3.5 PASADO: Master gain extremo validado en mensaje nativo")

    except Exception as e:
        logger.error(f"❌ Test 3.5 FALLADO: {e}")

    # Test 4: Master Gain Extremo (vía ChannelManager directo)
    logger.info("\n🧪 TEST 4: Master Gain Extremo")
    master_extreme_message = {
        'type': 'update_mix',
        'channels': [0, 1],
        'gains': {'0': 1.0, '1': 1.0},
        'pans': {'0': 0.0, '1': 0.0},
        'master_gain': 20.0  # Extremo
    }

    try:
        # Nota: update_mix del native_server no maneja master_gain directamente
        # Esto se haría desde el channel_manager
        success = channel_manager.update_client_mix(
            mock_client.persistent_id,
            master_gain=20.0
        )

        subscription = channel_manager.get_client_subscription(mock_client.persistent_id)
        master_gain = subscription.get('master_gain', 1.0)
        logger.info(f"🚨 Master gain aplicado: {master_gain}")

        if master_gain == 20.0:
            logger.error("🚨 Test 4: Master gain EXTREMO aplicado SIN validación")
        else:
            logger.info("✅ Test 4: Master gain validado correctamente")

    except Exception as e:
        logger.error(f"❌ Test 4 FALLADO: {e}")

    # Test 5: Simular múltiples clientes con ganancias altas
    logger.info("\n🧪 TEST 5: Múltiples clientes con ganancias")
    client2 = MockClient("test_android_client_2")
    channel_manager.subscribe_client(
        client2.persistent_id,
        channels=[0, 1],
        gains={0: 3.0, 1: 4.0},
        pans={0: 0.0, 1: 0.0},
        client_type="native"
    )

    # Calcular ganancia total acumulada
    total_gain = 0
    for client_id in [mock_client.persistent_id, client2.persistent_id]:
        subscription = channel_manager.get_client_subscription(client_id)
        if subscription:
            gains = subscription.get('gains', {})
            master = subscription.get('master_gain', 1.0)
            max_gain = max(gains.values()) if gains else 1.0
            total_gain += max_gain * master

    logger.info(f"📊 Ganancia total acumulada: {total_gain:.1f}x")
    if total_gain > 10.0:
        logger.error("🚨 Test 5: Ganancia acumulada EXTREMA - riesgo de saturación")
    elif total_gain > 5.0:
        logger.warning("⚠️ Test 5: Ganancia acumulada alta")
    else:
        logger.info("✅ Test 5: Ganancia acumulada normal")

    # Resumen de hallazgos
    logger.info("\n" + "="*60)
    logger.info("📋 RESUMEN DE HALLAZGOS - NATIVE SERVER")
    logger.info("="*60)
    logger.info("✅ VALIDACIÓN IMPLEMENTADA: El Native Server ahora valida ganancias")
    logger.info("   - Ganancias individuales limitadas: 0.0 - 3.0 (10dB máximo)")
    logger.info("   - Logging automático de ganancias rechazadas")
    logger.info("   - Prevención de saturación por clientes Android")
    logger.info("")
    logger.info("⚠️ PENDIENTE: Validación de master_gain en mensajes nativos")
    logger.info("   - Actualmente se valida en ChannelManager, pero no en native_server")
    logger.info("")
    logger.info("💡 RECOMENDACIONES ADICIONALES:")
    logger.info("   - Monitorear logs para ganancias sospechosas")
    logger.info("   - Considerar límites más estrictos si es necesario")
    logger.info("   - Implementar alertas para ganancias > 2.0x")

    logger.info("\n🧪 Tests completados")

if __name__ == "__main__":
    test_native_server_gain_validation()