#!/usr/bin/env python3
"""
Test de Continuidad de Amplitud de Audio
Mide la amplitud en cada etapa del pipeline de audio para detectar aumentos extremos de ganancia.
"""

import numpy as np
import sys
import os
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from audio_server.audio_capture import AudioCapture
from audio_server.audio_mixer import AudioMixer
from audio_server.channel_manager import ChannelManager

def calculate_amplitude_stats(audio_data, label):
    """Calcula estadísticas de amplitud del audio"""
    if audio_data is None or audio_data.size == 0:
        return {"peak": 0.0, "rms": 0.0, "max_abs": 0.0}

    # Convertir a float si es necesario
    if audio_data.dtype != np.float32:
        audio_data = audio_data.astype(np.float32)

    peak = np.max(np.abs(audio_data))
    rms = np.sqrt(np.mean(audio_data ** 2))

    stats = {
        "peak": float(peak),
        "rms": float(rms),
        "max_abs": float(peak),
        "shape": audio_data.shape,
        "dtype": str(audio_data.dtype)
    }

    logger.info(f"📊 {label}: Peak={peak:.4f}, RMS={rms:.4f}, Shape={audio_data.shape}")
    return stats

def test_audio_amplitude_continuity():
    """Test completo de continuidad de amplitud"""
    logger.info("🎵 Iniciando test de continuidad de amplitud de audio")

    # 1. Inicializar componentes
    try:
        # Crear datos de audio de prueba (simular captura)
        sample_rate = config.SAMPLE_RATE
        blocksize = config.BLOCKSIZE
        num_channels = 2  # Simular 2 canales

        # Generar señal de prueba: tono sinusoidal a -20dBFS
        t = np.linspace(0, blocksize / sample_rate, blocksize, endpoint=False)
        test_signal = 0.1 * np.sin(2 * np.pi * 440 * t)  # -20dBFS approx
        audio_data = np.tile(test_signal.reshape(-1, 1), (1, num_channels)).astype(np.float32)

        logger.info(f"🎵 Señal de prueba generada: {audio_data.shape}, dtype={audio_data.dtype}")

        # 2. Punto 1: Después de "captura" (datos crudos)
        stats_capture = calculate_amplitude_stats(audio_data, "CAPTURA (Raw)")

        # 3. Inicializar ChannelManager y AudioMixer
        channel_manager = ChannelManager(num_channels)
        audio_mixer = AudioMixer(sample_rate=sample_rate, buffer_size=blocksize)

        # Crear cliente de prueba
        test_client_id = "test_client"
        test_channels = [0, 1]
        test_gains = {0: 2.0, 1: 1.5}  # Ganancias altas para probar
        test_pans = {0: 0.0, 1: 0.0}
        test_master_gain = 1.2

        channel_manager.subscribe_client(
            test_client_id,
            test_channels,
            gains=test_gains,
            pans=test_pans
        )
        channel_manager.update_client_mix(
            test_client_id,
            master_gain=test_master_gain
        )

        # 4. Simular procesamiento en AudioMixer
        subscription = channel_manager.get_client_subscription(test_client_id)

        # Aplicar ganancias individuales (simular parte del process_and_broadcast)
        gains = subscription.get('gains', {})
        master_gain = subscription.get('master_gain', 1.0)

        # Convertir a float32
        processed_audio = audio_data.astype(np.float32)

        # Aplicar ganancias individuales
        for ch in test_channels:
            if ch < processed_audio.shape[1]:
                gain = gains.get(ch, 1.0)
                processed_audio[:, ch] *= gain

        stats_after_individual_gains = calculate_amplitude_stats(processed_audio, "DESPUÉS DE GANANCIAS INDIVIDUALES")

        # Aplicar master gain
        processed_audio *= master_gain
        stats_after_master_gain = calculate_amplitude_stats(processed_audio, "DESPUÉS DE MASTER GAIN")

        # Aplicar limiter suave
        processed_audio = audio_mixer._apply_soft_limiter_professional(processed_audio, threshold=0.85, ratio=3.0)
        stats_after_limiter = calculate_amplitude_stats(processed_audio, "DESPUÉS DE LIMITER")

        # Aplicar headroom de compresión
        compression_headroom = audio_mixer.compression_headroom
        processed_audio *= compression_headroom
        stats_after_compression_headroom = calculate_amplitude_stats(processed_audio, "DESPUÉS DE COMPRESSION HEADROOM")

        # Simular compresión si está habilitada
        if audio_mixer.audio_compressor:
            compressed_audio = audio_mixer.audio_compressor.compress(processed_audio)
            # Para análisis, no podemos medir amplitud en bytes comprimidos
            stats_after_compression = {
                "note": f"Audio comprimido a {len(compressed_audio)} bytes",
                "compression_ratio": len(compressed_audio) / (processed_audio.nbytes * 0.01)  # estimado
            }
            logger.info(f"📊 DESPUÉS DE COMPRESIÓN: {len(compressed_audio)} bytes")
        else:
            stats_after_compression = {"note": "Compresión no habilitada"}

        # 5. Análisis de continuidad
        logger.info("\n" + "="*60)
        logger.info("📈 ANÁLISIS DE CONTINUIDAD DE AMPLITUD")
        logger.info("="*60)

        stages = [
            ("Captura", stats_capture),
            ("Ganancias Individuales", stats_after_individual_gains),
            ("Master Gain", stats_after_master_gain),
            ("Limiter", stats_after_limiter),
            ("Compression Headroom", stats_after_compression_headroom),
        ]

        previous_peak = stats_capture["peak"]
        for stage_name, stats in stages:
            if "peak" in stats:
                current_peak = stats["peak"]
                ratio = current_peak / previous_peak if previous_peak > 0 else float('inf')
                db_change = 20 * np.log10(ratio) if ratio > 0 else float('inf')

                status = "⚠️  AUMENTO EXTREMO" if ratio > 2.0 else "✅ Normal"
                logger.info(f"{stage_name}: {ratio:.2f}x ({db_change:+.1f}dB) {status}")

                previous_peak = current_peak

        # 6. Verificar clipping
        final_peak = stats_after_compression_headroom["peak"]
        if final_peak > 1.0:
            logger.warning(f"🚨 CLIPPING DETECTADO: Peak = {final_peak:.4f} (> 1.0)")
        else:
            logger.info(f"✅ Sin clipping: Peak = {final_peak:.4f}")

        logger.info("\n🎵 Test completado exitosamente")

    except Exception as e:
        logger.error(f"❌ Error en test: {e}")
        import traceback
        traceback.print_exc()

