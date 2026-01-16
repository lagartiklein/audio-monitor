// audio_callback.h - SIN PROCESAMIENTO PLC/JITTER
// Audio natural sin procesamiento artificial

#ifndef FICHATECH_AUDIO_CALLBACK_H
#define FICHITECH_AUDIO_CALLBACK_H

#include <oboe/Oboe.h>
#include <android/log.h>
#include <atomic>
#include <vector>
#include <cstring>
#include <memory>
#include <algorithm>
#include <chrono>

#define LOG_TAG "AudioCallback"
#define LOGD(...) __android_log_print(ANDROID_LOG_DEBUG, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

// Lock-free SPSC buffer
template<typename T>
class LockFreeAudioBuffer {
private:
    std::vector<T> buffer;
    const int capacity;
    std::atomic<int> writeIndex{0};
    std::atomic<int> readIndex{0};
public:
    explicit LockFreeAudioBuffer(int size) : buffer(size), capacity(size) {}

    int write(const T* data, int count) {
        int written = 0;
        while (written < count) {
            int w = writeIndex.load(std::memory_order_relaxed);
            int r = readIndex.load(std::memory_order_acquire);
            int space = capacity - ((w - r + capacity) % capacity) - 1;
            if (space <= 0) break;
            int toWrite = std::min(count - written, space);
            int chunk = std::min(toWrite, capacity - (w % capacity));
            std::memcpy(&buffer[w % capacity], data + written, chunk * sizeof(T));
            writeIndex.store((w + chunk) % capacity, std::memory_order_release);
            written += chunk;
        }
        return written;
    }

    int read(T* out, int count) {
        int readTotal = 0;
        while (readTotal < count) {
            int w = writeIndex.load(std::memory_order_acquire);
            int r = readIndex.load(std::memory_order_relaxed);
            int available = (w - r + capacity) % capacity;
            if (available <= 0) break;
            int toRead = std::min(count - readTotal, available);
            int chunk = std::min(toRead, capacity - (r % capacity));
            std::memcpy(out + readTotal, &buffer[r % capacity], chunk * sizeof(T));
            readIndex.store((r + chunk) % capacity, std::memory_order_release);
            readTotal += chunk;
        }
        return readTotal;
    }

    void clear() {
        writeIndex.store(0, std::memory_order_relaxed);
        readIndex.store(0, std::memory_order_relaxed);
    }

    int getAvailable() const {
        int w = writeIndex.load(std::memory_order_acquire);
        int r = readIndex.load(std::memory_order_acquire);
        return (w - r + capacity) % capacity;
    }

    int getCapacity() const { return capacity - 1; }
};

class AudioCallback : public oboe::AudioStreamDataCallback {
private:
    static constexpr int BUFFER_SIZE_FRAMES = 1024; // valor por defecto, configurable en el constructor
    static constexpr int SILENCE_TIMEOUT_MS = 5000;

    // ahora es un puntero para poder reconstruir el buffer si cambiamos tamaño en ejecución
    std::unique_ptr<LockFreeAudioBuffer<float>> circularBuffer;
    int channelCount = 2;
    int bufferFrames = BUFFER_SIZE_FRAMES; // frames configurables
    int sampleRate = 48000; // sample rate configurable (por defecto 48k)

    std::atomic<int64_t> lastAudioTime{0};
    std::atomic<bool> wasSilent{false};

public:
    // Ahora se puede pasar bufferFrames y sampleRate para reducir latencia
    explicit AudioCallback(int channels, int bufferFrames_ = BUFFER_SIZE_FRAMES, int sampleRate_ = 48000)
            : channelCount(channels),
              bufferFrames(bufferFrames_),
              sampleRate(sampleRate_) {
        // crear el buffer circular con capacidad = frames * canales + 1
        circularBuffer = std::make_unique<LockFreeAudioBuffer<float>>(bufferFrames * channels + 1);
        lastAudioTime = getCurrentTimeMillis();
        LOGD("✅ AudioCallback simplificado: %d canales, bufferFrames=%d, sampleRate=%d", channels, bufferFrames_, sampleRate_);
    }

