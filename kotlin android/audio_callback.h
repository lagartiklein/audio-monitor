// audio_callback.h - FIXED: Recuperación automática de saturación
// Callback para Oboe con protección contra deadlocks

#ifndef FICHATECH_AUDIO_CALLBACK_H
#define FICHATECH_AUDIO_CALLBACK_H

#include <oboe/Oboe.h>
#include <android/log.h>
#include <vector>
#include <mutex>
#include <cstring>
#include <chrono>
#include <atomic>

#define LOG_TAG "AudioCallback"
#define LOGD(...) __android_log_print(ANDROID_LOG_DEBUG, LOG_TAG, __VA_ARGS__)
#define LOGW(...) __android_log_print(ANDROID_LOG_WARN, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

class AudioCallback : public oboe::AudioStreamDataCallback {
private:
    // ✅ FASE 3: Buffer reducido de 2048 → 256 frames para callback directo
    // 2048 frames @ 48kHz = 42.7ms (demasiado para latencia baja)
    // 256 frames @ 48kHz = 5.3ms (adecuado para callback directo de Oboe)
    static constexpr int BUFFER_SIZE_FRAMES = 256;      // ~5.3ms @ 48kHz ⬇️
    static constexpr int TARGET_BUFFER_FRAMES = 128;     // ~2.7ms objetivo
    static constexpr int DROP_THRESHOLD = 192;          // 75% del buffer (era 1536)
    static constexpr int SILENCE_TIMEOUT_MS = 5000;      // ✅ 5s antes de reset
    static constexpr int CORRUPTION_CHECK_INTERVAL = 100; // Cada 100 callbacks

    std::vector<float> circularBuffer;
    std::mutex bufferMutex;

    int writePos = 0;
    int readPos = 0;
    std::atomic<int> availableFrames{0};
    int channelCount = 2;

    // Estadísticas RF
    std::atomic<int> underrunCount{0};
    std::atomic<int> dropCount{0};
    std::atomic<int64_t> lastAudioTime{0};
    std::atomic<bool> wasSilent{false};

    // ✅ NUEVO: Detección de corrupción
    std::atomic<int> callbackCount{0};
    std::atomic<int> resetCount{0};
    std::atomic<int64_t> lastResetTime{0};

public:
    explicit AudioCallback(int channels) : channelCount(channels) {
        circularBuffer.resize(BUFFER_SIZE_FRAMES * channelCount, 0.0f);
        lastAudioTime = getCurrentTimeMillis();
        LOGD("✅ AudioCallback RF: %d canales, buffer %d frames (~%dms)",
                channels, BUFFER_SIZE_FRAMES,
                BUFFER_SIZE_FRAMES * 1000 / 48000);
    }

