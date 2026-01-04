// native_audio_engine.cpp - VERSIÓN FASE 3 OPTIMIZADA
// Bridge JNI entre Kotlin y Oboe - ULTRA LOW LATENCY + NEON SIMD

#include <jni.h>
#include <oboe/Oboe.h>
#include <android/log.h>
#include <memory>
#include <map>
#include "audio_callback.h"

// ✅ FASE 3: NEON SIMD para ARM processors
#if defined(__ARM_NEON__) || defined(__ARM_NEON)
#include <arm_neon.h>
#define HAS_NEON 1
#else
#define HAS_NEON 0
#endif

#define LOG_TAG "NativeAudioEngine"
#define LOGD(...) __android_log_print(ANDROID_LOG_DEBUG, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)
#define LOGW(...) __android_log_print(ANDROID_LOG_WARN, LOG_TAG, __VA_ARGS__)

struct AudioStreamWrapper {
    std::shared_ptr<oboe::AudioStream> stream;
    std::shared_ptr<AudioCallback> callback;
    int channelId;

    AudioStreamWrapper(std::shared_ptr<oboe::AudioStream> s,
            std::shared_ptr<AudioCallback> c,
            int id)
            : stream(std::move(s)), callback(std::move(c)), channelId(id) {}
};

struct AudioEngine {
    int32_t sampleRate;
    int32_t channels;
    std::map<int, std::shared_ptr<AudioStreamWrapper>> streams;

    AudioEngine(int32_t rate, int32_t ch)
            : sampleRate(rate), channels(ch) {
        LOGI("✅ AudioEngine creado: %dHz, %d canales", rate, ch);
    }

    ~AudioEngine() {
        LOGI("🗑️ AudioEngine destruyendo %zu streams...", streams.size());
        streams.clear();
    }
};