    // Permite ajustar el tamaño del buffer en tiempo de ejecución (p. ej. usando framesPerBurst del stream)
    void setBufferFrames(int newBufferFrames, int newChannelCount = -1) {
        if (newBufferFrames <= 0) return;
        int ch = (newChannelCount > 0) ? newChannelCount : channelCount;
        bufferFrames = newBufferFrames;
        channelCount = ch;
        circularBuffer = std::make_unique<LockFreeAudioBuffer<float>>(bufferFrames * channelCount + 1);
        LOGD("⚙️ Buffer reconstruido: canales=%d, bufferFrames=%d", channelCount, bufferFrames);
    }

    // Ajustar bufferFrames automáticamente basado en framesPerBurst del stream
    // Se recomienda: bufferFrames = framesPerBurst * multiplier (1..4). Menor multiplier = menor latencia, mayor riesgo de underrun.
    void adaptToFramesPerBurst(int framesPerBurst, int multiplier = 2) {
        if (framesPerBurst <= 0) return;
        int target = framesPerBurst * std::max(1, multiplier);
        setBufferFrames(target);
        LOGD("🔧 Adaptado a framesPerBurst=%d, multiplier=%d => bufferFrames=%d", framesPerBurst, multiplier, target);
    }

    AudioCallback(const AudioCallback&) = delete;
    AudioCallback& operator=(const AudioCallback&) = delete;

    oboe::DataCallbackResult onAudioReady(
            oboe::AudioStream *audioStream,
            void *audioData,
            int32_t numFrames) override {

        (void) audioStream;
        auto *outputBuffer = static_cast<float *>(audioData);
        const int samplesNeeded = numFrames * channelCount;

        // Verificar si hay audio disponible
        int framesInBuffer = circularBuffer->getAvailable() / channelCount;

        if (framesInBuffer <= 0) {
            // SIN PLC: Silencio natural cuando no hay datos
            std::memset(outputBuffer, 0, samplesNeeded * sizeof(float));

            const int64_t silentTime = getCurrentTimeMillis() - lastAudioTime.load();
            if (silentTime > SILENCE_TIMEOUT_MS && wasSilent.load()) {
                LOGD("🔇 Silencio prolongado: %lldms", static_cast<long long>(silentTime));
            }

            wasSilent = true;
            return oboe::DataCallbackResult::Continue;
        }

        // Leer audio disponible (sin procesamiento adicional)
        const int framesToRead = std::min(framesInBuffer, numFrames);
        const int samplesToRead = framesToRead * channelCount;
        const int samplesRead = circularBuffer->read(outputBuffer, samplesToRead);

        // Rellenar con silencio si faltan frames (natural, sin PLC)
        if (samplesRead < samplesNeeded) {
            std::memset(outputBuffer + samplesRead, 0,
                        (samplesNeeded - samplesRead) * sizeof(float));
        }

        if (samplesRead > 0) {
            lastAudioTime = getCurrentTimeMillis();
        }

        if (wasSilent.load() && samplesRead > 0) {
            LOGD("🔊 Audio recuperado naturalmente");
            wasSilent = false;
        }

        return oboe::DataCallbackResult::Continue;
    }

    int writeAudio(const float *data, int numFrames) {
        const int samplesToWrite = numFrames * channelCount;
        int samplesWritten = circularBuffer->write(data, samplesToWrite);

        if (samplesWritten > 0) {
            lastAudioTime = getCurrentTimeMillis();
        }

        return samplesWritten / channelCount;
    }

    void clear() {
        circularBuffer->clear();
        wasSilent = false;
        lastAudioTime = getCurrentTimeMillis();
        LOGD("🧹 Buffer limpiado");
    }

    int getAvailableFrames() const {
        return circularBuffer->getAvailable() / channelCount;
    }

    float getLatencyMs() const {
        // usar sampleRate real en el cálculo de latencia
        int sr = sampleRate > 0 ? sampleRate : 48000;
        return (static_cast<float>(getAvailableFrames()) / static_cast<float>(sr)) * 1000.0f;
    }

    // Añadir helpers para actualizar sample rate si es necesario
    void setSampleRate(int sr) {
        if (sr > 0) sampleRate = sr;
    }

    int getBufferFrames() const { return bufferFrames; }

    bool isReceivingAudio() const {
        return (getCurrentTimeMillis() - lastAudioTime.load()) < 2000;
    }

private:
    static int64_t getCurrentTimeMillis() {
        using namespace std::chrono;
        return duration_cast<milliseconds>(
                system_clock::now().time_since_epoch()).count();
    }
};

#endif // FICHATECH_AUDIO_CALLBACK_H