    /**
     * ✅ FIXED: Callback con recuperación automática
     */
    oboe::DataCallbackResult onAudioReady(
            oboe::AudioStream *audioStream,
            void *audioData,
            int32_t numFrames) override {

        auto *outputBuffer = static_cast<float *>(audioData);
        const int samplesNeeded = numFrames * channelCount;

        std::lock_guard<std::mutex> lock(bufferMutex);

        callbackCount++;

        // ✅ 1. Validación periódica de sanidad
        if (callbackCount % CORRUPTION_CHECK_INTERVAL == 0) {
            if (!validateBufferState()) {
                LOGE("💥 Corrupción detectada, reseteando...");
                forceReset();
                std::memset(outputBuffer, 0, samplesNeeded * sizeof(float));
                return oboe::DataCallbackResult::Continue;
            }
        }

        // ✅ 2. Manejo de buffer vacío con timeout
        if (availableFrames == 0) {
            std::memset(outputBuffer, 0, samplesNeeded * sizeof(float));
            underrunCount++;

            int64_t silentTime = getCurrentTimeMillis() - lastAudioTime;

            // ✅ Reset automático después de silencio prolongado
            if (silentTime > SILENCE_TIMEOUT_MS && wasSilent) {
                int64_t timeSinceLastReset = getCurrentTimeMillis() - lastResetTime;

                // Evitar resets en bucle (mínimo 10s entre resets)
                if (timeSinceLastReset > 10000) {
                    LOGW("🔄 Silencio prolongado (%lldms), reseteando buffer", silentTime);
                    forceReset();
                }
            }

            wasSilent = true;
            return oboe::DataCallbackResult::Continue;
        }

        // ✅ 3. Validar readPos antes de leer
        if (readPos >= static_cast<int>(circularBuffer.size())) {
            LOGE("💥 readPos corrupto: %d >= %zu", readPos, circularBuffer.size());
            forceReset();
            std::memset(outputBuffer, 0, samplesNeeded * sizeof(float));
            return oboe::DataCallbackResult::Continue;
        }

        // ✅ 4. Reproducir audio con seguridad
        int framesToPlay = std::min(availableFrames.load(), numFrames);
        int samplesToPlay = framesToPlay * channelCount;

        for (int i = 0; i < samplesToPlay; i++) {
            outputBuffer[i] = circularBuffer[readPos];
            readPos = (readPos + 1) % static_cast<int>(circularBuffer.size());
        }

        // Silencio para frames faltantes
        if (samplesToPlay < samplesNeeded) {
            std::memset(outputBuffer + samplesToPlay, 0,
                    (samplesNeeded - samplesToPlay) * sizeof(float));
        }

        availableFrames -= framesToPlay;

        // ✅ 5. Actualizar timestamp de último audio válido
        if (framesToPlay > 0) {
            lastAudioTime = getCurrentTimeMillis();
        }

        // Log de recuperación
        if (wasSilent && framesToPlay > 0) {
            LOGD("🔊 Audio recuperado después de %d underruns", underrunCount.load());
            wasSilent = false;
        }

        // ✅ 6. Drop preventivo si buffer creció demasiado
        if (availableFrames > DROP_THRESHOLD) {
            int excess = availableFrames - TARGET_BUFFER_FRAMES;
            if (excess > 0) {
                readPos = (readPos + excess * channelCount) % static_cast<int>(circularBuffer.size());
                availableFrames -= excess;
                dropCount += excess;

                if (excess > 256) {
                    LOGD("🗑️ Drop preventivo: %d frames (quedan: %d)",
                            excess, availableFrames.load());
                }
            }
        }

        return oboe::DataCallbackResult::Continue;
    }

    /**
     * ✅ FIXED: Escritura con validación estricta de límites
     */
    int writeAudio(const float *data, int numFrames) {
        std::lock_guard<std::mutex> lock(bufferMutex);

        lastAudioTime = getCurrentTimeMillis();

        const int samplesTotal = numFrames * channelCount;

        // ✅ 1. Calcular espacio real disponible
        int freeFrames = BUFFER_SIZE_FRAMES - availableFrames;

        // ✅ 2. Si no hay espacio suficiente, vaciar agresivamente
        if (freeFrames < numFrames) {
            // Estrategia: Vaciar el 75% del buffer para dar margen
            int framesToClear = (availableFrames * 3) / 4;

            if (framesToClear > 0) {
                LOGW("🗑️ Buffer saturado (%d frames), limpiando %d frames",
                        availableFrames.load(), framesToClear);

                readPos = (readPos + framesToClear * channelCount) % static_cast<int>(circularBuffer.size());
                availableFrames -= framesToClear;
                dropCount += framesToClear;

                // Recalcular espacio
                freeFrames = BUFFER_SIZE_FRAMES - availableFrames;
            }
        }

        // ✅ 3. Calcular cuánto podemos escribir con seguridad
        int framesToWrite = std::min(numFrames, freeFrames);

        // ✅ 4. Verificación crítica: nunca escribir si no hay espacio
        if (framesToWrite <= 0) {
            LOGW("❌ Buffer completamente lleno, descartando %d frames", numFrames);
            dropCount += numFrames;
            return 0;
        }

        int samplesToWrite = framesToWrite * channelCount;

        // ✅ 5. Escribir con validación de límites
        for (int i = 0; i < samplesToWrite; i++) {
            circularBuffer[writePos] = data[i];
            writePos = (writePos + 1) % static_cast<int>(circularBuffer.size());
        }

        // ✅ 6. Actualizar contador SOLO con lo realmente escrito
        availableFrames += framesToWrite;

        // ✅ 7. Validación post-escritura
        if (availableFrames > BUFFER_SIZE_FRAMES) {
            LOGE("💥 CORRUPCIÓN: availableFrames=%d > MAX=%d",
                    availableFrames.load(), BUFFER_SIZE_FRAMES);
            forceReset();
            return 0;
        }

        return framesToWrite;
    }

