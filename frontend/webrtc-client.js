/**
 * Cliente WebRTC para Audio Monitor
 * Latencia objetivo: 3-15ms
 */

class WebRTCClient {
    constructor(socket, clientId) {
        this.socket = socket;
        this.clientId = clientId;
        this.pc = null;
        this.dataChannel = null;
        this.audioContext = null;
        this.mediaStream = null;
        this.audioElement = null;
        this.audioNodes = [];
        
        // Configuración
        this.config = {
            audioCodec: 'opus',
            bitrate: 96000,
            frameDuration: 20, // ms
            useDtx: false,
            useFec: true,
            forceOpus: true,
            targetLatency: 15, // ms objetivo
            maxLatency: 30,    // ms máximo aceptable
            bufferSize: 2      // buffers en jitter buffer
        };
        
        // Métricas
        this.metrics = {
            connectionLatency: 0,
            audioLatency: 0,
            packetLoss: 0,
            jitter: 0,
            bytesReceived: 0,
            protocol: 'webrtc',
            connected: false,
            iceState: '',
            connectionState: '',
            quality: 'unknown',
            lastPacketTime: 0,
            packetGap: 0
        };
        
        // Estado
        this.connected = false;
        this.reconnecting = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 3;
        this.connectionStartTime = 0;
        
        // Buffer para métricas
        this.latencyMeasurements = [];
        this.maxLatencySamples = 10;
        
        // Interval IDs
        this.metricsInterval = null;
        this.latencyInterval = null;
        this.healthCheckInterval = null;
        
        console.log('[WebRTC] Cliente inicializado para', clientId);
    }
    
    async connect() {
        console.log('[WebRTC] Conectando...');
        this.connectionStartTime = Date.now();
        
        try {
            await this.createPeerConnection();
            return true;
        } catch (error) {
            console.error('[WebRTC] Error conectando:', error);
            this.handleError(error);
            return false;
        }
    }
    
    async createPeerConnection() {
        // Configuración optimizada para audio de baja latencia
        const configuration = {
            iceServers: [
                { urls: 'stun:stun.l.google.com:19302' },
                { urls: 'stun:stun1.l.google.com:19302' },
                { urls: 'stun:stun2.l.google.com:19302' }
            ],
            iceTransportPolicy: 'all',
            bundlePolicy: 'max-bundle',
            rtcpMuxPolicy: 'require',
            iceCandidatePoolSize: 0
        };
        
        // Crear PeerConnection
        this.pc = new RTCPeerConnection(configuration);
        
        // Configurar event handlers
        this.setupEventHandlers();
        
        // Crear oferta
        const offer = await this.pc.createOffer({
            offerToReceiveAudio: true,
            offerToReceiveVideo: false,
            voiceActivityDetection: false,
            iceRestart: false
        });
        
        // Optimizar SDP para baja latencia
        offer.sdp = this.optimizeSDP(offer.sdp);
        
        await this.pc.setLocalDescription(offer);
        
        // Enviar oferta al servidor via WebSocket
        this.socket.emit('webrtc_offer', {
            sdp: offer.sdp,
            clientId: this.clientId,
            timestamp: Date.now()
        });
        
        console.log('[WebRTC] Oferta enviada, SDP optimizado para baja latencia');
        
        // Iniciar monitorización
        this.startMetricsMonitoring();
        this.startHealthChecks();
        
        return true;
    }
    
