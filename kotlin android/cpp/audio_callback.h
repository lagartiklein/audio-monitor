// audio_callback.h - ULTRA LOW LATENCY VERSION - FASE 2 OPTIMIZADO
// Callback para Oboe con buffer circular optimizado, prefetch y mínima contención

#ifndef FICHATECH_AUDIO_CALLBACK_H
#define FICHATECH_AUDIO_CALLBACK_H

#include <oboe/Oboe.h>
#include <android/log.h>
#include <vector>
#include <mutex>
#include <cstring>
#include <chrono>
#include <atomic>

// ✅ FASE 2: Prefetch para mejor rendimiento de caché L1/L2
#if defined(__GNUC__) || defined(__clang__)
#define PREFETCH_READ(addr)  __builtin_prefetch((addr), 0, 3)
#define PREFETCH_WRITE(addr) __builtin_prefetch((addr), 1, 3)
#define LIKELY(x)   __builtin_expect(!!(x), 1)
#define UNLIKELY(x) __builtin_expect(!!(x), 0)
#else
#define PREFETCH_READ(addr)
#define PREFETCH_WRITE(addr)
#define LIKELY(x)   (x)
#define UNLIKELY(x) (x)
#endif

// Macros de log para Android; facilitan escribir mensajes con niveles
#define LOG_TAG "AudioCallback"
#define LOGD(...) __android_log_print(ANDROID_LOG_DEBUG, LOG_TAG, __VA_ARGS__)
#define LOGW(...) __android_log_print(ANDROID_LOG_WARN, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

// Clase que implementa AudioStreamDataCallback de Oboe.
// ✅ OPTIMIZADO: Buffer circular con mínima contención y operaciones vectorizadas
class AudioCallback : public oboe::AudioStreamDataCallback {
private:
    // ✅ OPTIMIZACIÓN LATENCIA: Buffer aumentado para evitar saturación sin lag
    static constexpr int BUFFER_SIZE_FRAMES = 2048;      // ⬆️ AUMENTADO: 1024 → 2048 (~43ms @ 48kHz)
    static constexpr int TARGET_BUFFER_FRAMES = 128;      // ~2.67ms target latency
    static constexpr int DROP_THRESHOLD = 1536;           // 75% del nuevo buffer (más tolerancia)
    static constexpr int SILENCE_TIMEOUT_MS = 5000;      // Timeout de silencio
    static constexpr int CORRUPTION_CHECK_INTERVAL = 200; // Menos frecuente para mejor perf

    // Buffer circular que almacena muestras en formato float interleaved
    std::vector<float> circularBuffer;
    
    // ✅ OPTIMIZACIÓN: Mutex solo para operaciones de reset, no para R/W normal
    std::mutex resetMutex;

    // ✅ OPTIMIZACIÓN: Índices atómicos para acceso lock-free en casos simples
    std::atomic<int> writePos{0};
    std::atomic<int> readPos{0};
    std::atomic<int> availableFrames{0};
    
    int channelCount = 2;
    int bufferSizeSamples = 0;  // Cache para evitar multiplicaciones

    // Estadísticas atómicas
    std::atomic<int> underrunCount{0};
    std::atomic<int> dropCount{0};
    std::atomic<int64_t> lastAudioTime{0};
    std::atomic<bool> wasSilent{false};
    std::atomic<int> callbackCount{0};
    std::atomic<int> resetCount{0};
    std::atomic<int64_t> lastResetTime{0};

public:
    // Constructor: inicializa el buffer con tamaño optimizado
    explicit AudioCallback(int channels) : channelCount(channels) {
        bufferSizeSamples = BUFFER_SIZE_FRAMES * channelCount;
        circularBuffer.resize(bufferSizeSamples, 0.0f);
        lastAudioTime = getCurrentTimeMillis();
        LOGD("✅ AudioCallback ULTRA-LOW-LATENCY: %d canales, buffer %d frames (~%dms)",
                channels, BUFFER_SIZE_FRAMES,
                BUFFER_SIZE_FRAMES * 1000 / 48000);
    }

