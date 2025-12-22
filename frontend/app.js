// Audio Monitor - Cliente Web

class AudioMonitor {
    constructor() {
        this.socket = null;
        this.audioContext = null;
        this.channels = {};
        this.deviceInfo = null;
        this.jitterBuffers = {};
        this.activeChannels = new Set();
        
        this.init();
    }

    async init() {
        // Conectar WebSocket
        this.socket = io();
        
        this.socket.on('connect', () => {
            this.updateStatus('Conectado', 'success');
        });
        
        this.socket.on('disconnect', () => {
            this.updateStatus('Desconectado', 'error');
        });
        
        this.socket.on('device_info', (info) => {
            this.deviceInfo = info;
            this.displayDeviceInfo(info);
            this.createChannelGrid(info.channels);
        });
        
        this.socket.on('audio', (data) => {
            this.handleAudioData(data);
        });
    }

    async initAudioContext() {
        if (this.audioContext) return;
        
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
            latencyHint: 0.005, // 5ms mínimo
            sampleRate: this.deviceInfo.sample_rate
        });
        
        console.log(`AudioContext iniciado: ${this.audioContext.sampleRate} Hz, latencia: ${this.audioContext.baseLatency * 1000}ms`);
        
        // Estimación de latencia total
        const estimatedLatency = 
            (this.deviceInfo.blocksize / this.deviceInfo.sample_rate * 1000) + // Captura
            20 + // Jitter buffer
            (this.audioContext.baseLatency * 1000) + // Web Audio
            10; // Red/procesamiento
        
        document.getElementById('latency').textContent = Math.round(estimatedLatency);
    }

    displayDeviceInfo(info) {
        document.getElementById('device-info').innerHTML = `
            <strong>${info.name}</strong> | 
            ${info.channels} canales | 
            ${info.sample_rate} Hz
        `;
    }

    createChannelGrid(numChannels) {
        const grid = document.getElementById('channels-grid');
        grid.innerHTML = '';
        
        for (let i = 0; i < numChannels; i++) {
            const channelDiv = document.createElement('div');
            channelDiv.className = 'channel';
            channelDiv.innerHTML = `
                <div class="channel-header">
                    <button class="channel-toggle" data-channel="${i}">
                        Canal ${i + 1}
                    </button>
                </div>
                <div class="channel-controls">
                    <label>Volumen</label>
                    <input type="range" class="volume-slider" 
                           data-channel="${i}"
                           min="-60" max="12" value="0" step="1">
                    <span class="volume-value">0 dB</span>
                </div>
            `;
            
            grid.appendChild(channelDiv);
        }
        
        // Event listeners
        document.querySelectorAll('.channel-toggle').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const channel = parseInt(e.target.dataset.channel);
                this.toggleChannel(channel, e.target);
            });
        });
        
        document.querySelectorAll('.volume-slider').forEach(slider => {
            slider.addEventListener('input', (e) => {
                const channel = parseInt(e.target.dataset.channel);
                const db = parseFloat(e.target.value);
                const gain = this.dbToGain(db);
                
                e.target.nextElementSibling.textContent = `${db} dB`;
                this.updateChannelGain(channel, gain);
            });
        });
    }

    async toggleChannel(channel, button) {
        // Iniciar AudioContext en primera interacción (requerido por navegadores)
        await this.initAudioContext();
        
        if (this.activeChannels.has(channel)) {
            // Desactivar
            this.activeChannels.delete(channel);
            button.classList.remove('active');
            
            if (this.channels[channel]) {
                this.channels[channel].gainNode.disconnect();
                delete this.channels[channel];
                delete this.jitterBuffers[channel];
            }
        } else {
            // Activar
            this.activeChannels.add(channel);
            button.classList.add('active');
            
            // Crear GainNode para este canal
            const gainNode = this.audioContext.createGain();
            gainNode.connect(this.audioContext.destination);
            
            // Crear ScriptProcessor para playback
            const bufferSize = 4096;
            const processor = this.audioContext.createScriptProcessor(bufferSize, 1, 1);
            
            this.channels[channel] = {
                gainNode: gainNode,
                processor: processor,
                gain: 1.0
            };
            
            // Jitter buffer
            this.jitterBuffers[channel] = {
                buffer: [],
                targetSize: Math.ceil((20 / 1000) * this.deviceInfo.sample_rate / this.deviceInfo.blocksize)
            };
            
            processor.onaudioprocess = (e) => {
                this.processAudio(channel, e);
            };
            
            processor.connect(gainNode);
        }
        
        // Enviar suscripción al servidor
        this.updateSubscription();
    }

    updateSubscription() {
        const channels = Array.from(this.activeChannels);
        const gains = {};
        
        channels.forEach(ch => {
            gains[ch] = this.channels[ch]?.gain || 1.0;
        });
        
        this.socket.emit('subscribe', { channels, gains });
    }

    updateChannelGain(channel, gain) {
        if (this.channels[channel]) {
            this.channels[channel].gain = gain;
            // Actualizar localmente (latencia 0)
            this.channels[channel].gainNode.gain.value = gain;
        }
    }

    handleAudioData(data) {
        // data es ArrayBuffer: [channel_id (1 byte)][audio samples (int16)]
        const view = new DataView(data);
        const channel = view.getUint8(0);
        
        if (!this.activeChannels.has(channel)) return;
        
        // Convertir int16 a float32
        const numSamples = (data.byteLength - 1) / 2;
        const audioData = new Float32Array(numSamples);
        
        for (let i = 0; i < numSamples; i++) {
            const int16Value = view.getInt16(1 + i * 2, true); // little-endian
            audioData[i] = int16Value / 32768.0;
        }
        
        // Agregar a jitter buffer
        if (this.jitterBuffers[channel]) {
            this.jitterBuffers[channel].buffer.push(audioData);
            
            // Limitar tamaño máximo (evitar acumulación infinita)
            if (this.jitterBuffers[channel].buffer.length > 50) {
                this.jitterBuffers[channel].buffer.shift();
            }
        }
    }

    processAudio(channel, event) {
        const output = event.outputBuffer.getChannelData(0);
        const jitterBuffer = this.jitterBuffers[channel];
        
        if (!jitterBuffer) return;
        
        let outputIndex = 0;
        
        // Esperar a tener suficientes datos antes de empezar
        if (jitterBuffer.buffer.length < jitterBuffer.targetSize) {
            // Silencio mientras se llena el buffer
            output.fill(0);
            return;
        }
        
        // Leer del buffer
        while (outputIndex < output.length && jitterBuffer.buffer.length > 0) {
            const chunk = jitterBuffer.buffer.shift();
            const copyLength = Math.min(chunk.length, output.length - outputIndex);
            
            output.set(chunk.subarray(0, copyLength), outputIndex);
            outputIndex += copyLength;
        }
        
        // Rellenar con silencio si no hay suficientes datos
        if (outputIndex < output.length) {
            output.fill(0, outputIndex);
        }
    }

    dbToGain(db) {
        return Math.pow(10, db / 20);
    }

    updateStatus(message, type) {
        const statusDiv = document.getElementById('status');
        statusDiv.textContent = message;
        statusDiv.className = type;
    }
}

// Iniciar aplicación
const monitor = new AudioMonitor();