// Audio Monitor - Cliente Web con soporte WebRTC/WebSocket dual

class AudioMonitor {
    constructor() {
        this.socket = null;
        this.webrtcClient = null;
        this.audioContext = null;
        this.deviceInfo = null;
        this.activeChannels = new Set();
        this.channelProcessors = {};
        this.audioWorkletReady = false;
        
        // Configuración de protocolo
        this.useWebRTC = this.detectWebRTCSupport();
        this.protocol = 'webrtc'; // Por defecto WebRTC
        this.preferredProtocol = localStorage.getItem('audioMonitor_preferredProtocol') || 'webrtc';
        this.autoSwitchProtocol = true;
        this.webrtcConnected = false;
        
        // Métricas combinadas
        this.metrics = {
            networkLatency: 0,
            bufferHealth: 100,
            estimatedLatency: 0,
            protocol: 'WebRTC',
            audioLatency: 0,
            packetLoss: 0,
            connectionQuality: 'unknown',
            bytesReceived: 0,
            jitter: 0
        };
        
        // Estado
        this.connected = false;
        this.audioInitialized = false;
        this.connectionStartTime = 0;
        this.protocolSwitchCount = 0;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 3;
        
        // UI elements cache
        this.uiElements = {};
        
        this.init();
    }

    async init() {
        console.log('[AudioMonitor] Inicializando... WebRTC disponible:', this.useWebRTC);
        this.connectionStartTime = Date.now();
        
        // Cache UI elements
        this.cacheUIElements();
        
        // Actualizar UI inicial
        this.updateStatus('Conectando...', 'connecting');
        this.updateProtocolDisplay('WebRTC');
        
        // Conectar WebSocket (siempre necesario para señalización)
        await this.connectWebSocket();
        
        // Configurar event listeners
        this.setupEventListeners();
        
        // Iniciar monitorización de métricas
        this.startMetricsMonitoring();
    }
    
    cacheUIElements() {
        this.uiElements = {
            status: document.getElementById('status'),
            deviceInfo: document.getElementById('device-info'),
            latency: document.getElementById('latency'),
            bufferHealth: document.getElementById('buffer-health'),
            networkLatency: document.getElementById('network-latency'),
            protocolValue: document.getElementById('protocol-value'),
            channelsGrid: document.getElementById('channels-grid'),
            helpMessage: document.getElementById('help-message'),
            audioInitBtn: document.getElementById('audio-init-btn'),
            protocolInfo: document.getElementById('protocol-info') || this.createProtocolInfoElement()
        };
    }
    
    createProtocolInfoElement() {
        const metricsPanel = document.querySelector('.metrics-panel');
        if (!metricsPanel) return null;
        
        const protocolDiv = document.createElement('div');
        protocolDiv.className = 'metric';
        protocolDiv.id = 'protocol-info';
        protocolDiv.innerHTML = `
            <span class="metric-label">Protocolo</span>
            <span id="protocol-value" class="metric-value">WebRTC</span>
            <span class="metric-unit">-</span>
        `;
        metricsPanel.appendChild(protocolDiv);
        
        return protocolDiv;
    }
    
    detectWebRTCSupport() {
        const supported = !!(window.RTCPeerConnection && window.RTCSessionDescription);
        console.log(`[AudioMonitor] WebRTC soportado: ${supported}`);
        
        if (!supported) {
            console.warn('[AudioMonitor] WebRTC no está disponible en este navegador');
            this.showWarning('WebRTC no está disponible. Usando WebSocket.');
            this.protocol = 'websocket';
            this.metrics.protocol = 'WebSocket';
        }
        
        return supported;
    }
    