    /**
     * ✅ OPTIMIZADO FASE 2: Callback de audio con mínima latencia
     * - Usa memcpy vectorizado en lugar de loop sample-by-sample
     * - Prefetch para mejor cache hit rate
     * - Branch prediction hints
     * - Reduce operaciones en hot path
     */
    oboe::DataCallbackResult onAudioReady(
            oboe::AudioStream *audioStream,
            void *audioData,
            int32_t numFrames) override {

        auto *outputBuffer = static_cast<float *>(audioData);
        (void)audioStream;
        
        const int samplesNeeded = numFrames * channelCount;
        callbackCount++;

        // 1) Validación periódica (menos frecuente para mejor perf)
        if (UNLIKELY((callbackCount % CORRUPTION_CHECK_INTERVAL) == 0)) {
            if (!validateBufferState()) {
                LOGE("💥 Corrupción detectada, reseteando...");
                std::lock_guard<std::mutex> lock(resetMutex);
                forceResetInternal();
                std::memset(outputBuffer, 0, samplesNeeded * sizeof(float));
                return oboe::DataCallbackResult::Continue;
            }
        }

        // 2-4) Obtener frames y posición actual CON PROTECCIÓN
        int currentReadPos;
        int available;
        {
            // ✅ CRITICAL: Lock mínimo para leer valores consistentes
            std::lock_guard<std::mutex> lock(resetMutex);
            available = availableFrames.load(std::memory_order_acquire);
            currentReadPos = readPos.load(std::memory_order_acquire);
        }
        
        // 3) Underrun: no hay datos (caso raro, optimizar path común)
        if (UNLIKELY(available == 0)) {
            std::memset(outputBuffer, 0, samplesNeeded * sizeof(float));
            underrunCount++;
            
            int64_t silentTime = getCurrentTimeMillis() - lastAudioTime.load();
            if (silentTime > SILENCE_TIMEOUT_MS && wasSilent.load()) {
                int64_t timeSinceReset = getCurrentTimeMillis() - lastResetTime.load();
                if (timeSinceReset > 10000) {
                    LOGW("🔄 Silencio prolongado (%lldms), reseteando", (long long)silentTime);
                    std::lock_guard<std::mutex> lock(resetMutex);
                    forceResetInternal();
                }
            }
            wasSilent.store(true);
            return oboe::DataCallbackResult::Continue;
        }
        
        // Validar posición (raramente falla)
        if (UNLIKELY(currentReadPos < 0 || currentReadPos >= bufferSizeSamples)) {
            LOGE("💥 readPos corrupto: %d", currentReadPos);
            std::lock_guard<std::mutex> lock(resetMutex);
            forceResetInternal();
            std::memset(outputBuffer, 0, samplesNeeded * sizeof(float));
            return oboe::DataCallbackResult::Continue;
        }

        // 5) Calcular cuántos frames reproducir
        int framesToPlay = std::min(available, numFrames);
        int samplesToPlay = framesToPlay * channelCount;

        // ✅ FASE 2: Prefetch de datos del buffer circular
        PREFETCH_READ(&circularBuffer[currentReadPos]);
        PREFETCH_WRITE(outputBuffer);

        // 6) ✅ OPTIMIZADO: Copia vectorizada con memcpy
        int samplesInFirstPart = std::min(samplesToPlay, bufferSizeSamples - currentReadPos);
        
        // Primera parte (hasta el final del buffer)
        std::memcpy(outputBuffer, &circularBuffer[currentReadPos], 
                    samplesInFirstPart * sizeof(float));
        
        // Segunda parte (wrap-around si es necesario)
        int samplesRemaining = samplesToPlay - samplesInFirstPart;
        if (UNLIKELY(samplesRemaining > 0)) {
            // Prefetch del inicio del buffer para wrap-around
            PREFETCH_READ(&circularBuffer[0]);
            std::memcpy(outputBuffer + samplesInFirstPart, &circularBuffer[0],
                        samplesRemaining * sizeof(float));
        }

        // Padding con ceros si no hay suficientes datos (raro)
        if (UNLIKELY(samplesToPlay < samplesNeeded)) {
            std::memset(outputBuffer + samplesToPlay, 0,
                        (samplesNeeded - samplesToPlay) * sizeof(float));
        }

        // 7) Actualizar posición de lectura (CON PROTECCIÓN contra drop simultáneo)
        {
            std::lock_guard<std::mutex> lock(resetMutex);
            int newReadPos = (currentReadPos + samplesToPlay) % bufferSizeSamples;
            readPos.store(newReadPos, std::memory_order_release);
            availableFrames.fetch_sub(framesToPlay, std::memory_order_release);
        }

        // 8) Actualizar timestamp si reproducimos algo
        if (LIKELY(framesToPlay > 0)) {
            lastAudioTime.store(getCurrentTimeMillis());
            if (UNLIKELY(wasSilent.load())) {
                LOGD("🔊 Audio recuperado después de %d underruns", underrunCount.load());
                wasSilent.store(false);
            }
        }

        // 9) Drop preventivo si el buffer crece demasiado (raro) - CON PROTECCIÓN
        {
            std::lock_guard<std::mutex> lock(resetMutex);
            int currentAvailable = availableFrames.load();
            if (UNLIKELY(currentAvailable > DROP_THRESHOLD)) {
                int excess = currentAvailable - TARGET_BUFFER_FRAMES;
                if (excess > 0) {
                    int currentRP = readPos.load();
                    int newRP = (currentRP + excess * channelCount) % bufferSizeSamples;
                    readPos.store(newRP, std::memory_order_release);
                    availableFrames.fetch_sub(excess, std::memory_order_release);
                    dropCount.fetch_add(excess);
                    
                    if (excess > 256) {
                        LOGD("🗑️ Drop preventivo: %d frames", excess);
                    }
                }
            }
        }

        return oboe::DataCallbackResult::Continue;
    }

