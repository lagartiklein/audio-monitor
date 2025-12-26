class AudioProcessor extends AudioWorkletProcessor {
    constructor(options) {
        super();
        this.buffer = [];
        this.targetSize = options.processorOptions?.bufferSize || 3;
        this.port.onmessage = (event) => {
            if (event.data.type === 'audio') {
                this.buffer.push(new Float32Array(event.data.data));
            }
        };
    }
    
    process(inputs, outputs) {
        const output = outputs[0];
        if (!output || !output[0]) return true;
        
        const outputChannel = output[0];
        if (this.buffer.length < this.targetSize) {
            outputChannel.fill(0);
            return true;
        }
        
        let framesWritten = 0;
        while (framesWritten < outputChannel.length && this.buffer.length > 0) {
            const chunk = this.buffer[0];
            const framesToCopy = Math.min(chunk.length, outputChannel.length - framesWritten);
            outputChannel.set(chunk.subarray(0, framesToCopy), framesWritten);
            framesWritten += framesToCopy;
            
            if (framesToCopy === chunk.length) {
                this.buffer.shift();
            } else {
                this.buffer[0] = chunk.subarray(framesToCopy);
            }
        }
        
        if (framesWritten < outputChannel.length) {
            outputChannel.fill(0, framesWritten);
        }
        
        return true;
    }
}

registerProcessor('audio-processor', AudioProcessor);