    showWarning(message) {
        const warningEl = document.createElement('div');
        warningEl.id = 'webrtc-warning';
        warningEl.className = 'warning-message';
        warningEl.style.cssText = `
            position: fixed;
            top: 10px;
            right: 10px;
            background: #ff9800;
            color: white;
            padding: 10px 20px;
            border-radius: 5px;
            margin: 10px 0;
            text-align: center;
            z-index: 1000;
            max-width: 300px;
        `;
        warningEl.textContent = `⚠️ ${message}`;
        document.body.appendChild(warningEl);
        
        setTimeout(() => {
            warningEl.style.display = 'none';
        }, 5000);
    }
    
    async connectWebSocket() {
        console.log('[AudioMonitor] Conectando WebSocket para señalización...');
        
        this.socket = io({
            transports: ['websocket'],
            upgrade: false,
            reconnection: true,
            reconnectionDelay: 1000,
            reconnectionAttempts: 5
        });
        
        this.socket.on('connect', () => {
            console.log('[Socket] Conectado para señalización');
            this.updateStatus('Conectado (señalización)', 'connected');
            this.connected = true;
            
            // Si WebRTC está disponible, intentar conectar
            if (this.useWebRTC && this.preferredProtocol === 'webrtc') {
                this.initWebRTC();
            } else {
                // Mostrar botón de inicio para WebSocket
                this.showWebSocketInitButton();
            }
            
            // Re-suscribir canales activos si hay reconexión
            if (this.activeChannels.size > 0) {
                setTimeout(() => this.updateSubscription(), 500);
            }
        });
        
        this.socket.on('disconnect', (reason) => {
            console.log('[Socket] Desconectado:', reason);
            this.updateStatus('Desconectado', 'disconnected');
            this.connected = false;
            
            // Cerrar WebRTC si existe
            if (this.webrtcClient) {
                this.webrtcClient.close();
                this.webrtcClient = null;
                this.webrtcConnected = false;
            }
            
            // Intentar reconexión
            if (this.reconnectAttempts < this.maxReconnectAttempts) {
                this.reconnectAttempts++;
                setTimeout(() => {
                    console.log(`[Socket] Reintento ${this.reconnectAttempts}/${this.maxReconnectAttempts}`);
                    this.socket.connect();
                }, 1000 * this.reconnectAttempts);
            }
        });
        
        this.socket.on('device_info', (info) => {
            this.handleDeviceInfo(info);
        });
        
        // WebSocket audio (solo si estamos usando WebSocket como fallback)
        this.socket.on('audio', (data) => {
            if (this.protocol === 'websocket') {
                this.handleAudioData(data);
            }
        });
        
        this.socket.on('pong', (data) => {
            if (this.protocol === 'websocket') {
                const latency = Date.now() - data.client_timestamp;
                this.updateNetworkLatency(latency);
            }
        });
        
        // WebRTC events
        this.socket.on('webrtc_answer', (data) => {
            if (this.webrtcClient) {
                this.webrtcClient.handleAnswer(data);
            }
        });
        
        this.socket.on('webrtc_ice_candidate', (data) => {
            if (this.webrtcClient) {
                this.webrtcClient.handleRemoteIceCandidate(data);
            }
        });
        
        this.socket.on('webrtc_error', (data) => {
            console.error('[WebRTC] Error del servidor:', data.error);
            this.handleWebRTCError(data.error);
        });
        
        this.socket.on('webrtc_subscribed', (data) => {
            console.log('[WebRTC] Suscripción confirmada:', data.channels);
        });
        
        // Ping para WebSocket (solo cuando se usa WebSocket)
        setInterval(() => {
            if (this.socket && this.socket.connected && this.protocol === 'websocket') {
                this.socket.emit('ping', { timestamp: Date.now() });
            }
        }, 2000);
    }
    
    handleDeviceInfo(info) {
        this.deviceInfo = info;
        this.displayDeviceInfo(info);
        this.createChannelGrid(info.channels);
        
        console.log('[Device] Info recibida, WebRTC soportado:', info.supports_webrtc);
        
        // Determinar protocolo a usar
        this.determineProtocol(info);
        
        if (this.protocol === 'webrtc' && info.supports_webrtc) {
            // Intentar WebRTC automáticamente
            this.initWebRTC();
        } else {
            // Usar WebSocket
            this.showWebSocketInitButton();
        }
    }
    
