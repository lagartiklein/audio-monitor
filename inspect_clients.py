#!/usr/bin/env python3
"""
Inspección de configuraciones de clientes activos
Revisa las ganancias y configuraciones de todos los clientes conectados
"""

import sys
import os
import json
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from audio_server.channel_manager import ChannelManager

def inspect_client_configurations():
    """Inspecciona las configuraciones de todos los clientes"""
    logger.info("🔍 Inspeccionando configuraciones de clientes activos")

    # Inicializar ChannelManager
    channel_manager = ChannelManager(getattr(config, 'MAX_CHANNELS', 8))

    # Simular algunos clientes para inspección (esto cargaría configuraciones reales)
    # En un sistema real, estos vendrían de conexiones activas

    # Verificar archivos de configuración persistente
    config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config')

    # Revisar channels_state.json
    channels_state_file = os.path.join(config_dir, 'channels_state.json')
    if os.path.exists(channels_state_file):
        try:
            with open(channels_state_file, 'r', encoding='utf-8') as f:
                channels_data = json.load(f)

            logger.info("📁 Canales persistentes encontrados:")
            for device_uuid, state in channels_data.get('channels_state', {}).items():
                gains = state.get('gains', {})
                master_gain = state.get('master_gain', 1.0)

                # Buscar ganancias altas
                high_gains = {ch: gain for ch, gain in gains.items() if gain > 2.0}
                if high_gains:
                    logger.warning(f"🚨 GANANCIAS ALTAS en {device_uuid[:12]}: {high_gains}")

                if master_gain > 2.0:
                    logger.warning(f"🚨 MASTER GAIN ALTO en {device_uuid[:12]}: {master_gain}")

                logger.info(f"  {device_uuid[:12]}: {len(state.get('channels', []))} canales, master_gain={master_gain}")

        except Exception as e:
            logger.error(f"Error leyendo channels_state.json: {e}")

    # Revisar client_states.json
    client_states_file = os.path.join(config_dir, 'client_states.json')
    if os.path.exists(client_states_file):
        try:
            with open(client_states_file, 'r', encoding='utf-8') as f:
                clients_data = json.load(f)

            logger.info("📁 Estados de clientes persistentes encontrados:")
            for client_id, state in clients_data.items():
                gains = state.get('gains', {})
                master_gain = state.get('master_gain', 1.0)

                # Buscar ganancias altas
                high_gains = {ch: gain for ch, gain in gains.items() if gain > 2.0}
                if high_gains:
                    logger.warning(f"🚨 GANANCIAS ALTAS en cliente {client_id[:12]}: {high_gains}")

                if master_gain > 2.0:
                    logger.warning(f"🚨 MASTER GAIN ALTO en cliente {client_id[:12]}: {master_gain}")

                logger.info(f"  {client_id[:12]}: {len(state.get('channels', []))} canales, master_gain={master_gain}, tipo={state.get('client_type', 'unknown')}")

        except Exception as e:
            logger.error(f"Error leyendo client_states.json: {e}")

    # Verificar configuraciones activas simuladas
    logger.info("\n🎛️ Verificación de configuraciones problemáticas:")

    # Simular diferentes escenarios problemáticos
    test_scenarios = [
        {
            "name": "Cliente con ganancias altas",
            "gains": {"0": 5.0, "1": 3.0},
            "master_gain": 2.0
        },
        {
            "name": "Cliente con master gain alto",
            "gains": {"0": 1.0, "1": 1.0},
            "master_gain": 4.0
        },
        {
            "name": "Cliente normal",
            "gains": {"0": 1.0, "1": 1.0},
            "master_gain": 1.0
        }
    ]

    for scenario in test_scenarios:
        logger.info(f"\n🧪 Escenario: {scenario['name']}")
        logger.info(f"   Ganancias: {scenario['gains']}")
        logger.info(f"   Master Gain: {scenario['master_gain']}")

        # Calcular ganancia total máxima
        max_individual = max(scenario['gains'].values()) if scenario['gains'] else 1.0
        total_gain = max_individual * scenario['master_gain']
        total_db = 20 * (total_gain ** 0.5)  # Aproximado para múltiples canales

        if total_gain > 3.0:
            logger.warning(f"   🚨 GANANCIA TOTAL EXTREMA: {total_gain:.1f}x ({total_db:.1f}dB)")
        elif total_gain > 2.0:
            logger.warning(f"   ⚠️ Ganancia total alta: {total_gain:.1f}x ({total_db:.1f}dB)")
        else:
            logger.info(f"   ✅ Ganancia total normal: {total_gain:.1f}x")

    logger.info("\n🔍 Inspección completada")

if __name__ == "__main__":
    inspect_client_configurations()