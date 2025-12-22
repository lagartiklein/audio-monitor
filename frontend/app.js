// Audio Monitor - Cliente Web CORREGIDO

// Optimizado para latencia <25ms



class AudioMonitor {

    constructor() {

        this.socket = null;

        this.audioContext = null;

        this.channels = {};

        this.deviceInfo = null;

        this.activeChannels = new Set();

        this.audioWorkletReady = false;

        

        // MÃ©tricas

        this.metrics = {

            networkLatency: 0,

            bufferHealth: 0,

            estimatedLatency: 0,

            lastPingTime: 0

        };

        

        // Auto-init flag

        this.autoInitAttempted = false;

        

        this.init();

    }



    async init() {

        console.log('[AudioMonitor] Inicializando...');

        

        // Conectar WebSocket

        this.socket = io({

            transports: ['websocket'],

            upgrade: false,

            reconnection: true,

            reconnectionDelay: 1000,

            reconnectionAttempts: 5

        });

        

        this.socket.on('connect', () => {

            this.updateStatus('Conectado', 'connected');

            console.log('[Socket] Conectado');

            

            // Re-suscribir canales activos si hay reconexiÃ³n

            if (this.activeChannels.size > 0) {

                this.updateSubscription();

            }

        });

        

        this.socket.on('disconnect', (reason) => {

            this.updateStatus('Desconectado', 'disconnected');

            console.log('[Socket] Desconectado:', reason);

        });

        

        this.socket.on('device_info', (info) => {

            this.deviceInfo = info;

            this.displayDeviceInfo(info);

            this.createChannelGrid(info.channels);

            this.calculateEstimatedLatency();

            console.log('[Device] Info recibida:', info);

            

            // Mostrar botÃ³n de inicio si aÃºn no hay AudioContext

            if (!this.audioContext && !this.autoInitAttempted) {

                this.showInitButton();

            }

        });

        

        this.socket.on('audio', (data) => {

            this.handleAudioData(data);

        });

        

        this.socket.on('pong', (data) => {

            // CORREGIDO: Ambos timestamps en milisegundos

            const latency = Date.now() - data.client_timestamp;

            this.updateNetworkLatency(latency);

        });

        

        // Ping cada 2 segundos para medir latencia de red

        setInterval(() => {

            if (this.socket && this.socket.connected) {

                this.socket.emit('ping', { timestamp: Date.now() });

            }

        }, 2000);

        

        // Actualizar mÃ©tricas cada 100ms

        setInterval(() => {

            this.updateMetricsDisplay();

        }, 100);

    }



    showInitButton() {

        const initBtn = document.getElementById('audio-init-btn');

        if (initBtn) {

            initBtn.style.display = 'block';

            initBtn.onclick = () => this.initAudioContext();

        }

    }



    async initAudioContext() {

        if (this.audioContext) return true;

        

        if (!this.deviceInfo) {

            console.warn('[Audio] Esperando device_info...');

            return false;

        }

        

        try {

            this.autoInitAttempted = true;

            

            // Crear AudioContext con configuraciÃ³n Ã³ptima

            this.audioContext = new (window.AudioContext || window.webkitAudioContext)({

                latencyHint: 'interactive',

                sampleRate: this.deviceInfo.sample_rate

            });

            

            console.log(`[Audio] Context creado:`);

            console.log(`  Sample Rate: ${this.audioContext.sampleRate} Hz`);

            console.log(`  Base Latency: ${(this.audioContext.baseLatency * 1000).toFixed(1)}ms`);

            console.log(`  Output Latency: ${(this.audioContext.outputLatency * 1000).toFixed(1)}ms`);

            

            // Cargar AudioWorklet

            await this.loadAudioWorklet();

            

            // Ocultar botÃ³n de inicio

            const initBtn = document.getElementById('audio-init-btn');

            if (initBtn) initBtn.style.display = 'none';

            

            // Actualizar latencia estimada con valores reales

            this.calculateEstimatedLatency();

            

            return true;

            

        } catch (error) {

            console.error('[Audio] Error al inicializar:', error);

            alert('Error al inicializar audio. Intenta recargar la pÃ¡gina.');

            return false;

        }

    }



    async loadAudioWorklet() {

        try {

            await this.audioContext.audioWorklet.addModule('/audio-processor.js');

            this.audioWorkletReady = true;

            console.log('[AudioWorklet] Cargado correctamente');

        } catch (error) {

            console.error('[AudioWorklet] Error al cargar:', error);

            this.audioWorkletReady = false;

        }

    }