    optimizeSDP(sdp) {
        let lines = sdp.split('\n');
        let optimized = [];
        
        for (let line of lines) {
            // Configurar Opus con parámetros de baja latencia
            if (line.includes('opus/48000')) {
                optimized.push(line);
                optimized.push('a=ptime:20');
                optimized.push('a=maxptime:60');
                optimized.push('a=minptime:10');
                if (this.config.useFec) {
                    optimized.push('a=useinbandfec:1');
                }
                if (this.config.useDtx) {
                    optimized.push('a=usedtx:1');
                }
            }
            // Eliminar video
            else if (line.startsWith('m=video')) {
                optimized.push('m=video 0 UDP/TLS/RTP/SAVPF 0');
            }
            // Eliminar otros codecs de video
            else if (line.includes('VP8') || line.includes('VP9') || line.includes('H264')) {
                continue;
            }
            // Mantener otras líneas
            else {
                optimized.push(line);
            }
        }
        
        // Agregar atributos adicionales
        optimized.push('a=setup:actpass');
        optimized.push('a=mid:audio0');
        optimized.push('a=sendrecv');
        optimized.push('a=rtcp-mux');
        
        return optimized.join('\n');
    }
    
    setupEventHandlers() {
        // ICE Candidate
        this.pc.onicecandidate = (event) => {
            if (event.candidate) {
                this.socket.emit('webrtc_ice_candidate', {
                    candidate: event.candidate,
                    clientId: this.clientId
                });
            } else {
                console.log('[WebRTC] ICE gathering completo');
            }
        };
        
        // ICE Connection State
        this.pc.oniceconnectionstatechange = () => {
            this.metrics.iceState = this.pc.iceConnectionState;
            console.log('[WebRTC] ICE state:', this.metrics.iceState);
            
            switch (this.metrics.iceState) {
                case 'connected':
                case 'completed':
                    this.handleConnected();
                    break;
                    
                case 'failed':
                    console.error('[WebRTC] ICE failed');
                    this.handleDisconnected();
                    break;
                    
                case 'disconnected':
                    console.warn('[WebRTC] ICE disconnected');
                    this.handleDisconnected();
                    break;
            }
        };
        
        // Connection State
        this.pc.onconnectionstatechange = () => {
            this.metrics.connectionState = this.pc.connectionState;
            console.log('[WebRTC] Connection state:', this.metrics.connectionState);
            
            if (this.metrics.connectionState === 'connected') {
                this.metrics.connected = true;
                this.connected = true;
            } else if (this.metrics.connectionState === 'failed' || 
                       this.metrics.connectionState === 'disconnected' ||
                       this.metrics.connectionState === 'closed') {
                this.metrics.connected = false;
                this.connected = false;
                this.handleDisconnected();
            }
        };
        
        // Track recibido (audio)
        this.pc.ontrack = (event) => {
            console.log('[WebRTC] Track recibido:', event.track.kind, 'id:', event.track.id);
            
            if (event.track.kind === 'audio') {
                this.handleAudioTrack(event.streams[0]);
            }
        };
        
        // Data Channel
        this.pc.ondatachannel = (event) => {
            this.dataChannel = event.channel;
            this.setupDataChannel();
        };
        
        // ICE Gathering State
        this.pc.onicegatheringstatechange = () => {
            console.log('[WebRTC] ICE gathering:', this.pc.iceGatheringState);
        };
        
        // Signaling State
        this.pc.onsignalingstatechange = () => {
            console.log('[WebRTC] Signaling:', this.pc.signalingState);
        };
        
        // Negotiation Needed
        this.pc.onnegotiationneeded = () => {
            console.log('[WebRTC] Negotiation needed');
        };
        
        // ICE Candidate Error
        this.pc.onicecandidateerror = (event) => {
            console.error('[WebRTC] ICE candidate error:', event);
        };
    }
    
