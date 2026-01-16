// opus_codec_jni.cpp - Decodificación Opus nativa para Android
// ✅ FIXED: Conversión correcta Int16 → Float32 (32768.0)

#include <jni.h>
#include <android/log.h>
#include <opus/opus.h>
#include <vector>
#include <memory>
#include <cstring>

#define LOG_TAG "OpusCodecJNI"
#define LOGD(...) __android_log_print(ANDROID_LOG_DEBUG, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)

// ============================================================================
// OPUS DECODER GLOBAL
// ============================================================================

static OpusDecoder* g_opus_decoder = nullptr;
static int g_sample_rate = 48000;
static int g_channels = 2;
static const int MAX_FRAME_SIZE = 5760; // 120ms @ 48kHz
static const int MAX_PACKET_SIZE = 4000;

// ============================================================================
// INICIALIZACIÓN
// ============================================================================

extern "C" JNIEXPORT void JNICALL
Java_com_cepalabsfree_fichatech_audiostream_AudioDecompressor_initOpusDecoderNative(
        JNIEnv* env, jobject thiz, jint sampleRate, jint channels) {

    g_sample_rate = sampleRate;
    g_channels = channels;

    // Destruir decoder anterior si existe
    if (g_opus_decoder) {
        opus_decoder_destroy(g_opus_decoder);
        g_opus_decoder = nullptr;
    }

    // Crear nuevo decoder
    int error = 0;
    g_opus_decoder = opus_decoder_create(g_sample_rate, g_channels, &error);

    if (error != OPUS_OK || !g_opus_decoder) {
        LOGE("❌ Error creando Opus decoder: %s", opus_strerror(error));
        return;
    }

    LOGI("✅ Opus decoder inicializado: %dHz, %dch", g_sample_rate, g_channels);
}

// ============================================================================
// DESCOMPRESIÓN
// ============================================================================

extern "C" JNIEXPORT jfloatArray JNICALL
Java_com_cepalabsfree_fichatech_audiostream_AudioDecompressor_decompressOpusNative(
        JNIEnv* env, jobject thiz, jbyteArray compressedData, jint sampleRate, jint channels) {

    if (!g_opus_decoder) {
        LOGE("❌ Opus decoder no inicializado");
        return env->NewFloatArray(0);
    }

    // Verificar que sample rate y canales coincidan
    if (sampleRate != g_sample_rate || channels != g_channels) {
        LOGE("❌ Sample rate/channels no coinciden: esperado %d/%d, recibido %d/%d",
             g_sample_rate, g_channels, sampleRate, channels);
        return env->NewFloatArray(0);
    }

    jsize compressedSize = env->GetArrayLength(compressedData);

    if (compressedSize <= 0 || compressedSize > MAX_PACKET_SIZE) {
        LOGE("❌ Tamaño de packet inválido: %d", compressedSize);
        return env->NewFloatArray(0);
    }

    // Obtener datos comprimidos
    jbyte* compressedBytes = env->GetByteArrayElements(compressedData, nullptr);
    if (!compressedBytes) {
        LOGE("❌ No se pudo obtener bytes comprimidos");
        return env->NewFloatArray(0);
    }

    // Buffer para decodificación (PCM float32)
    std::vector<float> pcmBuffer(MAX_FRAME_SIZE * g_channels);

    // Decodificar Opus directamente a float32
    int numSamples = opus_decode_float(
            g_opus_decoder,
            reinterpret_cast<const unsigned char*>(compressedBytes),
            compressedSize,
            pcmBuffer.data(),
            MAX_FRAME_SIZE,
            0  // No usar FEC (Forward Error Correction)
    );

    env->ReleaseByteArrayElements(compressedData, compressedBytes, JNI_ABORT);

    if (numSamples < 0) {
        LOGE("❌ Error decodificando Opus: %s", opus_strerror(numSamples));
        return env->NewFloatArray(0);
    }

    if (numSamples == 0) {
        LOGD("⚠️ Opus devolvió 0 samples");
        return env->NewFloatArray(0);
    }

    // No es necesario convertir, ya está en float32 [-1.0, 1.0]
    int totalSamples = numSamples * g_channels;
    jfloatArray result = env->NewFloatArray(totalSamples);

    if (!result) {
        LOGE("❌ No se pudo crear array de resultado");
        return env->NewFloatArray(0);
    }

    env->SetFloatArrayRegion(result, 0, totalSamples, pcmBuffer.data());

    LOGD("✅ Opus decodificado (float32): %d samples (%d frames)", totalSamples, numSamples);

    return result;
}

// ============================================================================
// LIBERACIÓN
// ============================================================================

extern "C" JNIEXPORT void JNICALL
Java_com_cepalabsfree_fichatech_audiostream_AudioDecompressor_releaseOpusDecoder(
        JNIEnv* env, jobject thiz) {

    if (g_opus_decoder) {
        opus_decoder_destroy(g_opus_decoder);
        g_opus_decoder = nullptr;
        LOGI("🧹 Opus decoder liberado");
    }
}

// ============================================================================
// VERSIÓN
// ============================================================================

extern "C" JNIEXPORT jstring JNICALL
Java_com_cepalabsfree_fichatech_audiostream_AudioDecompressor_getOpusVersion(
        JNIEnv* env, jobject thiz) {

    const char* version = opus_get_version_string();
    return env->NewStringUTF(version);
}