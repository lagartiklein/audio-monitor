/**
 * AudioWorklet Processor para Audio Monitor
 * Versión completa y funcional
 */

class AudioProcessor extends AudioWorkletProcessor {
    constructor(options) {
        super();
        
        // Buffer circular para datos
        this.buffer = [];
        this.targetSize = options.processorOptions.bufferSize || 3;
        this.minSize = Math.max(1, this.targetSize - 1);
        this.maxSize = this.targetSize * 4;
        
        // Estado
        this.isBuffering = true;
        this.isPlaying = false;
        
        // Métricas
        this.samplesProcessed = 0;
        this.underruns = 0;
        this.consecutiveUnderruns = 0;
        
        // Comunicación con main thread
        this.port.onmessage = (event) => {
            if (event.data.type === 'audio') {
                this.addAudioData(event.data.data);
            }
        };
        
        // Enviar métricas cada ~100ms
        this.healthCheckInterval = Math.round(sampleRate / 10);
        this.healthCheckCounter = 0;
        
        console.log(`[AudioProcessor] Inicializado | Target: ${this.targetSize} buffers`);
    }
    
    addAudioData(audioData) {
        // Agregar al buffer
        const data = new Float32Array(audioData);
        this.buffer.push(data);
        
        // Limitar crecimiento excesivo
        if (this.buffer.length > this.maxSize) {
            // Eliminar buffers antiguos
            const excess = this.buffer.length - this.targetSize;
            this.buffer.splice(0, excess);
        }
        
        // Salir de buffering si alcanzamos target
        if (this.isBuffering && this.buffer.length >= this.targetSize) {
            this.isBuffering = false;
            this.isPlaying = true;
            this.port.postMessage({
                type: 'status',
                status: 'playing'
            });
        }
    }
    
    process(inputs, outputs, parameters) {
        const output = outputs[0];
        
        if (!output || !output[0]) {
            return true;
        }
        
        const outputChannel = output[0];
        const frameCount = outputChannel.length;
        
        // Fase de buffering inicial
        if (this.isBuffering) {
            outputChannel.fill(0);
            return true;
        }
        
        let framesWritten = 0;
        
        // Llenar output desde buffer
        while (framesWritten < frameCount && this.buffer.length > 0) {
            const chunk = this.buffer[0];
            const remainingFrames = frameCount - framesWritten;
            const availableFrames = chunk.length;
            const framesToCopy = Math.min(remainingFrames, availableFrames);
            
            // Copiar datos
            outputChannel.set(
                chunk.subarray(0, framesToCopy),
                framesWritten
            );
            
            framesWritten += framesToCopy;
            
            // Si consumimos todo el chunk, removerlo
            if (framesToCopy === availableFrames) {
                this.buffer.shift();
            } else {
                // Actualizar chunk con datos restantes
                this.buffer[0] = chunk.subarray(framesToCopy);
            }
        }
        
        // Manejar underruns
        if (framesWritten < frameCount) {
            // Llenar con silencio
            outputChannel.fill(0, framesWritten);
            
            this.underruns++;
            this.consecutiveUnderruns++;
            
            // Re-buffering si hay muchos underruns consecutivos
            if (this.consecutiveUnderruns > 5) {
                this.isBuffering = true;
                this.isPlaying = false;
                this.consecutiveUnderruns = 0;
                
                this.port.postMessage({
                    type: 'status',
                    status: 'rebuffering'
                });
            }
        } else {
            this.consecutiveUnderruns = 0;
        }
        
        // Actualizar métricas
        this.samplesProcessed += frameCount;
        this.healthCheckCounter += frameCount;
        
        // Enviar métricas periódicamente
        if (this.healthCheckCounter >= this.healthCheckInterval) {
            const bufferHealth = Math.round((this.buffer.length / this.targetSize) * 100);
            
            this.port.postMessage({
                type: 'bufferHealth',
                value: bufferHealth,
                underruns: this.underruns,
                buffering: this.isBuffering
            });
            
            this.healthCheckCounter = 0;
        }
        
        return true;
    }
}

registerProcessor('audio-processor', AudioProcessor);