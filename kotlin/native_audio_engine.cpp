// native_audio_engine.cpp - FIXED
// Bridge JNI entre Kotlin y Oboe con stats de resets

#include <jni.h>
#include <oboe/Oboe.h>
#include <android/log.h>
#include <memory>
#include <map>
#include "audio_callback.h"

#define LOG_TAG "NativeAudioEngine"
#define LOGD(...) __android_log_print(ANDROID_LOG_DEBUG, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)

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

    AudioEngine(int32_t rate, int32_t ch) : sampleRate(rate), channels(ch) {
        LOGI("✅ AudioEngine creado: %dHz, %d canales", rate, ch);
    }

    ~AudioEngine() {
        LOGI("🗑️ AudioEngine destruyendo %zu streams...", streams.size());
        streams.clear();
    }
};

extern "C" {

JNIEXPORT jlong JNICALL
Java_com_cepalabsfree_fichatech_audiostream_OboeAudioRenderer_nativeCreateEngine(
        JNIEnv *env, jobject thiz, jint sampleRate, jint channels) {

    try {
        auto *engine = new AudioEngine(sampleRate, channels);
        LOGD("✅ Engine handle: %p", engine);
        return reinterpret_cast<jlong>(engine);
    } catch (const std::exception &e) {
        LOGE("❌ Error creando engine: %s", e.what());
        return 0;
    }
}

JNIEXPORT jlong JNICALL
Java_com_cepalabsfree_fichatech_audiostream_OboeAudioRenderer_nativeCreateStream(
        JNIEnv *env, jobject thiz, jlong engineHandle, jint channelId) {

    auto *engine = reinterpret_cast<AudioEngine*>(engineHandle);
    if (!engine) {
        LOGE("❌ Engine handle inválido");
        return 0;
    }

    try {
        auto callback = std::make_shared<AudioCallback>(engine->channels);

        oboe::AudioStreamBuilder builder;
        builder.setDirection(oboe::Direction::Output)
                ->setPerformanceMode(oboe::PerformanceMode::LowLatency)
                ->setSharingMode(oboe::SharingMode::Exclusive)
                ->setFormat(oboe::AudioFormat::Float)
                ->setSampleRate(engine->sampleRate)
                ->setChannelCount(engine->channels)
                ->setDataCallback(callback.get())
                ->setUsage(oboe::Usage::Media)
                ->setContentType(oboe::ContentType::Music);

        std::shared_ptr<oboe::AudioStream> stream;
        oboe::Result result = builder.openStream(stream);

        if (result != oboe::Result::OK) {
            LOGE("❌ Error abriendo stream canal %d: %s",
                    channelId, oboe::convertToText(result));
            return 0;
        }

        auto wrapper = std::make_shared<AudioStreamWrapper>(stream, callback, channelId);
        engine->streams[channelId] = wrapper;

        LOGI("✅ Stream canal %d creado", channelId);
        LOGI("   Sample Rate: %d Hz", stream->getSampleRate());
        LOGI("   Buffer Size: %d frames", stream->getBufferSizeInFrames());
        LOGI("   Frames/Burst: %d", stream->getFramesPerBurst());

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
        LOGD("▶️ Stream canal %d iniciado", wrapper->channelId);
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

    int framesWritten = wrapper->callback->writeAudio(data, length / wrapper->stream->getChannelCount());

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

    oboe::ResultWithValue<double> result = wrapper->stream->calculateLatencyMillis();

    if (result.error() == oboe::Result::OK) {
        return static_cast<jfloat>(result.value());
    }

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

/**
 * ✅ FIXED: Ahora incluye el contador de resets (índice 6)
 */
JNIEXPORT jintArray JNICALL
Java_com_cepalabsfree_fichatech_audiostream_OboeAudioRenderer_nativeGetRFStats(
        JNIEnv *env, jobject thiz, jlong streamHandle) {

    auto *wrapper = reinterpret_cast<AudioStreamWrapper*>(streamHandle);
    if (!wrapper || !wrapper->callback) {
        jintArray result = env->NewIntArray(7);  // ✅ Ahora son 7 valores
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
    statsArray[6] = stats.resets;  // ✅ NUEVO

    jintArray result = env->NewIntArray(7);
    env->SetIntArrayRegion(result, 0, 7, statsArray);
    return result;
}

/**
 * ✅ Limpia el buffer del stream (llama a forceReset)
 */
JNIEXPORT void JNICALL
Java_com_cepalabsfree_fichatech_audiostream_OboeAudioRenderer_nativeClearBuffer(
        JNIEnv *env, jobject thiz, jlong streamHandle) {

    auto *wrapper = reinterpret_cast<AudioStreamWrapper*>(streamHandle);
    if (wrapper && wrapper->callback) {
        wrapper->callback->clear();
        LOGD("🧹 Buffer canal %d limpiado (reset forzado)", wrapper->channelId);
    }
}

JNIEXPORT void JNICALL
Java_com_cepalabsfree_fichatech_audiostream_OboeAudioRenderer_nativeDestroyStream(
        JNIEnv *env, jobject thiz, jlong streamHandle) {

    auto *wrapper = reinterpret_cast<AudioStreamWrapper*>(streamHandle);
    if (!wrapper) return;

    LOGD("🗑️ Destruyendo stream canal %d", wrapper->channelId);

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

// ✅ NUEVO: Configurar tamaño de buffer para baja latencia
JNIEXPORT void JNICALL
Java_com_cepalabsfree_fichatech_audiostream_OboeAudioRenderer_nativeSetBufferSize(
        JNIEnv *env, jobject thiz, jlong streamHandle, jint bufferSize) {

    auto *wrapper = reinterpret_cast<AudioStreamWrapper*>(streamHandle);
    if (!wrapper || !wrapper->stream) {
        LOGE("❌ Stream handle inválido para setBufferSize");
        return;
    }

    oboe::ResultWithValue<int32_t> result = wrapper->stream->setBufferSizeInFrames(bufferSize);

    if (result.error() == oboe::Result::OK) {
        LOGD("📏 Buffer size establecido: %d frames para canal %d", result.value(), wrapper->channelId);
    } else {
        LOGE("❌ Error configurando buffer size: %s", oboe::convertToText(result.error()));
    }
}

} // extern "C"