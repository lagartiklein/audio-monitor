// audio_callback.h - Lock-Free Ultra Low Latency
#ifndef FICHATECH_AUDIO_CALLBACK_OPTIMIZED_H
#define FICHATECH_AUDIO_CALLBACK_OPTIMIZED_H

#include <oboe/Oboe.h>
#include <android/log.h>
#include <atomic>
#include <cstring>
#include <cstdint>
#include <time.h>

#define LOG_TAG "AudioCallbackOpt"
#define LOGD(...) __android_log_print(ANDROID_LOG_DEBUG, LOG_TAG, __VA_ARGS__)
#define LOGW(...) __android_log_print(ANDROID_LOG_WARN, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

class LockFreeAudioCallback : public oboe::AudioStreamDataCallback {
public:
    struct RFStats {
        int availableFrames;
        float latencyMs;
        bool isReceiving;
        uint32_t underruns;
        uint32_t drops;
        float usagePercent;
        uint32_t resets;
    };

    RFStats getRFStats() const {
        RFStats stats;
        stats.availableFrames = getAvailableFrames();
        stats.latencyMs = getLatencyMs();
        stats.isReceiving = isReceivingAudio();
        stats.underruns = getUnderrunCount();
        stats.drops = getOverrunCount();
        stats.usagePercent = (getAvailableFrames() * 100.0f) / BUFFER_SIZE_FRAMES;
        stats.resets = 0; // Si tienes lógica de resets, cámbialo
        return stats;
    }
private:
    static constexpr int BUFFER_SIZE_FRAMES = 128; // ~2.67ms @ 48kHz
    static constexpr int BUFFER_SIZE_SAMPLES = BUFFER_SIZE_FRAMES * 2; // Stereo
    static constexpr int BUFFER_MASK = BUFFER_SIZE_FRAMES - 1;

    alignas(64) float circularBuffer[BUFFER_SIZE_SAMPLES];
    alignas(64) std::atomic<uint32_t> writePos{0};
    alignas(64) std::atomic<uint32_t> readPos{0};
    alignas(64) std::atomic<uint32_t> underrunCount{0};
    alignas(64) std::atomic<uint32_t> overrunCount{0};
    alignas(64) std::atomic<int64_t> lastWriteTimeNs{0};

    int channelCount;

public:
    explicit LockFreeAudioCallback(int channels) : channelCount(channels) {
        std::memset(circularBuffer, 0, sizeof(circularBuffer));
        LOGD("✅ LockFreeAudioCallback: %d canales, %d frames (~%.1fms)",
             channels, BUFFER_SIZE_FRAMES,
             BUFFER_SIZE_FRAMES * 1000.0f / 48000.0f);
    }

    int writeAudio(const float* data, int numFrames) {
        const uint32_t currentWrite = writePos.load(std::memory_order_relaxed);
        const uint32_t currentRead = readPos.load(std::memory_order_acquire);
        const uint32_t freeFrames = ((currentRead - currentWrite - 1) & BUFFER_MASK);

        if (freeFrames == 0) {
            overrunCount.fetch_add(1, std::memory_order_relaxed);
            return 0;
        }

        const int framesToWrite = std::min(numFrames, static_cast<int>(freeFrames));
        const int samplesToWrite = framesToWrite * channelCount;
        uint32_t writeIdx = (currentWrite * channelCount) % BUFFER_SIZE_SAMPLES;

        for (int i = 0; i < samplesToWrite; ++i) {
            circularBuffer[writeIdx] = data[i];
            writeIdx = (writeIdx + 1) % BUFFER_SIZE_SAMPLES;
        }

        writePos.store((currentWrite + framesToWrite) & BUFFER_MASK,
                       std::memory_order_release);
        lastWriteTimeNs.store(getCurrentTimeNs(), std::memory_order_relaxed);
        return framesToWrite;
    }

    oboe::DataCallbackResult onAudioReady(oboe::AudioStream* audioStream,
                                          void* audioData,
                                          int32_t numFrames) override {
        auto* outputBuffer = static_cast<float*>(audioData);
        const int samplesNeeded = numFrames * channelCount;

        const uint32_t currentRead = readPos.load(std::memory_order_relaxed);
        const uint32_t currentWrite = writePos.load(std::memory_order_acquire);
        const uint32_t availableFrames = (currentWrite - currentRead) & BUFFER_MASK;

        if (availableFrames == 0) {
            std::memset(outputBuffer, 0, samplesNeeded * sizeof(float));
            underrunCount.fetch_add(1, std::memory_order_relaxed);
            return oboe::DataCallbackResult::Continue;
        }

        const int framesToRead = std::min(static_cast<int>(availableFrames), numFrames);
        const int samplesToRead = framesToRead * channelCount;
        uint32_t readIdx = (currentRead * channelCount) % BUFFER_SIZE_SAMPLES;

        for (int i = 0; i < samplesToRead; ++i) {
            outputBuffer[i] = circularBuffer[readIdx];
            readIdx = (readIdx + 1) % BUFFER_SIZE_SAMPLES;
        }

        if (samplesToRead < samplesNeeded) {
            std::memset(outputBuffer + samplesToRead, 0,
                       (samplesNeeded - samplesToRead) * sizeof(float));
        }

        readPos.store((currentRead + framesToRead) & BUFFER_MASK,
                      std::memory_order_release);
        return oboe::DataCallbackResult::Continue;
    }

    int getAvailableFrames() const {
        const uint32_t w = writePos.load(std::memory_order_acquire);
        const uint32_t r = readPos.load(std::memory_order_acquire);
        return (w - r) & BUFFER_MASK;
    }

    uint32_t getUnderrunCount() const { return underrunCount.load(std::memory_order_relaxed); }
    uint32_t getOverrunCount() const { return overrunCount.load(std::memory_order_relaxed); }

    float getLatencyMs() const {
        return (getAvailableFrames() * 1000.0f) / 48000.0f;
    }

    bool isReceivingAudio() const {
        const int64_t now = getCurrentTimeNs();
        const int64_t lastWrite = lastWriteTimeNs.load(std::memory_order_relaxed);
        return (now - lastWrite) < 2000000000LL;
    }

    void clear() {
        writePos.store(0, std::memory_order_release);
        readPos.store(0, std::memory_order_release);
        std::memset(circularBuffer, 0, sizeof(circularBuffer));
    }

private:
    static int64_t getCurrentTimeNs() {
        struct timespec ts;
        clock_gettime(CLOCK_MONOTONIC, &ts);
        return ts.tv_sec * 1000000000LL + ts.tv_nsec;
    }
};

#endif // FICHATECH_AUDIO_CALLBACK_OPTIMIZED_H
