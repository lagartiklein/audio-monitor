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

// Macros de log para Android; facilitan escribir mensajes con niveles
#define LOG_TAG "AudioCallback"
#define LOGD(...) __android_log_print(ANDROID_LOG_DEBUG, LOG_TAG, __VA_ARGS__)
#define LOGW(...) __android_log_print(ANDROID_LOG_WARN, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

// Clase que implementa AudioStreamDataCallback de Oboe.
// Esta clase gestiona un buffer circular en memoria donde se escribe audio
// desde la parte de producción y se lee desde el callback de audio (consumo).
class AudioCallback : public oboe::AudioStreamDataCallback {
private:
    // Constantes de configuración del buffer y de recuperación
    static constexpr int BUFFER_SIZE_FRAMES = 2048;      // Tamaño del buffer en frames (no en muestras). ~42 ms a 48 kHz
    static constexpr int TARGET_BUFFER_FRAMES = 128;     // Tamaño objetivo de buffer en frames para latencia baja (~2.7 ms)
    static constexpr int DROP_THRESHOLD = 1536;          // Umbral (en frames) a partir del cual empezamos a dropear para evitar overflow (75% de BUFFER_SIZE_FRAMES)
    static constexpr int SILENCE_TIMEOUT_MS = 5000;      // Tiempo en ms de silencio sostenido tras el cual intentamos un reset automático (5 s)
    static constexpr int CORRUPTION_CHECK_INTERVAL = 100; // Cada cuántos callbacks verificamos si hay corrupción interna

    // Buffer circular que almacena muestras en formato float interleaved (canal0, canal1, canal0, canal1, ...)
    std::vector<float> circularBuffer;
    // Mutex para proteger accesos concurrentes entre el hilo que escribe y el callback de audio
    std::mutex bufferMutex;

    // Punteros/índices dentro del buffer circular (en muestras, no en frames)
    int writePos = 0; // índice de la siguiente posición donde se escribirá una muestra
    int readPos = 0;  // índice de la siguiente muestra que se leerá en el callback

    // Contador de frames disponibles (en frames, no en muestras). Atómico para lectura segura sin lock en getters.
    std::atomic<int> availableFrames{0};
    int channelCount = 2; // número de canales (por defecto stereo)

    // Estadísticas y contadores atómicos para inspección y recuperación
    std::atomic<int> underrunCount{0};         // cuántas veces no había audio para reproducir
    std::atomic<int> dropCount{0};             // cuántos frames se descartaron por overflow
    std::atomic<int64_t> lastAudioTime{0};     // timestamp (ms) del último audio válido recibido
    std::atomic<bool> wasSilent{false};        // flag que indica si estábamos en estado de silencio prolongado

    // Contadores para detección de corrupción y resets
    std::atomic<int> callbackCount{0};         // cuántos callbacks se han ejecutado (para chequeos periódicos)
    std::atomic<int> resetCount{0};            // cuántos resets forzados se han hecho
    std::atomic<int64_t> lastResetTime{0};     // timestamp (ms) del último reset

public:
    // Constructor: inicializa el buffer en función de canales y marca el tiempo actual
    explicit AudioCallback(int channels) : channelCount(channels) {
        // Reservamos espacio: BUFFER_SIZE_FRAMES * channelCount muestras
        circularBuffer.resize(BUFFER_SIZE_FRAMES * channelCount, 0.0f);
        lastAudioTime = getCurrentTimeMillis();
        // Log informativo indicando la configuración
        LOGD("✅ AudioCallback RF: %d canales, buffer %d frames (~%dms)",
                channels, BUFFER_SIZE_FRAMES,
                BUFFER_SIZE_FRAMES * 1000 / 48000);
    }