    /**
     * ✅ OPTIMIZADO FASE 2: Escritura de audio con operaciones vectorizadas y prefetch
     */
    int writeAudio(const float *data, int numFrames) {
        lastAudioTime.store(getCurrentTimeMillis());

        const int samplesTotal = numFrames * channelCount;

        // ✅ FASE 2: Prefetch de datos entrantes
        PREFETCH_READ(data);

        // 1) Obtener frames disponibles y calcular espacio libre
        int available = availableFrames.load(std::memory_order_acquire);
        int freeFrames = BUFFER_SIZE_FRAMES - available;

        // 2) Si no hay espacio suficiente, hacer drop con mutex (evita race condition)
        if (UNLIKELY(freeFrames < numFrames)) {
            // ✅ CRITICAL FIX: Usar mutex para drop - readPos se está leyendo desde callback simultáneamente
            std::lock_guard<std::mutex> lock(resetMutex);
            
            available = availableFrames.load(std::memory_order_acquire);
            freeFrames = BUFFER_SIZE_FRAMES - available;
            
            if (UNLIKELY(freeFrames < numFrames) && available > 100) {
                // ✅ FIX: Cleanly drop solo 30% (mucho menos agresivo que 50%)
                int framesToClear = (available * 3) / 10;  // 30% en lugar de 75% anterior
                if (framesToClear > 0) {
                    LOGW("🗑️ Buffer saturado (%d frames), limpiando %d", available, framesToClear);
                    
                    int currentRP = readPos.load(std::memory_order_acquire);
                    int newRP = (currentRP + framesToClear * channelCount) % bufferSizeSamples;
                    readPos.store(newRP, std::memory_order_release);
                    availableFrames.fetch_sub(framesToClear, std::memory_order_release);
                    dropCount.fetch_add(framesToClear);
                    
                    freeFrames = BUFFER_SIZE_FRAMES - availableFrames.load();
                }
            }
        }

        // 3) Calcular cuántos frames escribir (caso normal: todos)
        int framesToWrite = std::min(numFrames, freeFrames);
        if (UNLIKELY(framesToWrite <= 0)) {
            LOGW("❌ Buffer lleno, descartando %d frames", numFrames);
            dropCount.fetch_add(numFrames);
            return 0;
        }

        int samplesToWrite = framesToWrite * channelCount;

        // 4) ✅ OPTIMIZADO FASE 2: Escritura vectorizada con memcpy y prefetch
        int currentWP = writePos.load(std::memory_order_acquire);
        
        // Prefetch destino
        PREFETCH_WRITE(&circularBuffer[currentWP]);
        
        int samplesInFirstPart = std::min(samplesToWrite, bufferSizeSamples - currentWP);
        
        // Primera parte
        std::memcpy(&circularBuffer[currentWP], data, samplesInFirstPart * sizeof(float));
        
        // Segunda parte (wrap-around) - raro
        int samplesRemaining = samplesToWrite - samplesInFirstPart;
        if (UNLIKELY(samplesRemaining > 0)) {
            PREFETCH_WRITE(&circularBuffer[0]);
            std::memcpy(&circularBuffer[0], data + samplesInFirstPart, 
                        samplesRemaining * sizeof(float));
        }

        // 5) Actualizar posición de escritura
        int newWP = (currentWP + samplesToWrite) % bufferSizeSamples;
        writePos.store(newWP, std::memory_order_release);
        availableFrames.fetch_add(framesToWrite, std::memory_order_release);
        
        // 6) Verificación de consistencia (raramente falla)
        if (UNLIKELY(availableFrames.load() > BUFFER_SIZE_FRAMES)) {
            LOGE("💥 CORRUPCIÓN: availableFrames=%d > MAX=%d",
                    availableFrames.load(), BUFFER_SIZE_FRAMES);
            std::lock_guard<std::mutex> lock(resetMutex);
            forceResetInternal();
            return 0;
        }

        return framesToWrite;
    }

