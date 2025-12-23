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

        

        // ConfiguraciÃ³n

        this.config = {

            audioCodec: 'opus',

            bitrate: 96000,

            frameDuration: 20, // ms

            useDtx: false,

            useFec: true,

            forceOpus: true,

            targetLatency: 15, // ms objetivo

            maxLatency: 30,    // ms mÃ¡ximo aceptable

            bufferSize: 2      // buffers en jitter buffer

        };

        

        // MÃ©tricas

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

        

        // Buffer para mÃ©tricas

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

        // ConfiguraciÃ³n optimizada para audio de baja latencia

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

        

        // Iniciar monitorizaciÃ³n

        this.startMetricsMonitoring();

        this.startHealthChecks();

        

        return true;

    }

    

    // ============================================
// REEMPLAZA LA FUNCIÓN optimizeSDP() COMPLETA
// ============================================

optimizeSDP(sdp) {
    console.log('[WebRTC] Original SDP:', sdp);
    
    let lines = sdp.split('\n');
    let optimized = [];
    let skipNext = false;
    let opusPayloadType = null;
    
    // Paso 1: Encontrar el payload type de Opus
    for (let line of lines) {
        if (line.includes('opus/48000')) {
            const match = line.match(/a=rtpmap:(\d+)\s+opus/);
            if (match) {
                opusPayloadType = match[1];
                console.log('[WebRTC] Opus payload type:', opusPayloadType);
            }
        }
    }
    
    // Paso 2: Procesar líneas
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();
        
        if (!line) {
            optimized.push('');
            continue;
        }
        
        // Saltar si marcado
        if (skipNext) {
            skipNext = false;
            console.log('[WebRTC] Skipping duplicate:', line);
            continue;
        }
        
        // ✅ MANTENER línea de audio original
        if (line.startsWith('m=audio')) {
            console.log('[WebRTC] Keeping audio line:', line);
            optimized.push(line);
            continue;
        }
        
        // ✅ RECHAZAR video (puerto 0)
        if (line.startsWith('m=video')) {
            console.log('[WebRTC] Rejecting video');
            optimized.push('m=video 0 UDP/TLS/RTP/SAVPF 0');
            // Saltar todas las líneas de atributos de video
            while (i + 1 < lines.length && lines[i + 1].trim().startsWith('a=')) {
                i++;
            }
            continue;
        }
        
        // ✅ OPTIMIZAR parámetros de Opus
        if (opusPayloadType && line.startsWith(`a=fmtp:${opusPayloadType}`)) {
            console.log('[WebRTC] Replacing Opus fmtp:', line);
            // Reemplazar con parámetros optimizados (SIN espacio después del ;)
            optimized.push(`a=fmtp:${opusPayloadType} minptime=10;useinbandfec=1;maxaveragebitrate=96000`);
            continue;
        }
        
        // ✅ Agregar maxptime después de rtpmap de Opus
        if (opusPayloadType && line.startsWith(`a=rtpmap:${opusPayloadType}`)) {
            optimized.push(line);
            optimized.push('a=maxptime:60');
            continue;
        }
        
        // ✅ ELIMINAR líneas duplicadas de fmtp si existen
        if (line.includes('a=fmtp:111 minptime=10;') && optimized.some(l => l.includes('a=fmtp:111'))) {
            console.log('[WebRTC] Skipping duplicate fmtp');
            continue;
        }
        
        // Mantener todas las demás líneas
        optimized.push(line);
    }
    
    const result = optimized.join('\n');
    console.log('[WebRTC] Optimized SDP:', result);
    return result;
}
    

    // REEMPLAZA LA FUNCIÃ“N setupEventHandlers():