    /**
     * ✅ NUEVO: Validar estado del buffer
     */
    bool validateBufferState() {
        if (availableFrames < 0 || availableFrames > BUFFER_SIZE_FRAMES) {
            LOGE("❌ availableFrames fuera de rango: %d", availableFrames.load());
            return false;
        }

        if (readPos < 0 || readPos >= static_cast<int>(circularBuffer.size())) {
            LOGE("❌ readPos fuera de rango: %d", readPos);
            return false;
        }

        if (writePos < 0 || writePos >= static_cast<int>(circularBuffer.size())) {
            LOGE("❌ writePos fuera de rango: %d", writePos);
            return false;
        }

        return true;
    }

    /**
     * ✅ NUEVO: Reset forzado del buffer
     */
    void forceReset() {
        std::fill(circularBuffer.begin(), circularBuffer.end(), 0.0f);
        writePos = 0;
        readPos = 0;
        availableFrames = 0;
        underrunCount = 0;
        dropCount = 0;
        wasSilent = false;
        resetCount++;
        lastResetTime = getCurrentTimeMillis();

        LOGW("🔄 Buffer reseteado (reset #%d)", resetCount.load());
    }

    /**
     * Limpia el buffer (versión pública)
     */
    void clear() {
        std::lock_guard<std::mutex> lock(bufferMutex);
        forceReset();
    }

    int getAvailableFrames() const {
        return availableFrames.load();
    }

    int getUnderrunCount() const {
        return underrunCount.load();
    }

    float getBufferUsagePercent() const {
        return (static_cast<float>(availableFrames) / BUFFER_SIZE_FRAMES) * 100.0f;
    }

    float getLatencyMs() const {
        return (static_cast<float>(availableFrames) / 48000.0f) * 1000.0f;
    }

    bool isReceivingAudio() const {
        return (getCurrentTimeMillis() - lastAudioTime) < 2000;
    }

    int getDropCount() const {
        return dropCount.load();
    }

    int getResetCount() const {
        return resetCount.load();
    }

    /**
     * ✅ NUEVO: Estructura de estadísticas RF completa
     */
    struct RFStats {
        int availableFrames;
        float latencyMs;
        bool isReceiving;
        int underruns;
        int drops;
        float usagePercent;
        int resets;
        int64_t lastAudioTimeMs;
        int callbackCount;
    };

    RFStats getRFStats() const {
        RFStats stats;
        stats.availableFrames = availableFrames.load();
        stats.latencyMs = getLatencyMs();
        stats.isReceiving = isReceivingAudio();
        stats.underruns = underrunCount.load();
        stats.drops = dropCount.load();
        stats.usagePercent = getBufferUsagePercent();
        stats.resets = resetCount.load();
        stats.lastAudioTimeMs = lastAudioTime.load();
        stats.callbackCount = callbackCount.load();
        return stats;
    }

private:
    int64_t getCurrentTimeMillis() const {
        using namespace std::chrono;
        return duration_cast<milliseconds>(
                system_clock::now().time_since_epoch()
        ).count();
    }
};

#endif // FICHATECH_AUDIO_CALLBACK_H