    determineProtocol(info) {
        const canUseWebRTC = this.useWebRTC && info.supports_webrtc && info.webrtc_enabled !== false;
        
        if (this.preferredProtocol === 'webrtc' && canUseWebRTC) {
            this.protocol = 'webrtc';
            console.log('[AudioMonitor] Usando WebRTC (preferido)');
        } else if (this.preferredProtocol === 'websocket') {
            this.protocol = 'websocket';
            console.log('[AudioMonitor] Usando WebSocket (preferido)');
        } else if (canUseWebRTC) {
            this.protocol = 'webrtc';
            console.log('[AudioMonitor] Usando WebRTC (auto)');
        } else {
            this.protocol = 'websocket';
            console.log('[AudioMonitor] Usando WebSocket (fallback)');
        }
        
        this.metrics.protocol = this.protocol === 'webrtc' ? 'WebRTC' : 'WebSocket';
        this.updateProtocolDisplay(this.metrics.protocol);
    }
    
    async initWebRTC() {
        if (!this.useWebRTC || !this.socket?.connected) {
            console.log('[WebRTC] No disponible o no conectado');
            this.fallbackToWebSocket('WebRTC no disponible');
            return;
        }
        
        try {
            console.log('[AudioMonitor] Iniciando WebRTC...');
            this.updateStatus('Conectando WebRTC...', 'connecting');
            
            this.webrtcClient = new WebRTCClient(this.socket, this.socket.id);
            
            // Configurar callbacks
            this.webrtcClient.onAudioConnected = () => {
                console.log('[WebRTC] Audio conectado');
                this.handleWebRTCConnected();
            };
            
            this.webrtcClient.onConnected = () => {
                console.log('[WebRTC] Conexión establecida');
                this.webrtcConnected = true;
                this.protocol = 'webrtc';
                this.metrics.protocol = 'WebRTC';
                this.updateProtocolDisplay('WebRTC');
                
                // Re-suscribir canales si es reconexión
                if (this.activeChannels.size > 0) {
                    const channels = Array.from(this.activeChannels);
                    const gains = {};
                    channels.forEach(ch => {
                        gains[ch] = this.channelProcessors[ch]?.gain || 1.0;
                    });
                    
                    this.webrtcClient.subscribe(channels, gains);
                }
                
                // Ocultar botón de inicio
                this.hideInitButton();
            };
            
            this.webrtcClient.onDisconnected = () => {
                console.log('[WebRTC] Desconectado');
                this.webrtcConnected = false;
                
                if (this.protocol === 'webrtc' && this.autoSwitchProtocol && this.protocolSwitchCount < 2) {
                    this.fallbackToWebSocket('WebRTC desconectado');
                }
            };
            
            this.webrtcClient.onError = (error) => {
                console.error('[WebRTC] Error:', error);
                this.handleWebRTCError(error.message || 'Error desconocido');
            };
            
            // Conectar WebRTC
            const success = await this.webrtcClient.connect();
            if (!success) {
                throw new Error('No se pudo conectar WebRTC');
            }
            
        } catch (error) {
            console.error('[AudioMonitor] Error iniciando WebRTC:', error);
            this.fallbackToWebSocket(`Error WebRTC: ${error.message}`);
        }
    }
    
    handleWebRTCConnected() {
        this.audioInitialized = true;
        this.protocol = 'webrtc';
        this.metrics.protocol = 'WebRTC';
        
        // Actualizar UI
        this.updateStatus('Conectado (WebRTC)', 'connected');
        this.updateProtocolDisplay('WebRTC');
        this.hideInitButton();
        
        // Calcular latencia estimada
        this.calculateEstimatedLatency();
        
        console.log('[AudioMonitor] WebRTC completamente conectado');
        
        // Guardar preferencia
        localStorage.setItem('audioMonitor_preferredProtocol', 'webrtc');
    }
    