    setupDataChannel() {
        this.dataChannel.onopen = () => {
            console.log('[WebRTC] DataChannel abierto, estado:', this.dataChannel.readyState);
            
            // Configurar DataChannel para baja latencia
            this.dataChannel.binaryType = 'arraybuffer';
            
            // Enviar configuración inicial
            setTimeout(() => {
                if (this.dataChannel.readyState === 'open') {
                    this.dataChannel.send(JSON.stringify({
                        type: 'get_config',
                        clientId: this.clientId,
                        timestamp: Date.now()
                    }));
                }
            }, 100);
            
            // Iniciar medición de latencia
            this.startLatencyMeasurement();
        };
        
        this.dataChannel.onmessage = (event) => {
            try {
                if (typeof event.data === 'string') {
                    const message = JSON.parse(event.data);
                    this.handleDataMessage(message);
                } else {
                    console.log('[WebRTC] Datos binarios recibidos:', event.data.byteLength, 'bytes');
                }
            } catch (error) {
                console.warn('[WebRTC] Error procesando mensaje:', error, 'data:', event.data);
            }
        };
        
        this.dataChannel.onclose = () => {
            console.log('[WebRTC] DataChannel cerrado');
            this.metrics.connected = false;
            this.stopLatencyMeasurement();
        };
        
        this.dataChannel.onerror = (error) => {
            console.error('[WebRTC] DataChannel error:', error);
        };
        
        // Configurar buffering bajo
        if (this.dataChannel.bufferedAmountLowThreshold !== undefined) {
            this.dataChannel.bufferedAmountLowThreshold = 0;
        }
    }
    
    async handleAnswer(data) {
        try {
            const answer = {
                type: 'answer',
                sdp: data.sdp
            };
            
            await this.pc.setRemoteDescription(answer);
            console.log('[WebRTC] Respuesta configurada');
            
        } catch (error) {
            console.error('[WebRTC] Error configurando respuesta:', error);
            this.handleError(error);
        }
    }
    
    handleRemoteIceCandidate(data) {
        if (this.pc && data.candidate) {
            this.pc.addIceCandidate(data.candidate)
                .catch(error => {
                    console.error('[WebRTC] Error agregando ICE candidate:', error);
                });
        }
    }
    