    displayDeviceInfo(info) {

        document.getElementById('device-info').innerHTML = `

            <strong>${info.name}</strong> | 

            ${info.channels} canales | 

            ${info.sample_rate} Hz | 

            Buffer: ${info.blocksize} samples (${(info.blocksize/info.sample_rate*1000).toFixed(1)}ms)

        `;

    }



    calculateEstimatedLatency() {

        if (!this.deviceInfo) return;

        

        const captureLatency = (this.deviceInfo.blocksize / this.deviceInfo.sample_rate * 1000);

        const jitterBuffer = this.deviceInfo.jitter_buffer_ms;

        const processingLatency = 2;

        const networkLatency = this.metrics.networkLatency || 10;

        

        // AÃ±adir latencias del AudioContext si estÃ¡ disponible

        let contextLatency = 0;

        if (this.audioContext) {

            contextLatency = (this.audioContext.baseLatency + this.audioContext.outputLatency) * 1000;

        }

        

        this.metrics.estimatedLatency = 

            captureLatency + 

            jitterBuffer + 

            processingLatency + 

            networkLatency +

            contextLatency;

    }



    createChannelGrid(numChannels) {

        const grid = document.getElementById('channels-grid');

        grid.innerHTML = '';

        

        const helpMsg = document.getElementById('help-message');

        if (helpMsg) helpMsg.style.display = 'none';

        

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

                

                e.target.nextElementSibling.textContent = `${db > 0 ? '+' : ''}${db} dB`;

                this.updateChannelGain(channel, gain);

            });

        });

    }



    async toggleChannel(channel, button) {

        // Iniciar AudioContext en primera interacciÃ³n

        if (!this.audioContext) {

            const success = await this.initAudioContext();

            if (!success) return;

        }

        

        const channelDiv = button.closest('.channel');

        

        if (this.activeChannels.has(channel)) {

            // Desactivar

            this.activeChannels.delete(channel);

            button.classList.remove('active');

            channelDiv.classList.remove('active');

            

            if (this.channels[channel]) {

                this.channels[channel].gainNode.disconnect();

                if (this.channels[channel].workletNode) {

                    this.channels[channel].workletNode.disconnect();

                }

                delete this.channels[channel];

            }

        } else {

            // Activar

            this.activeChannels.add(channel);

            button.classList.add('active');

            channelDiv.classList.add('active');

            

            this.createChannelProcessor(channel);

        }

        

        // Actualizar suscripciÃ³n

        this.updateSubscription();

    }



    createChannelProcessor(channel) {

        try {

            if (!this.audioWorkletReady) {

                console.warn('[Audio] AudioWorklet no disponible, usando fallback');

                this.createChannelProcessorFallback(channel);

                return;

            }

            

            // Calcular buffer size en tÃ©rminos de bloques

            const bufferSize = Math.max(3, Math.ceil(

                (this.deviceInfo.jitter_buffer_ms / 1000) * 

                this.deviceInfo.sample_rate / 

                this.deviceInfo.blocksize

            ));

            

            // Crear AudioWorkletNode

            const workletNode = new AudioWorkletNode(this.audioContext, 'audio-processor', {

                processorOptions: {

                    bufferSize: bufferSize

                }

            });

            

            // GainNode para control de volumen

            const gainNode = this.audioContext.createGain();

            gainNode.gain.value = 1.0;

            

            workletNode.connect(gainNode);

            gainNode.connect(this.audioContext.destination);

            

            // Escuchar mensajes del worklet

            workletNode.port.onmessage = (event) => {

                if (event.data.type === 'bufferHealth') {

                    this.metrics.bufferHealth = event.data.value;

                } else if (event.data.type === 'status') {

                    console.log(`[Canal ${channel}] ${event.data.status}`);

                }

            };

            

            this.channels[channel] = {

                workletNode: workletNode,

                gainNode: gainNode,

                gain: 1.0

            };

            

            console.log(`[Canal ${channel}] AudioWorklet creado (buffer: ${bufferSize} bloques)`);

            

        } catch (error) {

            console.error(`[Canal ${channel}] Error creando worklet:`, error);

            this.createChannelProcessorFallback(channel);

        }

    }



    createChannelProcessorFallback(channel) {

        console.log(`[Canal ${channel}] Usando ScriptProcessor (fallback)`);

        

        // Usar buffer mÃ¡s pequeÃ±o para reducir latencia

        const bufferSize = 2048;

        const processor = this.audioContext.createScriptProcessor(bufferSize, 1, 1);

        const gainNode = this.audioContext.createGain();

        gainNode.gain.value = 1.0;

        

        const jitterBuffer = [];

        const targetSize = Math.max(2, Math.ceil(

            (this.deviceInfo.jitter_buffer_ms / 1000) * 

            this.deviceInfo.sample_rate / 

            this.deviceInfo.blocksize

        ));

        

        processor.onaudioprocess = (e) => {

            const output = e.outputBuffer.getChannelData(0);

            let outputIndex = 0;

            

            // Buffering inicial

            if (jitterBuffer.length < targetSize) {

                output.fill(0);

                return;

            }

            

            // Llenar output desde buffer

            while (outputIndex < output.length && jitterBuffer.length > 0) {

                const chunk = jitterBuffer.shift();

                const copyLength = Math.min(chunk.length, output.length - outputIndex);

                output.set(chunk.subarray(0, copyLength), outputIndex);

                outputIndex += copyLength;

            }

            

            // Llenar resto con silencio

            if (outputIndex < output.length) {

                output.fill(0, outputIndex);

            }

            

            this.metrics.bufferHealth = (jitterBuffer.length / targetSize) * 100;

        };

        

        processor.connect(gainNode);

        gainNode.connect(this.audioContext.destination);

        

        this.channels[channel] = {

            processor: processor,

            gainNode: gainNode,

            jitterBuffer: jitterBuffer,

            targetSize: targetSize,

            gain: 1.0

        };

    }



    updateSubscription() {

        const channels = Array.from(this.activeChannels);

        const gains = {};

        

        channels.forEach(ch => {

            gains[ch] = this.channels[ch]?.gain || 1.0;

        });

        

        this.socket.emit('subscribe', { channels, gains });

        console.log('[Subscription] Canales:', channels);

    }



    updateChannelGain(channel, gain) {

        if (this.channels[channel]) {

            this.channels[channel].gain = gain;

            this.channels[channel].gainNode.gain.value = gain;

        }

    }



    handleAudioData(data) {

        // CORREGIDO: data es ArrayBuffer: [channel_id (uint32)][float32 samples]

        const view = new DataView(data);

        const channel = view.getUint32(0, true); // little-endian

        

        if (!this.activeChannels.has(channel)) return;

        

        // Extraer Float32Array (offset de 4 bytes por uint32)

        const numSamples = (data.byteLength - 4) / 4;

        const audioData = new Float32Array(data, 4, numSamples);

        

        // Validar datos

        if (audioData.length === 0) {

            console.warn(`[Canal ${channel}] Datos vacÃ­os recibidos`);

            return;

        }

        

        const channelData = this.channels[channel];

        if (!channelData) return;

        

        if (channelData.workletNode) {

            // AudioWorklet

            channelData.workletNode.port.postMessage({

                type: 'audio',

                data: audioData

            });

        } else if (channelData.jitterBuffer) {

            // Fallback

            channelData.jitterBuffer.push(audioData);

            

            // Limitar tamaÃ±o del buffer

            if (channelData.jitterBuffer.length > channelData.targetSize * 5) {

                channelData.jitterBuffer.shift();

            }

        }

    }



    updateNetworkLatency(latency) {

        // Suavizar latencia con promedio mÃ³vil

        this.metrics.networkLatency = this.metrics.networkLatency * 0.8 + latency * 0.2;

        this.calculateEstimatedLatency();

    }



    updateMetricsDisplay() {

        // Latencia total

        const latencyEl = document.getElementById('latency');

        if (latencyEl) {

            const latency = Math.round(this.metrics.estimatedLatency);

            latencyEl.textContent = latency;

            latencyEl.className = 'metric-value ' + 

                (latency <= 30 ? 'good' : latency <= 50 ? 'warning' : 'bad');

        }

        

        // Buffer health

        const bufferEl = document.getElementById('buffer-health');

        if (bufferEl) {

            const buffer = Math.round(this.metrics.bufferHealth);

            bufferEl.textContent = buffer;

            bufferEl.className = 'metric-value ' + 

                (buffer >= 50 && buffer <= 150 ? 'good' : buffer > 150 ? 'warning' : 'bad');

        }

        

        // Latencia de red

        const networkEl = document.getElementById('network-latency');

        if (networkEl) {

            const network = Math.round(this.metrics.networkLatency);

            networkEl.textContent = network;

            networkEl.className = 'metric-value ' + 

                (network <= 10 ? 'good' : network <= 25 ? 'warning' : 'bad');

        }

    }



    dbToGain(db) {

        return Math.pow(10, db / 20);

    }



    updateStatus(message, type) {

        const statusDiv = document.getElementById('status');

        if (statusDiv) {

            statusDiv.textContent = message;

            statusDiv.className = `status-${type}`;

        }

    }

}



// Iniciar aplicaciÃ³n

const monitor = new AudioMonitor();