def test_audio_amplitude_continuity_real():
    """Test completo de continuidad de amplitud con datos de audio REAL capturados"""
    logger.info("🎵 Iniciando test de continuidad de amplitud con audio REAL")

    # 1. Inicializar componentes
    try:
        sample_rate = config.SAMPLE_RATE
        blocksize = config.BLOCKSIZE
        num_channels = 2  # Asumir 2 canales para prueba

        # Inicializar captura de audio REAL
        audio_capture = AudioCapture()
        audio_capture.start_capture()

        # Esperar un poco para que se estabilice
        import time
        time.sleep(0.5)

        # Capturar un buffer real
        try:
            audio_data = audio_capture.read()
            if audio_data is None or audio_data.size == 0:
                logger.warning("⚠️ No se pudo capturar audio real, usando datos sintéticos")
                # Fallback a datos sintéticos
                t = np.linspace(0, blocksize / sample_rate, blocksize, endpoint=False)
                test_signal = 0.01 * np.sin(2 * np.pi * 440 * t)  # Señal más baja para audio real
                audio_data = np.tile(test_signal.reshape(-1, 1), (1, num_channels)).astype(np.float32)
        except Exception as e:
            logger.warning(f"⚠️ Error capturando audio real: {e}, usando datos sintéticos")
            # Fallback a datos sintéticos
            t = np.linspace(0, blocksize / sample_rate, blocksize, endpoint=False)
            test_signal = 0.01 * np.sin(2 * np.pi * 440 * t)  # Señal más baja
            audio_data = np.tile(test_signal.reshape(-1, 1), (1, num_channels)).astype(np.float32)
        finally:
            audio_capture.stop_capture()

        logger.info(f"🎵 Datos de audio capturados: {audio_data.shape}, dtype={audio_data.dtype}")

        # 2. Punto 1: Después de captura real
        stats_capture = calculate_amplitude_stats(audio_data, "CAPTURA REAL")

        # 3. Inicializar ChannelManager y AudioMixer
        channel_manager = ChannelManager(num_channels)
        audio_mixer = AudioMixer(sample_rate=sample_rate, buffer_size=blocksize)

        # Crear cliente de prueba con ganancias REALISTAS (no extremas)
        test_client_id = "test_client_real"
        test_channels = [0, 1]
        test_gains = {0: 1.0, 1: 1.0}  # Ganancias unitarias para test realista
        test_pans = {0: 0.0, 1: 0.0}
        test_master_gain = 1.0  # Sin master gain extra

        channel_manager.subscribe_client(
            test_client_id,
            test_channels,
            gains=test_gains,
            pans=test_pans
        )
        channel_manager.update_client_mix(
            test_client_id,
            master_gain=test_master_gain
        )

        # 4. Simular procesamiento en AudioMixer
        subscription = channel_manager.get_client_subscription(test_client_id)

        # Aplicar ganancias individuales
        gains = subscription.get('gains', {})
        master_gain = subscription.get('master_gain', 1.0)

        processed_audio = audio_data.astype(np.float32)

        # Aplicar ganancias individuales
        for ch in test_channels:
            if ch < processed_audio.shape[1]:
                gain = gains.get(ch, 1.0)
                processed_audio[:, ch] *= gain

        stats_after_individual_gains = calculate_amplitude_stats(processed_audio, "DESPUÉS DE GANANCIAS INDIVIDUALES")

        # Aplicar master gain
        processed_audio *= master_gain
        stats_after_master_gain = calculate_amplitude_stats(processed_audio, "DESPUÉS DE MASTER GAIN")

        # Aplicar limiter suave
        processed_audio = audio_mixer._apply_soft_limiter_professional(processed_audio, threshold=0.85, ratio=3.0)
        stats_after_limiter = calculate_amplitude_stats(processed_audio, "DESPUÉS DE LIMITER")

        # Aplicar headroom de compresión
        compression_headroom = audio_mixer.compression_headroom
        processed_audio *= compression_headroom
        stats_after_compression_headroom = calculate_amplitude_stats(processed_audio, "DESPUÉS DE COMPRESSION HEADROOM")

        # Simular compresión si está habilitada
        if audio_mixer.audio_compressor:
            compressed_audio = audio_mixer.audio_compressor.compress(processed_audio)
            stats_after_compression = {
                "note": f"Audio comprimido a {len(compressed_audio)} bytes",
                "compression_ratio": len(compressed_audio) / (processed_audio.nbytes * 0.01)  # estimado
            }
            logger.info(f"📊 DESPUÉS DE COMPRESIÓN: {len(compressed_audio)} bytes")
        else:
            stats_after_compression = {"note": "Compresión no habilitada"}

        # 5. Análisis de continuidad
        logger.info("\n" + "="*60)
        logger.info("📈 ANÁLISIS DE CONTINUIDAD DE AMPLITUD (AUDIO REAL)")
        logger.info("="*60)

        stages = [
            ("Captura Real", stats_capture),
            ("Ganancias Individuales", stats_after_individual_gains),
            ("Master Gain", stats_after_master_gain),
            ("Limiter", stats_after_limiter),
            ("Compression Headroom", stats_after_compression_headroom),
        ]

        previous_peak = stats_capture["peak"]
        for stage_name, stats in stages:
            if "peak" in stats:
                current_peak = stats["peak"]
                ratio = current_peak / previous_peak if previous_peak > 0 else float('inf')
                db_change = 20 * np.log10(ratio) if ratio > 0 else float('inf')

                status = "🚨 AUMENTO EXTREMO" if ratio > 5.0 else "⚠️ Aumento alto" if ratio > 2.0 else "✅ Normal"
                logger.info(f"{stage_name}: {ratio:.2f}x ({db_change:+.1f}dB) {status}")

                previous_peak = current_peak

        # 6. Verificar clipping
        final_peak = stats_after_compression_headroom["peak"]
        if final_peak > 1.0:
            logger.warning(f"🚨 CLIPPING DETECTADO: Peak = {final_peak:.4f} (> 1.0)")
        elif final_peak > 0.95:
            logger.warning(f"⚠️ Cerca del clipping: Peak = {final_peak:.4f}")
        else:
            logger.info(f"✅ Sin clipping: Peak = {final_peak:.4f}")

        # 7. Análisis adicional para audio real
        if stats_capture["peak"] > 0.1:
            logger.warning(f"⚠️ Señal de entrada muy alta: {stats_capture['peak']:.4f} - posible preamplificación excesiva")

        logger.info("\n🎵 Test con audio real completado exitosamente")

    except Exception as e:
        logger.error(f"❌ Error en test con audio real: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Ejecutar test con datos sintéticos
    test_audio_amplitude_continuity()
    print("\n" + "="*80)
    # Ejecutar test con datos reales
    test_audio_amplitude_continuity_real()