setupEventHandlers() {

    // ICE Candidate

    this.pc.onicecandidate = (event) => {

        if (event.candidate) {

            console.log('[WebRTC] ICE candidate:', event.candidate);

            this.socket.emit('webrtc_ice_candidate', {

                candidate: event.candidate,

                clientId: this.clientId

            });

        } else {

            console.log('[WebRTC] ICE gathering complete');

        }

    };

    

    // ICE Connection State

    this.pc.oniceconnectionstatechange = () => {

        const state = this.pc.iceConnectionState;

        console.log('[WebRTC] ICE Connection State:', state);

        this.metrics.iceState = state;

        

        if (state === 'connected' || state === 'completed') {

            this.handleConnected();

        } else if (state === 'failed') {

            console.error('[WebRTC] ICE failed, attempting restart...');

            // Intentar restart ICE

            if (this.pc) {

                this.pc.restartIce();

            }

        }

    };

    

    // Connection State

    this.pc.onconnectionstatechange = () => {

        const state = this.pc.connectionState;

        console.log('[WebRTC] Connection State:', state);

        this.metrics.connectionState = state;

        

        if (state === 'connected') {

            console.log('[WebRTC] âœ… CONNECTED!');

            this.metrics.connected = true;

            this.connected = true;

        } else if (state === 'failed' || state === 'disconnected') {

            console.error('[WebRTC] âŒ Connection failed:', state);

            this.metrics.connected = false;

            this.connected = false;

        }

    };

    

    // Â¡ESTO ES LO MÃS IMPORTANTE! - Track recibido

    this.pc.ontrack = (event) => {

        console.log('[WebRTC] Track received!', {

            kind: event.track.kind,

            id: event.track.id,

            readyState: event.track.readyState,

            streams: event.streams.length

        });

        

        if (event.track.kind === 'audio') {

            console.log('[WebRTC] âœ… Audio track received!');

            this.handleAudioTrack(event.streams[0]);

        }

        

        if (event.streams && event.streams[0]) {

            console.log('[WebRTC] Stream available:', event.streams[0].id);

        }

    };

    

    // DataChannel (opcional, por si acaso)

    this.pc.ondatachannel = (event) => {

        console.log('[WebRTC] DataChannel received:', event.channel.label);

        this.dataChannel = event.channel;

        this.setupDataChannel();

    };

    

    // Manejo de errores

    this.pc.onicecandidateerror = (event) => {

        console.error('[WebRTC] ICE candidate error:', event.errorCode, event.errorText);

    };

}

    setupDataChannel() {

        this.dataChannel.onopen = () => {

            console.log('[WebRTC] DataChannel abierto, estado:', this.dataChannel.readyState);

            

            // Configurar DataChannel para baja latencia

            this.dataChannel.binaryType = 'arraybuffer';

            

            // Enviar configuraciÃ³n inicial

            setTimeout(() => {

                if (this.dataChannel.readyState === 'open') {

                    this.dataChannel.send(JSON.stringify({

                        type: 'get_config',

                        clientId: this.clientId,

                        timestamp: Date.now()

                    }));

                }

            }, 100);

            

            // Iniciar mediciÃ³n de latencia

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

    console.log('[WebRTC] Handling audio track, streams:', stream.getAudioTracks().length);

    

    // Detectar si el contexto de audio estÃ¡ bloqueado

    if (this.audioContext && this.audioContext.state === 'suspended') {

        console.log('[WebRTC] Audio context suspended, resuming...');

        this.audioContext.resume().then(() => {

            console.log('[WebRTC] Audio context resumed');

        }).catch(console.error);

    }

    

    // Crear contexto si no existe

    if (!this.audioContext) {

        console.log('[WebRTC] Creating new AudioContext');

        this.audioContext = new (window.AudioContext || window.webkitAudioContext)({

            latencyHint: 'interactive'

        });

    }

    

    // Verificar que el stream tenga tracks de audio

    const audioTracks = stream.getAudioTracks();

    if (audioTracks.length === 0) {

        console.error('[WebRTC] No audio tracks in stream!');

        return;

    }

    

    console.log('[WebRTC] Audio track details:', {

        enabled: audioTracks[0].enabled,

        muted: audioTracks[0].muted,

        readyState: audioTracks[0].readyState,

        kind: audioTracks[0].kind

    });

    

    // Crear fuente de audio desde el stream

    try {

        const source = this.audioContext.createMediaStreamSource(stream);

        const gainNode = this.audioContext.createGain();

        gainNode.gain.value = 1.0;

        

        source.connect(gainNode);

        gainNode.connect(this.audioContext.destination);

        

        this.audioNodes = [source, gainNode];

        this.mediaStream = stream;

        

        console.log('[WebRTC] âœ… Audio successfully connected to speakers');

        

        // Crear elemento audio para debugging

        if (!this.audioElement) {

            this.audioElement = document.createElement('audio');

            this.audioElement.autoplay = true;

            this.audioElement.controls = false;

            this.audioElement.style.display = 'none';

            document.body.appendChild(this.audioElement);

        }

        

        this.audioElement.srcObject = stream;

        

        // Intentar reproducir

        this.audioElement.play().then(() => {

            console.log('[WebRTC] Audio element playing');

        }).catch(error => {

            console.warn('[WebRTC] Audio element play error:', error);

            // Intentar con user gesture

            document.addEventListener('click', () => {

                this.audioElement.play().catch(console.error);

            }, { once: true });

        });

        

        // Notificar conexiÃ³n exitosa

        if (this.onAudioConnected) {

            setTimeout(() => this.onAudioConnected(), 100);

        }

        

    } catch (error) {

        console.error('[WebRTC] Error connecting audio:', error);

    }

}

    

    handleDataMessage(message) {

        try {

            switch (message.type) {

                case 'config':

                    console.log('[WebRTC] ConfiguraciÃ³n recibida:', message);

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

        

        // Clasificar calidad de conexiÃ³n

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

        

        // Actualizar timestamp del Ãºltimo paquete

        this.metrics.lastPacketTime = Date.now();

    }

    

    startLatencyMeasurement() {

        // Limpiar intervalo anterior

        if (this.latencyInterval) {

            clearInterval(this.latencyInterval);

        }

        

        // Enviar ping periÃ³dico para medir latencia

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

        

        // Monitorear mÃ©tricas WebRTC periÃ³dicamente

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

            

            // PÃ©rdida de paquetes y bytes recibidos

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

        

        // Actualizar mÃ©tricas

        this.metrics.audioLatency = Math.round(audioLatency);

        this.metrics.packetLoss = Math.round(packetLoss * 100) / 100;

        this.metrics.jitter = Math.round(jitter);

        this.metrics.bytesReceived = bytesReceived;

        this.metrics.packetGap = currentPacketGap;

        

        // Actualizar calidad basada en mÃºltiples factores

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

        

        // Penalizar por pÃ©rdida de paquetes

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

        

        // Verificar salud de la conexiÃ³n

        this.healthCheckInterval = setInterval(() => {

            const now = Date.now();

            const timeSinceLastPacket = now - this.metrics.lastPacketTime;

            

            // Si no hay paquetes en 10 segundos, hay problema

            if (timeSinceLastPacket > 10000 && this.metrics.connected) {

                console.warn('[WebRTC] Sin paquetes por', timeSinceLastPacket, 'ms');

                this.metrics.quality = 'bad';

            }

            

            // Verificar si el audio estÃ¡ silenciado

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

            

            console.log(`[WebRTC] SuscripciÃ³n enviada para ${channels.length} canales`);

            

        } else if (this.socket && this.socket.connected) {

            // Fallback a WebSocket para seÃ±alizaciÃ³n

            this.socket.emit('webrtc_subscribe', {

                channels: channels,

                gains: gains,

                clientId: this.clientId

            });

            

            console.log(`[WebRTC] SuscripciÃ³n enviada via WebSocket (fallback)`);

        } else {

            console.error('[WebRTC] No hay conexiÃ³n para enviar suscripciÃ³n');

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

        console.log(`[WebRTC] Tiempo de conexiÃ³n: ${connectionTime}ms`);

        

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

        

        // Cerrar conexiÃ³n anterior

        await this.close();

        

        // Esperar antes de reintentar

        await new Promise(resolve => 

            setTimeout(resolve, 1000 * Math.min(this.reconnectAttempts, 3))

        );

        

        // Intentar reconectar

        try {

            await this.connect();

        } catch (error) {

            console.error('[WebRTC] Error en reconexiÃ³n:', error);

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

        console.log('[WebRTC] Cerrando conexiÃ³n...');

        

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

        

        console.log('[WebRTC] ConexiÃ³n cerrada');

    }

    

    // MÃ©todos pÃºblicos

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