    handleWebRTCError(errorMessage) {
        console.error('[WebRTC] Error crítico:', errorMessage);
        
        if (this.autoSwitchProtocol && this.protocolSwitchCount < 2) {
            this.fallbackToWebSocket(`WebRTC error: ${errorMessage}`);
        } else {
            this.showError(`Error WebRTC: ${errorMessage}`);
        }
    }
    
    fallbackToWebSocket(reason) {
        console.log(`[AudioMonitor] Fallback a WebSocket: ${reason}`);
        this.protocolSwitchCount++;
        
        this.protocol = 'websocket';
        this.metrics.protocol = 'WebSocket';
        
        // Cerrar WebRTC si existe
        if (this.webrtcClient) {
            this.webrtcClient.close();
            this.webrtcClient = null;
            this.webrtcConnected = false;
        }
        
        // Actualizar UI
        this.updateProtocolDisplay('WebSocket');
        this.showWebSocketInitButton();
        
        console.log('[AudioMonitor] Cambiado a WebSocket');
    }
    
    showWebSocketInitButton() {
        const btn = this.uiElements.audioInitBtn;
        if (btn) {
            btn.style.display = 'block';
            btn.textContent = '🔊 Iniciar Audio (WebSocket)';
            btn.onclick = () => this.initWebSocketAudio();
        }
    }
    
    hideInitButton() {
        const btn = this.uiElements.audioInitBtn;
        if (btn) {
            btn.style.display = 'none';
        }
    }
    
    async initWebSocketAudio() {
        if (this.audioContext) return true;
        
        if (!this.deviceInfo) {
            console.warn('[Audio] Esperando device_info...');
            return false;
        }
        
        try {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
                latencyHint: 'interactive',
                sampleRate: this.deviceInfo.sample_rate
            });
            
            console.log(`[Audio] Context WebSocket creado: ${this.audioContext.sampleRate}Hz`);
            
            // Cargar AudioWorklet
            await this.loadAudioWorklet();
            
            // Ocultar botón
            this.hideInitButton();
            
            this.audioInitialized = true;
            this.protocol = 'websocket';
            this.metrics.protocol = 'WebSocket';
            
            this.calculateEstimatedLatency();
            this.updateStatus('Conectado (WebSocket)', 'connected');
            
            // Guardar preferencia
            localStorage.setItem('audioMonitor_preferredProtocol', 'websocket');
            