extern "C" {

/**
 * ✅ CORREGIDO: Firma sin bufferSize (se configura después)
 */
JNIEXPORT jlong JNICALL
Java_com_cepalabsfree_fichatech_audiostream_OboeAudioRenderer_nativeCreateEngine(
        JNIEnv *env, jobject thiz, jint sampleRate, jint channels) {

    try {
        auto *engine = new AudioEngine(sampleRate, channels);
        LOGD("✅ Engine handle: %p", engine);
        LOGD("   Sample Rate: %d Hz", sampleRate);
        LOGD("   Channels: %d", channels);
        return reinterpret_cast<jlong>(engine);
    } catch (const std::exception &e) {
        LOGE("❌ Error creando engine: %s", e.what());
        return 0;
    }
}

/**
 * ✅ SIMPLIFICADO: Stream estándar con MMAP automático
 *
 * IMPORTANTE: Oboe activa MMAP automáticamente cuando:
 * - Performance mode = LowLatency
 * - Sharing mode = Exclusive
 * - El dispositivo lo soporta
 *
 * NO necesitamos lógica custom para MMAP.
 */
JNIEXPORT jlong JNICALL
Java_com_cepalabsfree_fichatech_audiostream_OboeAudioRenderer_nativeCreateStream(
        JNIEnv *env, jobject thiz, jlong engineHandle, jint channelId) {

    auto *engine = reinterpret_cast<AudioEngine*>(engineHandle);
    if (!engine) {
        LOGE("❌ Engine handle inválido");
        return 0;
    }

    try {
        // ✅ Callback con buffer optimizado (512 frames)
        auto callback = std::make_shared<AudioCallback>(engine->channels);

        oboe::AudioStreamBuilder builder;

        // ✅ CONFIGURACIÓN ULTRA-BAJA LATENCIA
        builder.setDirection(oboe::Direction::Output)
                ->setFormat(oboe::AudioFormat::Float)
                ->setSampleRate(engine->sampleRate)
                ->setChannelCount(engine->channels)
                ->setDataCallback(callback.get())
                ->setUsage(oboe::Usage::Media)
                ->setContentType(oboe::ContentType::Music)
                        // ✅ CRÍTICO: Performance mode y sharing mode
                ->setPerformanceMode(oboe::PerformanceMode::LowLatency)
                ->setSharingMode(oboe::SharingMode::Exclusive);  // Activa MMAP si está disponible

        // ✅ NO especificar buffer capacity ni frames per callback
        // Esto permite que Oboe use los valores óptimos del dispositivo

        std::shared_ptr<oboe::AudioStream> stream;
        oboe::Result result = builder.openStream(stream);

        if (result != oboe::Result::OK) {
            LOGE("❌ Error abriendo stream canal %d: %s",
                    channelId, oboe::convertToText(result));
            return 0;
        }

        // ✅ Ajustar buffer size al óptimo (2x burst size)
        int32_t framesPerBurst = stream->getFramesPerBurst();
        int32_t optimalBufferSize = framesPerBurst * 2;

        oboe::ResultWithValue<int32_t> bufferResult =
                stream->setBufferSizeInFrames(optimalBufferSize);

        if (bufferResult.error() == oboe::Result::OK) {
            LOGI("📦 Buffer size: %d frames (burst=%d)",
                    bufferResult.value(), framesPerBurst);
        }

        auto wrapper = std::make_shared<AudioStreamWrapper>(
                stream, callback, channelId
        );
        engine->streams[channelId] = wrapper;

        // ✅ MMAP se detecta automáticamente
        bool isUsingMMAP = (stream->getSharingMode() == oboe::SharingMode::Exclusive);

        // ✅ Log detallado de configuración
        LOGI("✅ Stream canal %d creado %s",
                channelId, isUsingMMAP ? "con MMAP ⚡" : "(Legacy mode)");
        LOGI("   Sample Rate: %d Hz", stream->getSampleRate());
        LOGI("   Buffer Size: %d frames", stream->getBufferSizeInFrames());
        LOGI("   Frames/Burst: %d", framesPerBurst);
        LOGI("   Performance: %s",
                stream->getPerformanceMode() == oboe::PerformanceMode::LowLatency ?
                        "LOW_LATENCY" : "POWER_SAVING");
        LOGI("   Sharing: %s",
                stream->getSharingMode() == oboe::SharingMode::Exclusive ?
                        "EXCLUSIVE (MMAP)" : "SHARED");

        // ✅ Calcular latencia estimada
        float latencyMs = (float)stream->getBufferSizeInFrames() * 1000.0f / stream->getSampleRate();
        LOGI("   Latencia estimada: %.1f ms", latencyMs);

        return reinterpret_cast<jlong>(wrapper.get());

    } catch (const std::exception &e) {
        LOGE("❌ Excepción creando stream: %s", e.what());
        return 0;
    }
}

JNIEXPORT void JNICALL
Java_com_cepalabsfree_fichatech_audiostream_OboeAudioRenderer_nativeStartStream(
        JNIEnv *env, jobject thiz, jlong streamHandle) {

    auto *wrapper = reinterpret_cast<AudioStreamWrapper*>(streamHandle);
    if (!wrapper || !wrapper->stream) {
        LOGE("❌ Stream handle inválido");
        return;
    }

    oboe::Result result = wrapper->stream->requestStart();
    if (result == oboe::Result::OK) {
        bool isMMAP = (wrapper->stream->getSharingMode() == oboe::SharingMode::Exclusive);
        LOGD("▶️ Stream canal %d iniciado (%s)",
                wrapper->channelId,
                isMMAP ? "MMAP" : "Legacy");
    } else {
        LOGE("❌ Error iniciando stream: %s", oboe::convertToText(result));
    }
}

JNIEXPORT jint JNICALL
Java_com_cepalabsfree_fichatech_audiostream_OboeAudioRenderer_nativeWriteAudio(
        JNIEnv *env, jobject thiz, jlong streamHandle, jfloatArray buffer) {

    auto *wrapper = reinterpret_cast<AudioStreamWrapper*>(streamHandle);
    if (!wrapper || !wrapper->callback) {
        LOGE("❌ Wrapper inválido");
        return 0;
    }

    jsize length = env->GetArrayLength(buffer);
    jfloat *data = env->GetFloatArrayElements(buffer, nullptr);

    if (!data) {
        LOGE("❌ No se pudo obtener datos del buffer");
        return 0;
    }

    int framesWritten = wrapper->callback->writeAudio(
            data, length / wrapper->stream->getChannelCount()
    );

    env->ReleaseFloatArrayElements(buffer, data, JNI_ABORT);

    return framesWritten * wrapper->stream->getChannelCount();
}

JNIEXPORT void JNICALL
Java_com_cepalabsfree_fichatech_audiostream_OboeAudioRenderer_nativeStopStream(
        JNIEnv *env, jobject thiz, jlong streamHandle) {

    auto *wrapper = reinterpret_cast<AudioStreamWrapper*>(streamHandle);
    if (!wrapper || !wrapper->stream) {
        return;
    }

    oboe::Result result = wrapper->stream->requestStop();
    if (result == oboe::Result::OK) {
        LOGD("⏸️ Stream canal %d detenido", wrapper->channelId);
    }
}

JNIEXPORT jfloat JNICALL
Java_com_cepalabsfree_fichatech_audiostream_OboeAudioRenderer_nativeGetLatency(
        JNIEnv *env, jobject thiz, jlong streamHandle) {

    auto *wrapper = reinterpret_cast<AudioStreamWrapper*>(streamHandle);
    if (!wrapper || !wrapper->stream) {
        return 0.0f;
    }

    // ✅ Obtener latencia real del stream
    oboe::ResultWithValue<double> result = wrapper->stream->calculateLatencyMillis();

    if (result.error() == oboe::Result::OK) {
        return static_cast<jfloat>(result.value());
    }

    // Fallback: calcular basado en buffer size
    int bufferSize = wrapper->stream->getBufferSizeInFrames();
    int sampleRate = wrapper->stream->getSampleRate();
    return (static_cast<float>(bufferSize) / sampleRate) * 1000.0f;
}

JNIEXPORT jint JNICALL
Java_com_cepalabsfree_fichatech_audiostream_OboeAudioRenderer_nativeGetBufferStats(
        JNIEnv *env, jobject thiz, jlong streamHandle) {

    auto *wrapper = reinterpret_cast<AudioStreamWrapper*>(streamHandle);
    if (!wrapper || !wrapper->callback) {
        return 0;
    }

    return wrapper->callback->getAvailableFrames();
}

JNIEXPORT jintArray JNICALL
Java_com_cepalabsfree_fichatech_audiostream_OboeAudioRenderer_nativeGetRFStats(
        JNIEnv *env, jobject thiz, jlong streamHandle) {

    auto *wrapper = reinterpret_cast<AudioStreamWrapper*>(streamHandle);
    if (!wrapper || !wrapper->callback) {
        jintArray result = env->NewIntArray(7);
        jint defaultValues[7] = {0, 0, 0, 0, 0, 0, 0};
        env->SetIntArrayRegion(result, 0, 7, defaultValues);
        return result;
    }

    auto stats = wrapper->callback->getRFStats();

    jint statsArray[7];
    statsArray[0] = stats.availableFrames;
    statsArray[1] = static_cast<jint>(stats.latencyMs);
    statsArray[2] = stats.isReceiving ? 1 : 0;
    statsArray[3] = stats.underruns;
    statsArray[4] = stats.drops;
    statsArray[5] = static_cast<jint>(stats.usagePercent);
    statsArray[6] = stats.resets;

    jintArray result = env->NewIntArray(7);
    env->SetIntArrayRegion(result, 0, 7, statsArray);
    return result;
}

JNIEXPORT void JNICALL
Java_com_cepalabsfree_fichatech_audiostream_OboeAudioRenderer_nativeClearBuffer(
        JNIEnv *env, jobject thiz, jlong streamHandle) {

    auto *wrapper = reinterpret_cast<AudioStreamWrapper*>(streamHandle);
    if (wrapper && wrapper->callback) {
        wrapper->callback->clear();
        LOGD("🧹 Buffer canal %d limpiado", wrapper->channelId);
    }
}

JNIEXPORT void JNICALL
Java_com_cepalabsfree_fichatech_audiostream_OboeAudioRenderer_nativeDestroyStream(
        JNIEnv *env, jobject thiz, jlong streamHandle) {

    auto *wrapper = reinterpret_cast<AudioStreamWrapper*>(streamHandle);
    if (!wrapper) return;

    bool isMMAP = false;
    if (wrapper->stream) {
        isMMAP = (wrapper->stream->getSharingMode() == oboe::SharingMode::Exclusive);
    }

    LOGD("🗑️ Destruyendo stream canal %d (%s)",
            wrapper->channelId,
            isMMAP ? "MMAP" : "Legacy");

    if (wrapper->stream) {
        wrapper->stream->requestStop();
        wrapper->stream->close();
    }
}

JNIEXPORT void JNICALL
Java_com_cepalabsfree_fichatech_audiostream_OboeAudioRenderer_nativeDestroyEngine(
        JNIEnv *env, jobject thiz, jlong engineHandle) {

    auto *engine = reinterpret_cast<AudioEngine*>(engineHandle);
    if (engine) {
        LOGI("🗑️ Destruyendo engine con %zu streams", engine->streams.size());
        delete engine;
    }
}

/**
 * ✅ Configurar buffer size para baja latencia
 */
JNIEXPORT void JNICALL
Java_com_cepalabsfree_fichatech_audiostream_OboeAudioRenderer_nativeSetBufferSize(
        JNIEnv *env, jobject thiz, jlong streamHandle, jint bufferSize) {

    auto *wrapper = reinterpret_cast<AudioStreamWrapper*>(streamHandle);
    if (!wrapper || !wrapper->stream) {
        LOGE("❌ Stream handle inválido para setBufferSize");
        return;
    }

    oboe::ResultWithValue<int32_t> result =
            wrapper->stream->setBufferSizeInFrames(bufferSize);

    if (result.error() == oboe::Result::OK) {
        LOGD("📦 Buffer size: %d frames (canal %d)",
                result.value(), wrapper->channelId);
    } else {
        LOGE("❌ Error configurando buffer size: %s",
                oboe::convertToText(result.error()));
    }
}

// ✅ FASE 3: Funciones optimizadas con NEON SIMD
#if HAS_NEON

/**
 * Procesar audio estéreo con NEON SIMD
 * Aplica gain L/R y soft-clip en una sola pasada
 * ~4x más rápido que versión escalar
 */
inline void processAudioNEON(float* dst, const float* src, float gainL, float gainR, int samples) {
    // Vectores de ganancias
    float32x4_t vGainL = vdupq_n_f32(gainL);
    float32x4_t vGainR = vdupq_n_f32(gainR);
    
    // Límites para soft-clip [-1.0, 1.0]
    float32x4_t vMin = vdupq_n_f32(-1.0f);
    float32x4_t vMax = vdupq_n_f32(1.0f);
    
    int i = 0;
    const int simdLimit = (samples / 4) * 4;
    
    // Procesamiento vectorizado: 4 samples a la vez
    for (; i < simdLimit; i += 4) {
        // Cargar 4 samples mono
        float32x4_t vSrc = vld1q_f32(src + i);
        
        // Multiplicar por ganancias L/R
        float32x4_t vLeft = vmulq_f32(vSrc, vGainL);
        float32x4_t vRight = vmulq_f32(vSrc, vGainR);
        
        // Soft-clip con vmin/vmax (saturación rápida)
        vLeft = vmaxq_f32(vMin, vminq_f32(vMax, vLeft));
        vRight = vmaxq_f32(vMin, vminq_f32(vMax, vRight));
        
        // Interleave L/R para salida estéreo
        float32x4x2_t vInterleaved = vzipq_f32(vLeft, vRight);
        
        // Almacenar 8 valores (4 pares L/R)
        vst1q_f32(dst + i*2, vInterleaved.val[0]);
        vst1q_f32(dst + i*2 + 4, vInterleaved.val[1]);
    }
    
    // Procesar samples restantes (escalar)
    for (; i < samples; i++) {
        float sample = src[i];
        float left = sample * gainL;
        float right = sample * gainR;
        
        // Clamp [-1.0, 1.0]
        left = (left < -1.0f) ? -1.0f : (left > 1.0f ? 1.0f : left);
        right = (right < -1.0f) ? -1.0f : (right > 1.0f ? 1.0f : right);
        
        dst[i*2] = left;
        dst[i*2 + 1] = right;
    }
}

/**
 * Conversión Int16 -> Float32 con NEON (4x más rápido)
 */
inline void convertInt16ToFloatNEON(float* dst, const int16_t* src, int samples) {
    const float scale = 1.0f / 32768.0f;
    float32x4_t vScale = vdupq_n_f32(scale);
    
    int i = 0;
    const int simdLimit = (samples / 8) * 8;
    
    // Procesar 8 samples a la vez
    for (; i < simdLimit; i += 8) {
        // Cargar 8 int16
        int16x8_t vSrc = vld1q_s16(src + i);
        
        // Convertir a int32 (necesario para vcvtq_f32)
        int32x4_t vLow = vmovl_s16(vget_low_s16(vSrc));
        int32x4_t vHigh = vmovl_s16(vget_high_s16(vSrc));
        
        // Convertir a float y escalar
        float32x4_t vFloatLow = vcvtq_f32_s32(vLow);
        float32x4_t vFloatHigh = vcvtq_f32_s32(vHigh);
        
        vFloatLow = vmulq_f32(vFloatLow, vScale);
        vFloatHigh = vmulq_f32(vFloatHigh, vScale);
        
        // Almacenar
        vst1q_f32(dst + i, vFloatLow);
        vst1q_f32(dst + i + 4, vFloatHigh);
    }
    
    // Resto
    for (; i < samples; i++) {
        dst[i] = src[i] * scale;
    }
}

#endif // HAS_NEON

} // extern "C"