    /**
     * Método que implementa el callback de Oboe: se llama en el hilo de audio cada vez
     * que el sistema pide datos para reproducir. Debe ser extremadamente eficiente y
     * no bloquear por mucho tiempo.
     *
     * Retorna DataCallbackResult::Continue para seguir reproduciendo.
     */
    oboe::DataCallbackResult onAudioReady(
            oboe::AudioStream *audioStream,
            void *audioData,
            int32_t numFrames) override {

        // 'audioData' apunta a un buffer donde debemos escribir las muestras float a reproducir.
        auto *outputBuffer = static_cast<float *>(audioData);
        // Evita advertencia de parámetro no usado (el stream no se necesita aquí)
        (void)audioStream;
        // Calculamos cuántas muestras (floats) son necesarias: frames * canales
        const int samplesNeeded = numFrames * channelCount;

        // Bloqueamos el mutex para asegurar coherencia del buffer circular durante la lectura
        std::lock_guard<std::mutex> lock(bufferMutex);

        // Incrementamos el contador de callbacks (usado para chequeos periódicos)
        callbackCount++;

        // 1) Validación periódica de sanidad interna para detectar corrupción de índices
        if (callbackCount % CORRUPTION_CHECK_INTERVAL == 0) {
            if (!validateBufferState()) {
                // Si detectamos corrupción, hacemos un reset forzado y devolvemos silencio
                LOGE("💥 Corrupción detectada, reseteando...");
                forceReset();
                std::memset(outputBuffer, 0, samplesNeeded * sizeof(float));
                return oboe::DataCallbackResult::Continue;
            }
        }

        // 2) Manejo de buffer vacío (underrun): si no hay frames disponibles, devolvemos silencio
        if (availableFrames == 0) {
            // Rellenamos con ceros (silencio)
            std::memset(outputBuffer, 0, samplesNeeded * sizeof(float));
            underrunCount++;

            // Calculamos cuánto tiempo ha pasado desde el último audio válido
            int64_t silentTime = getCurrentTimeMillis() - lastAudioTime;

            // Si estuvo en silencio y supera el timeout, intentamos un reset automático
            if (silentTime > SILENCE_TIMEOUT_MS && wasSilent) {
                int64_t timeSinceLastReset = getCurrentTimeMillis() - lastResetTime;

                // Evitamos hacer resets muy seguidos: al menos 10s entre resets
                if (timeSinceLastReset > 10000) {
                    // casteamos a long long para cumplir el especificador %lld en el log
                    LOGW("🔄 Silencio prolongado (%lldms), reseteando buffer", (long long)silentTime);
                    forceReset();
                }
            }

            // Marcamos que estábamos en silencio
            wasSilent = true;
            return oboe::DataCallbackResult::Continue;
        }

        // 3) Validación adicional: asegurarnos de que readPos esté dentro del rango del vector
        if (readPos >= static_cast<int>(circularBuffer.size())) {
            LOGE("💥 readPos corrupto: %d >= %zu", readPos, circularBuffer.size());
            forceReset();
            std::memset(outputBuffer, 0, samplesNeeded * sizeof(float));
            return oboe::DataCallbackResult::Continue;
        }

        // 4) Reproducimos audio copiando desde el buffer circular al buffer de salida
        // Determinamos cuántos frames podemos reproducir: mínimo entre los disponibles y lo pedido
        int framesToPlay = std::min(availableFrames.load(), numFrames);
        int samplesToPlay = framesToPlay * channelCount;

        // Copiamos muestras de forma segura haciendo wrap-around con el módulo del tamaño del vector
        for (int i = 0; i < samplesToPlay; i++) {
            outputBuffer[i] = circularBuffer[readPos];
            readPos = (readPos + 1) % static_cast<int>(circularBuffer.size());
        }

        // Si no alcanzamos a llenar el buffer de salida, rellenamos el resto con ceros (silencio)
        if (samplesToPlay < samplesNeeded) {
            std::memset(outputBuffer + samplesToPlay, 0,
                    (samplesNeeded - samplesToPlay) * sizeof(float));
        }

        // Reducimos el contador de frames disponibles en la cantidad reproducida
        availableFrames -= framesToPlay;

        // 5) Si hemos reproducido frames válidos, actualizamos el timestamp del último audio válido
        if (framesToPlay > 0) {
            lastAudioTime = getCurrentTimeMillis();
        }

        // Si veníamos de silencio y ahora reproducimos, registramos recuperación
        if (wasSilent && framesToPlay > 0) {
            LOGD("🔊 Audio recuperado después de %d underruns", underrunCount.load());
            wasSilent = false;
        }

        // 6) Lógica preventiva para drops cuando el buffer crece demasiado (evitar latencia excesiva)
        if (availableFrames > DROP_THRESHOLD) {
            // Calculamos exceso respecto al target
            int excess = availableFrames - TARGET_BUFFER_FRAMES;
            if (excess > 0) {
                // Ajustamos readPos para descartar los frames más antiguos y reducir latencia
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
     * Método público para escribir audio en el buffer circular.
     * Recibe un puntero a floats interleaved y el número de frames a escribir.
     * Devuelve cuántos frames realmente escribió (podría escribir menos si el buffer está lleno).
     */
    int writeAudio(const float *data, int numFrames) {
        // Protegemos la escritura con el mismo mutex que usa el callback lector
        std::lock_guard<std::mutex> lock(bufferMutex);

        // Actualizamos el timestamp de actividad (estamos recibiendo audio ahora)
        lastAudioTime = getCurrentTimeMillis();

        const int samplesTotal = numFrames * channelCount;

        // 1) Calculamos espacio libre real en frames
        int freeFrames = BUFFER_SIZE_FRAMES - availableFrames;

        // 2) Si no hay espacio suficiente, aplicamos estrategia de clearing agresiva
        if (freeFrames < numFrames) {
            // Eliminamos el 75% del contenido actual para recuperar espacio (estrategia de emergencia)
            int framesToClear = (availableFrames * 3) / 4;

            if (framesToClear > 0) {
                LOGW("🗑️ Buffer saturado (%d frames), limpiando %d frames",
                        availableFrames.load(), framesToClear);

                // Avanzamos readPos para descartar frames antiguos y ajustar availableFrames
                readPos = (readPos + framesToClear * channelCount) % static_cast<int>(circularBuffer.size());
                availableFrames -= framesToClear;
                dropCount += framesToClear;

                // Recalculamos el espacio libre tras limpiar
                freeFrames = BUFFER_SIZE_FRAMES - availableFrames;
            }
        }

        // 3) Determinamos cuántos frames podemos escribir con seguridad
        int framesToWrite = std::min(numFrames, freeFrames);

        // 4) Si no hay nada que escribir, informamos y descartamos
        if (framesToWrite <= 0) {
            LOGW("❌ Buffer completamente lleno, descartando %d frames", numFrames);
            dropCount += numFrames;
            return 0;
        }

        int samplesToWrite = framesToWrite * channelCount;

        // 5) Escritura segura en el buffer circular (con wrap-around)
        for (int i = 0; i < samplesToWrite; i++) {
            circularBuffer[writePos] = data[i];
            writePos = (writePos + 1) % static_cast<int>(circularBuffer.size());
        }

        // 6) Actualizamos el contador de frames disponibles solo con lo que realmente escribimos
        availableFrames += framesToWrite;

        // 7) Verificación post-escritura para detectar inconsistencia
        if (availableFrames > BUFFER_SIZE_FRAMES) {
            LOGE("💥 CORRUPCIÓN: availableFrames=%d > MAX=%d",
                    availableFrames.load(), BUFFER_SIZE_FRAMES);
            forceReset();
            return 0;
        }

        // Devolvemos la cantidad de frames escritos (puede ser menor a numFrames)
        return framesToWrite;
    }

    /**
     * Validación del estado interno del buffer: verifica rangos de contadores e índices.
     * Retorna true si todo está dentro de rango, false si detecta inconsistencia.
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
     * Reset forzado del buffer: limpia contenidos y reinicia índices y contadores.
     * Útil cuando se detecta corrupción o se desea recuperar de estados inválidos.
     */
    void forceReset() {
        // Llenamos con ceros el buffer y reiniciamos posiciones y contadores.
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
     * Versión pública de limpieza que adquiere el lock y llama a forceReset.
     */
    void clear() {
        std::lock_guard<std::mutex> lock(bufferMutex);
        forceReset();
    }

    // Getters sencillos para inspeccionar estado desde fuera (seguros y rápidos)
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