            return true;
            
        } catch (error) {
            console.error('[Audio] Error al inicializar WebSocket:', error);
            this.showError(`Error audio: ${error.message}`);
            return false;
        }
    }
    
    async loadAudioWorklet() {
        try {
            await this.audioContext.audioWorklet.addModule('/audio-processor.js');
            console.log('[AudioWorklet] Cargado correctamente');
            return true;
        } catch (error) {
            console.error('[AudioWorklet] Error al cargar:', error);
            return false;
        }
    }
    
    displayDeviceInfo(info) {
        const el = this.uiElements.deviceInfo;
        if (el) {
            const protocolBadge = info.supports_webrtc ? 
                '<span style="color:#4CAF50; font-weight:bold;"> ⚡ WebRTC</span>' : 
                '<span style="color:#FF9800;"> WebSocket</span>';
            
            el.innerHTML = `
                <strong>${info.name}</strong> | 
                ${info.channels} canales | 
                ${info.sample_rate} Hz | 
                Buffer: ${info.blocksize} samples
                ${protocolBadge}
            `;
        }
    }
    
    createChannelGrid(numChannels) {
        const grid = this.uiElements.channelsGrid;
        const helpMsg = this.uiElements.helpMessage;
        
        if (!grid) return;
        
        grid.innerHTML = '';
        
        if (helpMsg) {
            helpMsg.style.display = 'none';
        }
        
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
        grid.querySelectorAll('.channel-toggle').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const channel = parseInt(e.target.dataset.channel);
                this.toggleChannel(channel, e.target);
            });
        });
        
        grid.querySelectorAll('.volume-slider').forEach(slider => {
            slider.addEventListener('input', (e) => {
                const channel = parseInt(e.target.dataset.channel);
                const db = parseFloat(e.target.value);
                const gain = this.dbToGain(db);
                
                e.target.nextElementSibling.textContent = `${db > 0 ? '+' : ''}${db} dB`;
                this.updateChannelGain(channel, gain);
            });
        });
        
        // Agregar controles de protocolo
        this.addProtocolControls();
    }
    
    addProtocolControls() {
        const grid = this.uiElements.channelsGrid;
        if (!grid) return;
        
        const controlsDiv = document.createElement('div');
        controlsDiv.className = 'channel';
        controlsDiv.style.gridColumn = '1 / -1';
        controlsDiv.style.textAlign = 'center';
        controlsDiv.style.padding = '20px';
        controlsDiv.style.backgroundColor = '#2a2a2a';
        controlsDiv.style.marginTop = '20px';
        
        controlsDiv.innerHTML = `
            <h3 style="margin-bottom: 15px; color: #e0e0e0;">Configuración de Protocolo</h3>
            <div style="display: flex; justify-content: center; gap: 15px; flex-wrap: wrap; margin-bottom: 15px;">
                <button id="btn-webrtc" class="protocol-btn" 
                        style="background: ${this.protocol === 'webrtc' ? '#4CAF50' : '#444'}; 
                               color: white; padding: 10px 20px; border: none; border-radius: 8px; 
                               cursor: pointer; font-weight: bold; transition: all 0.3s;">
                    ⚡ WebRTC (3-15ms)
                </button>
                <button id="btn-websocket" class="protocol-btn"
                        style="background: ${this.protocol === 'websocket' ? '#2196F3' : '#444'}; 
                               color: white; padding: 10px 20px; border: none; border-radius: 8px; 
                               cursor: pointer; font-weight: bold; transition: all 0.3s;">
                    🌐 WebSocket (20-40ms)
                </button>
            </div>
            <p style="color: #888; font-size: 0.9em;">
                Latencia actual: <span id="current-latency-display">--</span>ms | 
                Protocolo actual: <span id="current-protocol-display">${this.metrics.protocol}</span>
            </p>
        `;
        
        grid.appendChild(controlsDiv);
        
        // Event listeners para botones de protocolo
        document.getElementById('btn-webrtc').addEventListener('click', () => {
            this.switchProtocol('webrtc');
        });
        
        document.getElementById('btn-websocket').addEventListener('click', () => {
            this.switchProtocol('websocket');
        });
    }
    
    switchProtocol(newProtocol) {
        if (newProtocol === this.protocol) return;
        
        console.log(`[AudioMonitor] Cambiando protocolo: ${this.protocol} -> ${newProtocol}`);
        
        // Guardar canales activos
        const activeChannels = Array.from(this.activeChannels);
        const gains = {};
        activeChannels.forEach(ch => {
            gains[ch] = this.channelProcessors[ch]?.gain || 1.0;
        });
        
        // Cerrar conexión actual
        if (this.protocol === 'webrtc' && this.webrtcClient) {
            this.webrtcClient.close();
            this.webrtcClient = null;
            this.webrtcConnected = false;
        }
        
        if (this.protocol === 'websocket' && this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
            this.channelProcessors = {};
        }
        
        // Actualizar protocolo
        this.protocol = newProtocol;
        this.preferredProtocol = newProtocol;
        
        // Guardar preferencia
        localStorage.setItem('audioMonitor_preferredProtocol', this.preferredProtocol);
        
        // Reiniciar conexión
        if (this.protocol === 'webrtc') {
            this.initWebRTC();
        } else if (this.protocol === 'websocket') {
            this.showWebSocketInitButton();
            this.updateStatus('Listo para WebSocket', 'connecting');
        }
        
        this.protocolSwitchCount++;
        
        // Actualizar UI
        this.updateProtocolButtons();
    }
    
    updateProtocolButtons() {
        const webrtcBtn = document.getElementById('btn-webrtc');
        const websocketBtn = document.getElementById('btn-websocket');
        
        if (webrtcBtn) {
            webrtcBtn.style.background = this.protocol === 'webrtc' ? '#4CAF50' : '#444';
        }
        
        if (websocketBtn) {
            websocketBtn.style.background = this.protocol === 'websocket' ? '#2196F3' : '#444';
        }
        
        const protocolDisplay = document.getElementById('current-protocol-display');
        if (protocolDisplay) {
            protocolDisplay.textContent = this.metrics.protocol;
            protocolDisplay.style.color = this.protocol === 'webrtc' ? '#4CAF50' : '#2196F3';
        }
    }
    
    async toggleChannel(channel, button) {
        // Iniciar audio según protocolo
        if (this.protocol === 'websocket' && !this.audioContext) {
            const success = await this.initWebSocketAudio();
            if (!success) return;
        } else if (this.protocol === 'webrtc' && !this.webrtcConnected) {
            await this.initWebRTC();
            // Esperar un momento para que WebRTC se conecte
            await new Promise(resolve => setTimeout(resolve, 500));
        }
        
        const channelDiv = button.closest('.channel');
        
        if (this.activeChannels.has(channel)) {
            // Desactivar
            this.activeChannels.delete(channel);
            button.classList.remove('active');
            channelDiv.classList.remove('active');
            
            if (this.channelProcessors[channel]) {
                if (this.protocol === 'websocket') {
                    this.channelProcessors[channel].gainNode.disconnect();
                    if (this.channelProcessors[channel].workletNode) {
                        this.channelProcessors[channel].workletNode.disconnect();
                    }
                }
                delete this.channelProcessors[channel];
            }
        } else {
            // Activar
            this.activeChannels.add(channel);
            button.classList.add('active');
            channelDiv.classList.add('active');
            
            if (this.protocol === 'websocket') {
                this.createChannelProcessor(channel);
            }
        }
        
        // Actualizar suscripción
        this.updateSubscription();
    }
    
    createChannelProcessor(channel) {
        // Solo para WebSocket
        if (this.protocol !== 'websocket' || !this.audioContext) return;
        
        try {
            // Calcular buffer size
            const bufferSize = Math.max(3, Math.ceil(
                (this.deviceInfo.jitter_buffer_ms / 1000) * 
                this.deviceInfo.sample_rate / 
                this.deviceInfo.blocksize
            ));
            
            // Crear AudioWorkletNode
            const workletNode = new AudioWorkletNode(this.audioContext, 'audio-processor', {
                processorOptions: { bufferSize }
            });
            
            // GainNode para control de volumen
            const gainNode = this.audioContext.createGain();
            gainNode.gain.value = 1.0;
            
            workletNode.connect(gainNode);
            gainNode.connect(this.audioContext.destination);
            
            // Escuchar métricas del worklet
            workletNode.port.onmessage = (event) => {
                if (event.data.type === 'bufferHealth') {
                    this.metrics.bufferHealth = event.data.value;
                }
            };
            
            this.channelProcessors[channel] = {
                workletNode: workletNode,
                gainNode: gainNode,
                gain: 1.0
            };
            
            console.log(`[Canal ${channel}] Processor creado`);
            
        } catch (error) {
            console.error(`[Canal ${channel}] Error:`, error);
        }
    }
    
    updateSubscription() {
        const channels = Array.from(this.activeChannels);
        const gains = {};
        
        channels.forEach(ch => {
            gains[ch] = this.channelProcessors[ch]?.gain || 1.0;
        });
        
        if (this.protocol === 'websocket' && this.socket?.connected) {
            this.socket.emit('subscribe', { channels, gains });
            console.log('[WebSocket] Suscripción actualizada:', channels);
        } else if (this.protocol === 'webrtc' && this.webrtcClient?.isConnected()) {
            this.webrtcClient.subscribe(channels, gains);
        }
    }
    
    updateChannelGain(channel, gain) {
        if (this.channelProcessors[channel]) {
            this.channelProcessors[channel].gain = gain;
            this.channelProcessors[channel].gainNode.gain.value = gain;
        }
        
        // Enviar al servidor
        if (this.protocol === 'websocket' && this.socket?.connected) {
            this.socket.emit('update_gain', { channel, gain });
        } else if (this.protocol === 'webrtc' && this.webrtcClient?.isConnected()) {
            this.webrtcClient.updateGain(channel, gain);
        }
    }
    
    handleAudioData(data) {
        if (this.protocol !== 'websocket') return;
        
        const view = new DataView(data);
        const channel = view.getUint32(0, true);
        
        if (!this.activeChannels.has(channel)) return;
        
        const numSamples = (data.byteLength - 4) / 4;
        const audioData = new Float32Array(data, 4, numSamples);
        
        if (audioData.length === 0) return;
        
        const channelData = this.channelProcessors[channel];
        if (!channelData) return;
        
        if (channelData.workletNode) {
            channelData.workletNode.port.postMessage({
                type: 'audio',
                data: audioData
            });
        }
    }
    
    calculateEstimatedLatency() {
        if (!this.deviceInfo) return;
        
        const captureLatency = (this.deviceInfo.blocksize / this.deviceInfo.sample_rate * 1000);
        const jitterBuffer = this.deviceInfo.jitter_buffer_ms;
        
        let networkLatency = 10; // default
        
        if (this.protocol === 'websocket') {
            networkLatency = this.metrics.networkLatency || 15;
        } else if (this.protocol === 'webrtc' && this.webrtcClient) {
            networkLatency = this.webrtcClient.getLatency() || 8;
        }
        
        let contextLatency = 0;
        if (this.audioContext) {
            contextLatency = (this.audioContext.baseLatency + this.audioContext.outputLatency) * 1000;
        }
        
        this.metrics.estimatedLatency = 
            captureLatency + 
            jitterBuffer + 
            networkLatency +
            contextLatency + 5;
    }
    
    updateNetworkLatency(latency) {
        this.metrics.networkLatency = this.metrics.networkLatency * 0.8 + latency * 0.2;
        this.calculateEstimatedLatency();
    }
    
    startMetricsMonitoring() {
        setInterval(() => {
            this.updateMetricsDisplay();
        }, 100);
    }
    
    updateMetricsDisplay() {
        // Obtener métricas según protocolo
        if (this.protocol === 'webrtc' && this.webrtcClient) {
            const webrtcMetrics = this.webrtcClient.getMetrics();
            this.metrics.audioLatency = webrtcMetrics.audioLatency || webrtcMetrics.connectionLatency || 0;
            this.metrics.packetLoss = webrtcMetrics.packetLoss || 0;
            this.metrics.jitter = webrtcMetrics.jitter || 0;
            this.metrics.bytesReceived = webrtcMetrics.bytesReceived || 0;
            this.metrics.connectionQuality = webrtcMetrics.quality || 'unknown';
            
            // Usar latencia de WebRTC para cálculo estimado
            this.metrics.estimatedLatency = this.metrics.audioLatency || this.metrics.estimatedLatency;
            
        } else if (this.protocol === 'websocket') {
            this.metrics.protocol = 'WebSocket';
            this.calculateEstimatedLatency();
        }
        
        // Actualizar elementos UI
        this.updateMetricElement('latency', Math.round(this.metrics.estimatedLatency), [15, 30], 'ms');
        
        this.updateMetricElement('buffer-health', Math.round(this.metrics.bufferHealth), [50, 150], '%', true);
        
        const networkValue = this.protocol === 'webrtc' ? 
            this.metrics.audioLatency : this.metrics.networkLatency;
        this.updateMetricElement('network-latency', Math.round(networkValue), [10, 25], 'ms');
        
        // Actualizar protocolo display
        this.updateProtocolDisplay(this.metrics.protocol);
        
        // Actualizar display de latencia actual
        const latencyDisplay = document.getElementById('current-latency-display');
        if (latencyDisplay) {
            latencyDisplay.textContent = Math.round(this.metrics.estimatedLatency);
            latencyDisplay.style.color = this.getLatencyColor(this.metrics.estimatedLatency);
        }
        
        // Actualizar calidad de conexión
        this.updateConnectionQuality();
        
        // Actualizar botones de protocolo
        this.updateProtocolButtons();
    }
    
    updateMetricElement(id, value, thresholds, unit, invert = false) {
        const element = document.getElementById(id);
        if (!element) return;
        
        element.textContent = value;
        
        let className = 'bad';
        if (!invert) {
            if (value <= thresholds[0]) className = 'good';
            else if (value <= thresholds[1]) className = 'warning';
        } else {
            if (value >= thresholds[0] && value <= thresholds[1]) className = 'good';
            else if (value > thresholds[1]) className = 'warning';
        }
        
        element.className = `metric-value ${className}`;
    }
    
    getLatencyColor(latency) {
        if (latency <= 15) return '#4CAF50';
        if (latency <= 30) return '#FF9800';
        return '#f44336';
    }
    
    updateProtocolDisplay(protocol) {
        const el = this.uiElements.protocolValue;
        if (el) {
            el.textContent = protocol;
            el.className = 'metric-value ' + 
                (protocol === 'WebRTC' ? 'good' : 'warning');
        }
    }
    
    updateConnectionQuality() {
        const quality = this.metrics.connectionQuality;
        const statusEl = this.uiElements.status;
        
        if (statusEl && quality !== 'unknown') {
            const qualityColors = {
                'excellent': '#4CAF50',
                'good': '#8BC34A',
                'fair': '#FF9800',
                'poor': '#FF5722',
                'bad': '#f44336'
            };
            
            statusEl.style.borderLeft = `4px solid ${qualityColors[quality] || '#666'}`;
        }
    }
    
    updateStatus(message, type) {
        const statusEl = this.uiElements.status;
        if (statusEl) {
            statusEl.textContent = message;
            statusEl.className = `status-${type}`;
        }
    }
    
    showError(message) {
        this.updateStatus(`Error: ${message}`, 'disconnected');
        console.error('[AudioMonitor]', message);
        
        // Mostrar notificación temporal
        const notification = document.createElement('div');
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #f44336;
            color: white;
            padding: 15px;
            border-radius: 5px;
            z-index: 1000;
            max-width: 300px;
        `;
        notification.textContent = message;
        document.body.appendChild(notification);
        
        setTimeout(() => notification.remove(), 5000);
    }
    
    dbToGain(db) {
        return Math.pow(10, db / 20);
    }
    
    setupEventListeners() {
        // Botón de inicio de audio
        const initBtn = this.uiElements.audioInitBtn;
        if (initBtn) {
            initBtn.onclick = () => {
                if (this.protocol === 'websocket') {
                    this.initWebSocketAudio();
                } else if (this.protocol === 'webrtc') {
                    this.initWebRTC();
                }
            };
        }
        
        // Detectar cambios de visibilidad de página
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                console.log('[AudioMonitor] Página en segundo plano');
            } else {
                console.log('[AudioMonitor] Página en primer plano');
                // Reanudar audio si es necesario
                if (this.audioContext && this.audioContext.state === 'suspended') {
                    this.audioContext.resume();
                }
            }
        });
    }
}

// Iniciar aplicación cuando el DOM esté listo
document.addEventListener('DOMContentLoaded', () => {
    window.audioMonitor = new AudioMonitor();
});