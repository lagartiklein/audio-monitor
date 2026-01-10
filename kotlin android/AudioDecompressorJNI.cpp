/**
 * AudioDecompressorJNI.cpp - Implementación JNI para descompresión Opus
 * Compatible con AudioDecompressor.kt
 */

#include <jni.h>
#include <opus/opus.h>
#include <android/log.h>
#include <cstring>
#include <memory>

#define LOG_TAG "AudioDecompressorJNI"
#define LOGD(...) __android_log_print(ANDROID_LOG_DEBUG, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)

extern "C" {

JNIEXPORT jfloatArray JNICALL
Java_com_cepalabsfree_fichatech_audiostream_AudioDecompressor_decompressOpusNative(
        JNIEnv *env, jobject thiz, jbyteArray compressedData, jint sampleRate, jint channels) {

    LOGD("🎵 Starting Opus decompression: sampleRate=%d, channels=%d", sampleRate, channels);

    // Obtener datos comprimidos
    jsize compressedSize = env->GetArrayLength(compressedData);
    jbyte* compressedBytes = env->GetByteArrayElements(compressedData, nullptr);

    if (!compressedBytes) {
        LOGE("❌ Failed to get compressed data array");
        return env->NewFloatArray(0);
    }

    // Crear decoder Opus
    int error;
    OpusDecoder* decoder = opus_decoder_create(sampleRate, channels, &error);

    if (error != OPUS_OK) {
        LOGE("❌ Failed to create Opus decoder: %s", opus_strerror(error));
        env->ReleaseByteArrayElements(compressedData, compressedBytes, JNI_ABORT);
        return env->NewFloatArray(0);
    }

    // Calcular tamaño máximo del frame descomprimido
    // Para Opus, un frame típico es de 20ms
    int frameSize = sampleRate / 50; // 20ms frame
    int maxOutputSize = frameSize * channels;

    // Buffer para salida PCM
    std::unique_ptr<float[]> outputBuffer(new float[maxOutputSize]);

    // Descomprimir
    int decodedSamples = opus_decode_float(
        decoder,
        reinterpret_cast<unsigned char*>(compressedBytes),
        compressedSize,
        outputBuffer.get(),
        frameSize,
        0 // no FEC
    );

    // Limpiar
    env->ReleaseByteArrayElements(compressedData, compressedBytes, JNI_ABORT);
    opus_decoder_destroy(decoder);

    if (decodedSamples < 0) {
        LOGE("❌ Opus decode error: %s", opus_strerror(decodedSamples));
        return env->NewFloatArray(0);
    }

    // Crear array de floats para Java
    int actualSamples = decodedSamples * channels;
    jfloatArray result = env->NewFloatArray(actualSamples);

    if (result) {
        env->SetFloatArrayRegion(result, 0, actualSamples, outputBuffer.get());
        LOGD("✅ Opus decompression successful: %d samples", actualSamples);
    } else {
        LOGE("❌ Failed to create float array");
        result = env->NewFloatArray(0);
    }

    return result;
}

} // extern "C"