    handleAudioTrack(stream) {
        console.log('[WebRTC] Audio stream recibido, tracks:', stream.getAudioTracks().length);
        
        // Detener contexto anterior si existe
        if (this.audioContext) {
            this.audioContext.close().catch(() => {});
        }
        
        // Crear nuevo AudioContext con configuración óptima
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
            latencyHint: 'interactive',
            sampleRate: 48000
        });
        
        // Conectar stream a salida de audio
        const source = this.audioContext.createMediaStreamSource(stream);
        
        // Crear gain node para control de volumen global
        const gainNode = this.audioContext.createGain();
        gainNode.gain.value = 1.0;
        
        // Conectar a destino
        source.connect(gainNode);
        gainNode.connect(this.audioContext.destination);
        
        // Guardar nodos para control posterior
        this.audioNodes = [source, gainNode];
        
        // Crear elemento audio para fallback y debugging
        if (!this.audioElement) {
            this.audioElement = document.createElement('audio');
            this.audioElement.style.display = 'none';
            document.body.appendChild(this.audioElement);
        }
        
        this.audioElement.srcObject = stream;
        this.audioElement.play().catch(error => {
            console.warn('[WebRTC] Error reproduciendo audio element:', error);
        });
        
        this.mediaStream = stream;
        this.metrics.connected = true;
        this.connected = true;
        this.metrics.lastPacketTime = Date.now();
        
        // Notificar conexión exitosa
        console.log('[WebRTC] Audio conectado, contexto:', this.audioContext.state, 
                   'latency:', this.audioContext.baseLatency);
        
        if (this.onAudioConnected) {
            this.onAudioConnected();
        }
    }
    
    handleDataMessage(message) {
        try {
            switch (message.type) {
                case 'config':
                    console.log('[WebRTC] Configuración recibida:', message);
                    Object.assign(this.config, message);
                    break;
                    
                case 'pong':
                    this.handlePong(message);
                    break;
                    
                case 'stats':
                    console.log('[WebRTC] Stats del servidor:', message);
                    break;
                    
                default:
                    console.log('[WebRTC] Mensaje recibido:', message);
            }
        } catch (error) {
            console.error('[WebRTC] Error procesando mensaje:', error, message);
        }
    }
    
    handlePong(message) {
        const now = performance.now();
        const latency = now - message.timestamp;
        
        // Agregar a buffer de mediciones
        this.latencyMeasurements.push(latency);
        if (this.latencyMeasurements.length > this.maxLatencySamples) {
            this.latencyMeasurements.shift();
        }
        
        // Calcular latencia promedio
        const avgLatency = this.latencyMeasurements.length > 0 ?
            this.latencyMeasurements.reduce((a, b) => a + b, 0) / this.latencyMeasurements.length : 0;
        
        this.metrics.connectionLatency = Math.round(avgLatency);
        
        // Clasificar calidad de conexión
        if (avgLatency < 10) {
            this.metrics.quality = 'excellent';
        } else if (avgLatency < 20) {
            this.metrics.quality = 'good';
        } else if (avgLatency < 35) {
            this.metrics.quality = 'fair';
        } else if (avgLatency < 50) {
            this.metrics.quality = 'poor';
        } else {
            this.metrics.quality = 'bad';
        }
        
        // Actualizar timestamp del último paquete
        this.metrics.lastPacketTime = Date.now();
    }
    
    startLatencyMeasurement() {
        // Limpiar intervalo anterior
        if (this.latencyInterval) {
            clearInterval(this.latencyInterval);
        }
        
        // Enviar ping periódico para medir latencia
        this.latencyInterval = setInterval(() => {
            if (this.dataChannel && this.dataChannel.readyState === 'open') {
                this.dataChannel.send(JSON.stringify({
                    type: 'ping',
                    timestamp: performance.now(),
                    clientId: this.clientId
                }));
            }
        }, 2000); // Cada 2 segundos
    }
    
    stopLatencyMeasurement() {
        if (this.latencyInterval) {
            clearInterval(this.latencyInterval);
            this.latencyInterval = null;
        }
    }
    
    startMetricsMonitoring() {
        // Limpiar intervalo anterior
        if (this.metricsInterval) {
            clearInterval(this.metricsInterval);
        }
        
        // Monitorear métricas WebRTC periódicamente
        this.metricsInterval = setInterval(async () => {
            if (!this.pc || this.pc.connectionState !== 'connected') return;
            
            try {
                const stats = await this.pc.getStats();
                this.updateMetricsFromStats(stats);
            } catch (error) {
                console.error('[WebRTC] Error obteniendo stats:', error);
            }
        }, 1000); // Cada segundo
    }
    
    updateMetricsFromStats(stats) {
        let audioLatency = 0;
        let packetLoss = 0;
        let jitter = 0;
        let bytesReceived = 0;
        let currentPacketGap = 0;
        
        stats.forEach(report => {
            // Latencia de audio (RTT)
            if (report.type === 'remote-inbound-rtp' && report.kind === 'audio') {
                audioLatency = (report.roundTripTime || 0) * 1000;
                jitter = (report.jitter || 0) * 1000;
            }
            
            // Pérdida de paquetes y bytes recibidos
            if (report.type === 'inbound-rtp' && report.kind === 'audio') {
                if (report.packetsLost !== undefined && report.packetsReceived !== undefined) {
                    const total = report.packetsLost + report.packetsReceived;
                    packetLoss = total > 0 ? (report.packetsLost / total) * 100 : 0;
                }
                
                if (report.bytesReceived) {
                    bytesReceived = report.bytesReceived;
                }
                
                // Calcular gap entre paquetes
                if (report.lastPacketReceivedTimestamp) {
                    const lastPacketTime = report.lastPacketReceivedTimestamp;
                    currentPacketGap = Date.now() - lastPacketTime;
                }
            }
        });
        
        // Actualizar métricas
        this.metrics.audioLatency = Math.round(audioLatency);
        this.metrics.packetLoss = Math.round(packetLoss * 100) / 100;
        this.metrics.jitter = Math.round(jitter);
        this.metrics.bytesReceived = bytesReceived;
        this.metrics.packetGap = currentPacketGap;
        
        // Actualizar calidad basada en múltiples factores
        this.updateOverallQuality();
    }
    
    updateOverallQuality() {
        const latency = this.metrics.audioLatency || this.metrics.connectionLatency;
        const packetLoss = this.metrics.packetLoss;
        const jitter = this.metrics.jitter;
        
        let qualityScore = 100;
        
        // Penalizar por latencia
        if (latency > 30) qualityScore -= 40;
        else if (latency > 20) qualityScore -= 20;
        else if (latency > 15) qualityScore -= 10;
        else if (latency > 10) qualityScore -= 5;
        
        // Penalizar por pérdida de paquetes
        if (packetLoss > 10) qualityScore -= 40;
        else if (packetLoss > 5) qualityScore -= 20;
        else if (packetLoss > 2) qualityScore -= 10;
        else if (packetLoss > 0.5) qualityScore -= 5;
        
        // Penalizar por jitter
        if (jitter > 30) qualityScore -= 20;
        else if (jitter > 20) qualityScore -= 10;
        else if (jitter > 10) qualityScore -= 5;
        
        // Determinar calidad final
        if (qualityScore >= 90) this.metrics.quality = 'excellent';
        else if (qualityScore >= 75) this.metrics.quality = 'good';
        else if (qualityScore >= 60) this.metrics.quality = 'fair';
        else if (qualityScore >= 40) this.metrics.quality = 'poor';
        else this.metrics.quality = 'bad';
    }
    
    startHealthChecks() {
        // Limpiar intervalo anterior
        if (this.healthCheckInterval) {
            clearInterval(this.healthCheckInterval);
        }
        
        // Verificar salud de la conexión
        this.healthCheckInterval = setInterval(() => {
            const now = Date.now();
            const timeSinceLastPacket = now - this.metrics.lastPacketTime;
            
            // Si no hay paquetes en 10 segundos, hay problema
            if (timeSinceLastPacket > 10000 && this.metrics.connected) {
                console.warn('[WebRTC] Sin paquetes por', timeSinceLastPacket, 'ms');
                this.metrics.quality = 'bad';
            }
            
            // Verificar si el audio está silenciado
            if (this.audioContext && this.audioContext.state === 'suspended') {
                console.log('[WebRTC] Audio context suspended, resuming...');
                this.audioContext.resume().catch(console.error);
            }
        }, 5000); // Cada 5 segundos
    }
    
    subscribe(channels, gains = {}) {
        if (this.dataChannel && this.dataChannel.readyState === 'open') {
            this.dataChannel.send(JSON.stringify({
                type: 'subscribe',
                channels: channels,
                gains: gains,
                clientId: this.clientId,
                timestamp: Date.now()
            }));
            
            console.log(`[WebRTC] Suscripción enviada para ${channels.length} canales`);
            
        } else if (this.socket && this.socket.connected) {
            // Fallback a WebSocket para señalización
            this.socket.emit('webrtc_subscribe', {
                channels: channels,
                gains: gains,
                clientId: this.clientId
            });
            
            console.log(`[WebRTC] Suscripción enviada via WebSocket (fallback)`);
        } else {
            console.error('[WebRTC] No hay conexión para enviar suscripción');
        }
    }
    
    updateGain(channel, gain) {
        if (this.dataChannel && this.dataChannel.readyState === 'open') {
            this.dataChannel.send(JSON.stringify({
                type: 'update_gain',
                channel: channel,
                gain: gain,
                clientId: this.clientId
            }));
        } else if (this.socket && this.socket.connected) {
            this.socket.emit('update_gain', {
                channel: channel,
                gain: gain
            });
        }
    }
    
    setVolume(volume) {
        if (this.audioNodes && this.audioNodes[1]) { // gainNode
            this.audioNodes[1].gain.value = volume;
        }
    }
    
    handleConnected() {
        console.log('[WebRTC] Conectado');
        this.connected = true;
        this.reconnecting = false;
        this.reconnectAttempts = 0;
        
        const connectionTime = Date.now() - this.connectionStartTime;
        console.log(`[WebRTC] Tiempo de conexión: ${connectionTime}ms`);
        
        // Notificar a la UI
        if (this.onConnected) {
            this.onConnected();
        }
    }
    
    handleDisconnected() {
        console.log('[WebRTC] Desconectado');
        this.connected = false;
        this.metrics.connected = false;
        
        this.stopLatencyMeasurement();
        this.stopHealthChecks();
        
        if (!this.reconnecting && this.reconnectAttempts < this.maxReconnectAttempts) {
            setTimeout(() => this.reconnect(), 1000);
        } else if (this.onDisconnected) {
            this.onDisconnected();
        }
    }
    
    stopHealthChecks() {
        if (this.healthCheckInterval) {
            clearInterval(this.healthCheckInterval);
            this.healthCheckInterval = null;
        }
    }
    
    async reconnect() {
        this.reconnecting = true;
        this.reconnectAttempts++;
        
        console.log(`[WebRTC] Reintento ${this.reconnectAttempts}/${this.maxReconnectAttempts}`);
        
        // Cerrar conexión anterior
        await this.close();
        
        // Esperar antes de reintentar
        await new Promise(resolve => 
            setTimeout(resolve, 1000 * Math.min(this.reconnectAttempts, 3))
        );
        
        // Intentar reconectar
        try {
            await this.connect();
        } catch (error) {
            console.error('[WebRTC] Error en reconexión:', error);
            this.reconnecting = false;
        }
    }
    
    handleError(error) {
        console.error('[WebRTC] Error:', error);
        
        // Notificar a la UI
        if (this.onError) {
            this.onError(error);
        }
    }
    
    async close() {
        console.log('[WebRTC] Cerrando conexión...');
        
        // Detener todas las mediciones
        this.stopLatencyMeasurement();
        this.stopHealthChecks();
        if (this.metricsInterval) {
            clearInterval(this.metricsInterval);
            this.metricsInterval = null;
        }
        
        // Cerrar DataChannel
        if (this.dataChannel) {
            this.dataChannel.close();
            this.dataChannel = null;
        }
        
        // Cerrar PeerConnection
        if (this.pc) {
            this.pc.close();
            this.pc = null;
        }
        
        // Cerrar AudioContext
        if (this.audioContext) {
            await this.audioContext.close().catch(() => {});
            this.audioContext = null;
        }
        
        // Detener elemento audio
        if (this.audioElement) {
            this.audioElement.pause();
            this.audioElement.srcObject = null;
        }
        
        // Limpiar nodos
        this.audioNodes = [];
        this.mediaStream = null;
        
        this.connected = false;
        this.metrics.connected = false;
        
        console.log('[WebRTC] Conexión cerrada');
    }
    
    // Métodos públicos
    getMetrics() {
        const now = Date.now();
        const timeSinceLastPacket = now - this.metrics.lastPacketTime;
        
        return {
            ...this.metrics,
            connected: this.connected && this.metrics.connected,
            protocol: 'webrtc',
            timeSinceLastPacket: timeSinceLastPacket,
            reconnecting: this.reconnecting,
            reconnectAttempts: this.reconnectAttempts
        };
    }
    
    isConnected() {
        return this.connected && this.metrics.connected && 
               this.pc && this.pc.connectionState === 'connected';
    }
    
    getLatency() {
        return this.metrics.audioLatency || this.metrics.connectionLatency;
    }
    
    getQuality() {
        return this.metrics.quality;
    }
    
    // Callbacks
    onAudioConnected() {}
    onConnected() {}
    onDisconnected() {}
    onError(error) {}
}

// Exportar para uso global
window.WebRTCClient = WebRTCClient;