    /**
     * Validación del estado interno del buffer
     */
    bool validateBufferState() {
        int avail = availableFrames.load();
        int rp = readPos.load();
        int wp = writePos.load();
        
        if (avail < 0 || avail > BUFFER_SIZE_FRAMES) {
            LOGE("❌ availableFrames fuera de rango: %d", avail);
            return false;
        }

        if (rp < 0 || rp >= bufferSizeSamples) {
            LOGE("❌ readPos fuera de rango: %d", rp);
            return false;
        }

        if (wp < 0 || wp >= bufferSizeSamples) {
            LOGE("❌ writePos fuera de rango: %d", wp);
            return false;
        }

        return true;
    }

    /**
     * Reset interno (sin lock, usar solo cuando ya se tiene el lock)
     */
    void forceResetInternal() {
        std::fill(circularBuffer.begin(), circularBuffer.end(), 0.0f);
        writePos.store(0, std::memory_order_release);
        readPos.store(0, std::memory_order_release);
        availableFrames.store(0, std::memory_order_release);
        underrunCount.store(0);
        dropCount.store(0);
        wasSilent.store(false);
        resetCount++;
        lastResetTime.store(getCurrentTimeMillis());
        LOGW("🔄 Buffer reseteado (reset #%d)", resetCount.load());
    }

    /**
     * Versión pública de limpieza
     */
    void clear() {
        std::lock_guard<std::mutex> lock(resetMutex);
        forceResetInternal();
    }

    // Getters para estadísticas
    int getAvailableFrames() const {
        return availableFrames.load();
    }

    int getUnderrunCount() const {
        return underrunCount.load();
    }

    // Porcentaje de uso del buffer (0..100)
    float getBufferUsagePercent() const {
        return (static_cast<float>(availableFrames) / BUFFER_SIZE_FRAMES) * 100.0f;
    }

    // Latencia aproximada en ms calculada a partir de frames disponibles y frecuencia 48kHz
    float getLatencyMs() const {
        return (static_cast<float>(availableFrames) / 48000.0f) * 1000.0f;
    }

    // Indica si estamos recibiendo audio (basado en tiempo desde el último paquete válido)
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
     * Estructura de estadísticas completa que agrupa métricas útiles para depuración.
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

    // Devuelve un snapshot (copia) de las estadísticas actuales
    RFStats getRFStats() const {
        RFStats stats{}; // inicializa todos los campos a cero/false para evitar advertencias
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
    // Utilidad para obtener la hora actual en milisegundos desde epoch
    int64_t getCurrentTimeMillis() const {
        using namespace std::chrono;
        return duration_cast<milliseconds>(
                system_clock::now().time_since_epoch()
        ).count();
    }
};

#endif // FICHATECH_AUDIO_CALLBACK_H