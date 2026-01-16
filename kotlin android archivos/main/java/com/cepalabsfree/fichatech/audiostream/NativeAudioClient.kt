package com.cepalabsfree.fichatech.audiostream

import android.os.Process
import android.os.Handler
import android.os.Looper
import android.util.Log
import java.io.DataInputStream
import java.io.DataOutputStream
import java.net.InetSocketAddress
import java.net.Socket
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.UUID
import kotlinx.coroutines.*
import org.json.JSONObject
import android.content.Context
import android.content.SharedPreferences

/**
 * ✅ ULTRA-OPTIMIZADO con soporte Opus
 * - Decodificación Opus nativa (C++)
 * - Fallback Zlib si Opus no disponible
 * - Auto-detección de formato por flags
 */
class NativeAudioClient(private val context: Context) {

    companion object {
        private const val TAG = "NativeAudioClient"
        private const val CONNECT_TIMEOUT = 5000            // 5 segundos
        private const val READ_TIMEOUT = 5000             // ✅ 5 segundos
        private const val HEADER_SIZE = 16
        private const val MAGIC_NUMBER = 0xA1D10A7C.toInt()
        private const val PROTOCOL_VERSION = 2
        private const val MSG_TYPE_AUDIO = 0x01
        private const val MSG_TYPE_CONTROL = 0x02
        private const val MSG_TYPE_HEARTBEAT = 0x03  // ✅ NUEVO
        private const val FLAG_FLOAT32 = 0x01
        private const val FLAG_INT16 = 0x02
        private const val FLAG_COMPRESSED = 0x04  // Zlib
        private const val FLAG_OPUS = 0x08         // ✅ NUEVO: Opus
        private const val FLAG_RF_MODE = 0x80
        private const val MAX_CONTROL_PAYLOAD = 100_000
        private const val MAX_AUDIO_PAYLOAD = 500_000
        private const val TCP_QUICKACK = true
        private const val TCP_NODELAY = true
        private const val SOCKET_SNDBUF = 8192
        private const val SOCKET_RCVBUF = 4096

        private const val AUTO_RECONNECT = true
        private const val RECONNECT_DELAY_MS = 300L
        private const val MAX_RECONNECT_DELAY_MS = 10000L // ⬆️ Delay máximo aumentado
        private const val RECONNECT_BACKOFF = 1.3
        private const val MAX_RECONNECT_ATTEMPTS = 20  // ✅ Límite de intentos
        private const val TOTAL_RECONNECT_TIMEOUT_MS = 60000L  // ✅ 60s total

        private const val HEADER_BUFFER_POOL_SIZE = 4
        private const val PAYLOAD_BUFFER_POOL_SIZE = 8
    }

    private var socket: Socket? = null
    private var inputStream: DataInputStream? = null
    private var outputStream: DataOutputStream? = null

    @Volatile private var isConnected = false
    private var serverIp = ""
    private var serverPort = 5101

    @Volatile private var shouldStop = false
    private var consecutiveMagicErrors = 0
    private val maxConsecutiveMagicErrors = 3

    private val clientId: String by lazy { getOrCreateClientId(context) }
    private var persistentChannels = emptyList<Int>()
    private val subscriptionLock = Any()

    private var reconnectJob: Job? = null
    private var currentReconnectDelay = RECONNECT_DELAY_MS
    private var reconnectAttempts = 0
    private var reconnectStartTime = 0L

    @Volatile private var rfMode = true

    // ✅ NUEVO: Control de inicialización Opus
    private var opusInitialized = false

    // ✅ NUEVO: Variables para heartbeat
    private var lastHeartbeatTime = System.currentTimeMillis()
    private val HEARTBEAT_TIMEOUT_MS = 15000L  // ✅ 15s (más realista para RF)
    private var lastHeartbeatSent = 0L

    // ✅ NUEVO: Canales operacionales
    private var operationalChannels = emptySet<Int>()

    var onAudioData: ((FloatAudioData) -> Unit)? = null
    var onConnectionStatus: ((Boolean, String) -> Unit)? = null
    var onServerInfo: ((Map<String, Any>) -> Unit)? = null
    var onError: ((String) -> Unit)? = null
    var onChannelUpdate: ((channel: Int, gainDb: Float?, pan: Float?, active: Boolean?) -> Unit)? = null
    var onMasterGainUpdate: ((gainDb: Float) -> Unit)? = null
    var onMixStateUpdate: ((mixState: Map<String, Any>) -> Unit)? = null

    private val headerBufferPool = ArrayDeque<ByteArray>().apply {
        repeat(HEADER_BUFFER_POOL_SIZE) { add(ByteArray(HEADER_SIZE)) }
    }

    private val payloadBufferPool = ArrayDeque<ByteArray>()
    private val jsonBuilder = StringBuilder(1024)
    private val jsonLock = Any()
    private val uiHandler = Handler(Looper.getMainLooper())

    init {
        // ✅ Inicializar decoder Opus al crear el cliente
        initializeOpusDecoder()
    }

    private fun initializeOpusDecoder() {
        try {
            AudioDecompressor.initOpusDecoder(
                sampleRate = 48000,
                channels = 2
            )
            opusInitialized = true
            Log.d(TAG, "✅ Opus decoder inicializado")
        } catch (e: Exception) {
            Log.w(TAG, "⚠️ No se pudo inicializar Opus: ${e.message}")
            Log.w(TAG, "   Se usará fallback (Zlib o sin compresión)")
            opusInitialized = false
        }
    }

    private fun getOrCreateClientId(context: Context): String {
        val prefs: SharedPreferences = context.getSharedPreferences("audio_prefs", Context.MODE_PRIVATE)
        var id = prefs.getString("client_id", null)
        if (id == null) {
            id = UUID.randomUUID().toString()
            prefs.edit().putString("client_id", id).apply()
        }
        return id
    }

    suspend fun connect(ip: String, port: Int = 5101): Boolean {
        serverIp = ip.trim()
        serverPort = port
        shouldStop = false
        rfMode = true

        Log.d(TAG, "📡 Modo RF: Conectando a $ip:$port")
        return connectInternal()
    }

    private suspend fun connectInternal(): Boolean = withContext(Dispatchers.IO) {
        try {
            // ✅ PASO 1: Cerrar conexión anterior si existe
            closeResourcesSafely()
            
            // ✅ PASO 2: Crear socket con timeouts apropiados
            socket = Socket().apply {
                soTimeout = 2000  // ✅ 2s timeout para reads
                tcpNoDelay = true
                keepAlive = true
                sendBufferSize = SOCKET_SNDBUF
                receiveBufferSize = SOCKET_RCVBUF
            }
            
            // ✅ PASO 3: Conectar con timeout
            val connectResult = withTimeoutOrNull(CONNECT_TIMEOUT.toLong()) {
                socket?.connect(InetSocketAddress(serverIp, serverPort), CONNECT_TIMEOUT)
                true
            }
            
            if (connectResult != true) {
                Log.w(TAG, "⏰ Timeout conectando al servidor")
                closeResourcesSafely()
                return@withContext false
            }
            
            // ✅ PASO 4: Crear streams
            inputStream = DataInputStream(socket?.getInputStream()?.buffered(4096))
            outputStream = DataOutputStream(socket?.getOutputStream()?.buffered(4096))
            
            // ✅ PASO 5: Enviar handshake con timeout
            val handshakeResult = withTimeoutOrNull(3000L) {
                sendHandshake()
                true
            }
            
            if (handshakeResult != true) {
                Log.w(TAG, "⏰ Timeout en handshake")
                closeResourcesSafely()
                return@withContext false
            }
            
            // ✅ PASO 6: Actualizar estado
            isConnected = true
            consecutiveMagicErrors = 0
            currentReconnectDelay = RECONNECT_DELAY_MS
            lastHeartbeatTime = System.currentTimeMillis()
            
            // ✅ PASO 7: Iniciar reader thread
            startReaderThread()
            
            // ✅ PASO 8: Notificar UI
            withContext(Dispatchers.Main) {
                onConnectionStatus?.invoke(true, "ONLINE")
            }
            
            // ✅ PASO 9: Re-suscribir canales
            val channelsToResubscribe = synchronized(subscriptionLock) {
                persistentChannels.toList()
            }
            
            if (channelsToResubscribe.isNotEmpty()) {
                Log.d(TAG, "🔄 Auto-restaurando ${channelsToResubscribe.size} canales")
                subscribe(channelsToResubscribe)
            }
            
            Log.i(TAG, "✅ Conectado exitosamente a $serverIp:$serverPort")
            true
            
        } catch (e: Exception) {
            Log.e(TAG, "❌ Error en connectInternal: ${e.message}")
            closeResourcesSafely()
            false
        }
    }

    private val connectionLostLock = Any()
    private var isHandlingConnectionLost = false

    private fun handleConnectionLost(reason: String) {
        // ✅ Evitar llamadas concurrentes
        synchronized(connectionLostLock) {
            if (isHandlingConnectionLost) {
                Log.d(TAG, "⚠️ Ya manejando pérdida de conexión, ignorando")
                return
            }
            isHandlingConnectionLost = true
        }
        
        try {
            Log.w(TAG, "📡 Señal RF perdida: $reason")
            
            val wasConnected = isConnected
            isConnected = false
            
            // ✅ Cerrar recursos
            closeResourcesSafely()
            
            // ✅ Notificar UI
            if (wasConnected) {
                CoroutineScope(Dispatchers.Main).launch {
                    onConnectionStatus?.invoke(false, "BUSCANDO SEÑAL...")
                }
            }
            
            // ✅ Iniciar reconexión
            if (AUTO_RECONNECT && !shouldStop && rfMode) {
                startAutoReconnect()
            }
            
        } finally {
            synchronized(connectionLostLock) {
                isHandlingConnectionLost = false
            }
        }
    }

    private fun startAutoReconnect() {
        reconnectJob?.cancel()
        
        // ✅ Resetear contadores si es primer intento
        if (reconnectAttempts == 0) {
            reconnectStartTime = System.currentTimeMillis()
            currentReconnectDelay = RECONNECT_DELAY_MS
        }
        
        reconnectJob = CoroutineScope(Dispatchers.IO).launch {
            while (!shouldStop && !isConnected && rfMode) {
                reconnectAttempts++
                
                // ✅ CHECK 1: Límite de intentos
                if (reconnectAttempts > MAX_RECONNECT_ATTEMPTS) {
                    Log.e(TAG, "❌ Límite de intentos alcanzado ($MAX_RECONNECT_ATTEMPTS)")
                    handleReconnectFailure("Demasiados intentos")
                    break
                }
                
                // ✅ CHECK 2: Timeout total
                val elapsed = System.currentTimeMillis() - reconnectStartTime
                if (elapsed > TOTAL_RECONNECT_TIMEOUT_MS) {
                    Log.e(TAG, "❌ Timeout total de reconexión (${elapsed}ms)")
                    handleReconnectFailure("Timeout total")
                    break
                }
                
                Log.d(TAG, "🔄 Reconexión #$reconnectAttempts (delay=${currentReconnectDelay}ms)")
                
                // ✅ Esperar antes de intentar
                delay(currentReconnectDelay)
                
                // ✅ Intentar conexión
                try {
                    val success = connectInternal()
                    
                    if (success) {
                        Log.i(TAG, "✅ Reconexión exitosa después de $reconnectAttempts intentos")
                        reconnectAttempts = 0
                        return@launch
                    } else {
                        Log.w(TAG, "⚠️ Intento #$reconnectAttempts falló")
                    }
                } catch (e: Exception) {
                    Log.w(TAG, "⚠️ Excepción en intento #$reconnectAttempts: ${e.message}")
                }
                
                // ✅ Backoff exponencial con límite
                currentReconnectDelay = (currentReconnectDelay * RECONNECT_BACKOFF)
                    .toLong()
                    .coerceAtMost(MAX_RECONNECT_DELAY_MS)
            }
            
            Log.w(TAG, "🛑 Ciclo de reconexión terminado")
        }
    }
    
    private fun handleReconnectFailure(reason: String) {
        """✅ Manejar fallo total de reconexión"""
        reconnectAttempts = 0
        shouldStop = true
        
        CoroutineScope(Dispatchers.Main).launch {
            onConnectionStatus?.invoke(false, "OFFLINE - $reason")
            onError?.invoke("No se pudo reconectar: $reason")
        }
        
        // ✅ Opcionalmente, notificar al usuario para reconexión manual
        // showNotification("Conexión perdida", "Toca para reconectar")
    }

    fun disconnect(reason: String = "Desconexión manual") {
        Log.d(TAG, "🔌 Desconectando RF: $reason")

        shouldStop = true
        rfMode = false
        reconnectJob?.cancel()
        closeResourcesSafely()
        isConnected = false

        // ✅ Liberar decoder Opus
        AudioDecompressor.release()

        CoroutineScope(Dispatchers.Main).launch {
            onConnectionStatus?.invoke(false, "FICHATECH RETRO")
        }
    }

    private fun closeResourcesSafely() {
        """✅ Cierre garantizado de recursos"""
        try { 
            outputStream?.close() 
        } catch (e: Exception) { 
            Log.d(TAG, "Error cerrando outputStream: ${e.message}") 
        }
        
        try { 
            inputStream?.close() 
        } catch (e: Exception) { 
            Log.d(TAG, "Error cerrando inputStream: ${e.message}") 
        }
        
        try {
            socket?.let { s ->
                if (!s.isClosed) {
                    s.shutdownInput()
                    s.shutdownOutput()
                    s.close()
                }
            }
        } catch (e: Exception) {
            Log.d(TAG, "Error cerrando socket: ${e.message}")
        }
        
        outputStream = null
        inputStream = null
        socket = null
    }

    fun subscribe(channels: List<Int>) {
        synchronized(subscriptionLock) {
            persistentChannels = channels.toList()
        }

        if (isConnected) {
            CoroutineScope(Dispatchers.IO).launch {
                sendControlMessage(
                    "subscribe",
                    mapOf(
                        "client_id" to clientId,
                        "channels" to channels,
                        "timestamp" to System.currentTimeMillis(),
                        "rf_mode" to true,
                        "persistent" to true,
                        "audio_format" to "int16",
                        "opus_support" to opusInitialized  // ✅ NUEVO
                    )
                )
            }
        }
    }

    fun setMasterGain(gainDb: Float) {
        if (isConnected) {
            CoroutineScope(Dispatchers.IO).launch {
                sendControlMessage(
                    "set_master_gain",
                    mapOf(
                        "client_id" to clientId,
                        "gain_db" to gainDb,
                        "timestamp" to System.currentTimeMillis()
                    )
                )
            }
        }
    }

    private fun sendHandshake() {
        sendControlMessage(
            "handshake",
            mapOf(
                "client_id" to clientId,
                "client_type" to "android",
                "protocol_version" to PROTOCOL_VERSION,
                "timestamp" to System.currentTimeMillis(),
                "rf_mode" to true,
                "persistent" to true,
                "auto_reconnect" to true,
                "optimized" to true,
                "audio_format" to "int16",
                "opus_support" to opusInitialized,  // ✅ NUEVO
                "compression_formats" to listOf(
                    if (opusInitialized) "opus" else null,
                    "zlib",
                    "none"
                ).filterNotNull()  // ✅ NUEVO
            )
        )
    }

    private fun startHeartbeatSender() {
        CoroutineScope(Dispatchers.IO).launch {
            while (!shouldStop && isConnected) {
                delay(5000L)  // ✅ Enviar cada 5s
                
                if (System.currentTimeMillis() - lastHeartbeatSent > 5000L) {
                    sendHeartbeat()
                    lastHeartbeatSent = System.currentTimeMillis()
                }
            }
        }
    }

    private fun startReaderThread() {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_AUDIO)
            } catch (_: Exception) {}

            val headerBuffer = acquireHeaderBuffer()

            val heartbeatCheckRunnable = object : Runnable {
                override fun run() {
                    if (isConnected) {
                        val timeSinceHeartbeat = System.currentTimeMillis() - lastHeartbeatTime
                        if (timeSinceHeartbeat > HEARTBEAT_TIMEOUT_MS) {
                            Log.w(TAG, "❌ Heartbeat timeout: ${timeSinceHeartbeat}ms sin respuesta")
                            handleConnectionLost("Heartbeat timeout")
                        }
                    }
                    if (!shouldStop) {
                        uiHandler.postDelayed(this, 5000)  // Check cada 5s
                    }
                }
            }
            
            // ✅ Iniciar envío periódico de heartbeat
            startHeartbeatSender()
            
            uiHandler.post(heartbeatCheckRunnable)

            while (!shouldStop) {
                try {
                    if (!isConnected) {
                        delay(1000)
                        continue
                    }

                    val input = inputStream ?: break

                    input.readFully(headerBuffer)
                    val header = decodeHeader(headerBuffer)

                    // ✅ Actualizar timestamp
                    lastHeartbeatTime = System.currentTimeMillis()

                    if (header.magic != MAGIC_NUMBER) {
                        consecutiveMagicErrors++
                        if (consecutiveMagicErrors >= maxConsecutiveMagicErrors) {
                            handleConnectionLost("Protocolo inválido")
                            break
                        }
                        continue
                    }

                    consecutiveMagicErrors = 0

                    val maxPayload = if (header.msgType == MSG_TYPE_CONTROL) {
                        MAX_CONTROL_PAYLOAD
                    } else {
                        MAX_AUDIO_PAYLOAD
                    }

                    if (header.payloadLength < 0 || header.payloadLength > maxPayload) {
                        continue
                    }

                    val payload = acquirePayloadBuffer(header.payloadLength)

                    if (header.payloadLength > 0) {
                        input.readFully(payload, 0, header.payloadLength)
                    }

                    when (header.msgType) {
                        MSG_TYPE_AUDIO -> {
                            val audioData = decodeAudioPayload(
                                payload,
                                header.payloadLength,
                                header.flags
                            )

                            if (audioData != null) {
                                withContext(Dispatchers.Main) {
                                    try {
                                        onAudioData?.invoke(audioData)
                                    } catch (e: Exception) {
                                        Log.e(TAG, "Error callback audio: ${e.message}")
                                    }
                                }
                            }
                        }
                        MSG_TYPE_CONTROL -> {
                            handleControlMessage(payload, header.payloadLength)
                        }
                    }

                    releasePayloadBuffer(payload)

                } catch (e: java.io.EOFException) {
                    handleConnectionLost("Servidor desconectado")
                    break
                } catch (e: java.net.SocketTimeoutException) {
                    continue
                } catch (e: Exception) {
                    if (!shouldStop) {
                        handleConnectionLost("Error: ${e.message}")
                    }
                    break
                }
            }

            releaseHeaderBuffer(headerBuffer)
        }
    }

    private fun handleControlMessage(payload: ByteArray, length: Int) {
        try {
            val message = String(payload, 0, length, Charsets.UTF_8)
            val json = JSONObject(message)
            val msgType = json.optString("type", "")

            when (msgType) {
                "handshake_response" -> {
                    val serverInfo = mapOf(
                        "server_version" to json.optString("server_version", "unknown"),
                        "protocol_version" to json.optInt("protocol_version", 0),
                        "sample_rate" to json.optInt("sample_rate", 48000),
                        "max_channels" to json.optInt("max_channels", 8),
                        "rf_mode" to json.optBoolean("rf_mode", false),
                        "latency_ms" to json.optDouble("latency_ms", 0.0),
                        "compression_mode" to json.optString("compression_mode", "none")  // ✅ NUEVO
                    )

                    CoroutineScope(Dispatchers.Main).launch { onServerInfo?.invoke(serverInfo) }
                    
                    // ✅ NUEVO: Enviar ACK
                    sendControlMessage("handshake_ack", mapOf(
                        "client_id" to clientId,
                        "timestamp" to System.currentTimeMillis()
                    ))
                }
                "subscription_confirmed" -> {
                    val compressionMode = json.optString("compression_mode", "none")
                    Log.d(TAG, "✅ Suscripción confirmada RF (compresión: $compressionMode)")
                }
                "channel_update" -> {
                    val channel = json.optInt("channel", -1)
                    if (channel >= 0) {
                        val gainDb = if (json.has("gainDb")) json.getDouble("gainDb").toFloat() else null
                        val pan = if (json.has("pan")) json.getDouble("pan").toFloat() else null
                        val active = if (json.has("active")) json.getBoolean("active") else null

                        CoroutineScope(Dispatchers.Main).launch {
                            onChannelUpdate?.invoke(channel, gainDb, pan, active)
                        }
                    }
                }
                "master_gain_update" -> {
                    val gainDb = json.optDouble("gainDb", 0.0).toFloat()
                    CoroutineScope(Dispatchers.Main).launch { onMasterGainUpdate?.invoke(gainDb) }
                }
                "mix_state" -> {
                    val mixState = mutableMapOf<String, Any>()

                    val channelsArray = json.optJSONArray("channels")
                    val channels = mutableListOf<Int>()
                    if (channelsArray != null) {
                        for (i in 0 until channelsArray.length()) {
                            channels.add(channelsArray.getInt(i))
                        }
                    }
                    mixState["channels"] = channels

                    val gainsObj = json.optJSONObject("gains")
                    val gains = mutableMapOf<Int, Float>()
                    if (gainsObj != null) {
                        for (key in gainsObj.keys()) {
                            val ch = key.toIntOrNull()
                            if (ch != null) {
                                gains[ch] = gainsObj.getDouble(key).toFloat()
                            }
                        }
                    }
                    mixState["gains"] = gains

                    val pansObj = json.optJSONObject("pans")
                    val pans = mutableMapOf<Int, Float>()
                    if (pansObj != null) {
                        for (key in pansObj.keys()) {
                            val ch = key.toIntOrNull()
                            if (ch != null) {
                                pans[ch] = pansObj.getDouble(key).toFloat()
                            }
                        }
                    }
                    mixState["pans"] = pans

                    if (json.has("master_gain")) {
                        mixState["master_gain"] = json.getDouble("master_gain").toFloat()
                    }

                    CoroutineScope(Dispatchers.Main).launch { onMixStateUpdate?.invoke(mixState) }
                }
                // ✅ NUEVO: Sincronización completa de estado
                "full_state_sync" -> {
                    val gains = mutableMapOf<Int, Float>()
                    synchronized(subscriptionLock) {
                        // Extraer canales operacionales
                        val opChannelsArray = json.optJSONArray("operational_channels")
                        operationalChannels = if (opChannelsArray != null) {
                            (0 until opChannelsArray.length()).map { 
                                opChannelsArray.getInt(it) 
                            }.toSet()
                        } else {
                            emptySet()
                        }
                        // Extraer canales solicitados
                        val requestedChannels = mutableListOf<Int>()
                        val channelsArray = json.optJSONArray("channels")
                        if (channelsArray != null) {
                            for (i in 0 until channelsArray.length()) {
                                requestedChannels.add(channelsArray.getInt(i))
                            }
                        }
                        // ✅ VALIDAR: Solo aceptar canales operacionales
                        val validChannels = requestedChannels.filter { ch -> 
                            ch in operationalChannels
                        }
                        if (validChannels.size < requestedChannels.size) {
                            val invalid = requestedChannels - validChannels.toSet()
                            Log.w(TAG, "⚠️  Canales inválidos ignorados: $invalid")
                        }
                        persistentChannels = validChannels
                        // Extraer gains, pans, mutes
                        val gainsObj = json.optJSONObject("gains")
                        if (gainsObj != null) {
                            for (key in gainsObj.keys()) {
                                gains[key.toInt()] = gainsObj.getDouble(key).toFloat()
                            }
                        }
                        // Similar para pans y mutes...
                    }
                    // Notificar UI
                    CoroutineScope(Dispatchers.Main).launch {
                        onMixStateUpdate?.invoke(mapOf(
                            "channels" to persistentChannels,
                            "gains" to gains,
                            "operational_channels" to operationalChannels.toList()
                        ))
                    }
                    Log.d(TAG, "✅ Estado completo sincronizado: ${persistentChannels.size} canales")
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error procesando mensaje control: ${e.message}")
        }
    }

    private fun decodeHeader(bytes: ByteArray): PacketHeader {
        try {
            val buffer = ByteBuffer.wrap(bytes).order(ByteOrder.BIG_ENDIAN)
            val magic = buffer.int
            val version = buffer.short.toInt() and 0xFFFF
            val typeAndFlags = buffer.short.toInt() and 0xFFFF
            val msgType = (typeAndFlags shr 8) and 0xFF
            val flags = typeAndFlags and 0xFF
            val timestamp = buffer.int
            val payloadLength = buffer.int

            return PacketHeader(magic, version, msgType, flags, timestamp, 0, payloadLength)
        } catch (e: Exception) {
            return PacketHeader(0, 0, 0, 0, 0, 0, 0)
        }
    }

    private fun decodeAudioPayload(
        payload: ByteArray,
        length: Int,
        flags: Int
    ): FloatAudioData? {
        if (length < 12) return null

        try {
            val buffer = ByteBuffer.wrap(payload, 0, length).order(ByteOrder.BIG_ENDIAN)

            val samplePosition = buffer.long
            val channelMask = buffer.int

            val activeChannels = listOf(0, 1)
            val remainingBytes = length - 12

            // ✅ Detectar formato de audio por flags
            val interleavedAudioData = when {
                // ✅ OPUS COMPRIMIDO (máxima prioridad)
                (flags and FLAG_OPUS) != 0 -> {
                    Log.d(TAG, "📦 Decodificando Opus: $remainingBytes bytes")
                    AudioDecompressor.processAudioPacket(
                        payload.copyOfRange(12, length),
                        "opus"
                    )
                }
                // ✅ ZLIB COMPRIMIDO (fallback)
                (flags and FLAG_COMPRESSED) != 0 -> {
                    Log.d(TAG, "📦 Decodificando Zlib: $remainingBytes bytes")
                    AudioDecompressor.processAudioPacket(
                        payload.copyOfRange(12, length),
                        "zlib"
                    )
                }
                // ✅ INT16 SIN COMPRESIÓN
                (flags and FLAG_INT16) != 0 -> {
                    AudioDecompressor.processAudioPacket(
                        payload.copyOfRange(12, length),
                        "none"
                    )
                }
                // ✅ FLOAT32 (legacy)
                else -> {
                    // Decodificar float32 directamente
                    val floatBuffer = ByteBuffer.wrap(payload, 12, remainingBytes)
                        .order(ByteOrder.BIG_ENDIAN)
                        .asFloatBuffer()
                    FloatArray(floatBuffer.remaining()).also { floatBuffer.get(it) }
                }
            }

            if (interleavedAudioData.isEmpty()) {
                return null
            }

            val samplesPerChannel = interleavedAudioData.size / 2
            if (samplesPerChannel == 0) return null

            val channelsAudioData = Array(2) { FloatArray(samplesPerChannel) }

            for (s in 0 until samplesPerChannel) {
                val baseIdx = s * 2
                channelsAudioData[0][s] = interleavedAudioData[baseIdx]
                channelsAudioData[1][s] = interleavedAudioData[baseIdx + 1]
            }

            return FloatAudioData(samplePosition, activeChannels, channelsAudioData, samplesPerChannel)
        } catch (e: Exception) {
            Log.e(TAG, "Error decoding audio payload: ${e.message}")
            return null
        }
    }

    private fun sendControlMessage(type: String, data: Map<String, Any>) {
        if (!isConnected || shouldStop) return

        CoroutineScope(Dispatchers.IO).launch {
            try {
                val message = buildJsonMessageOptimized(type, data)
                val messageBytes = message.toByteArray(Charsets.UTF_8)

                val header = ByteBuffer.allocate(HEADER_SIZE).order(ByteOrder.BIG_ENDIAN)
                header.putInt(MAGIC_NUMBER)
                header.putShort(PROTOCOL_VERSION.toShort())
                val flags = FLAG_RF_MODE
                header.putShort(((MSG_TYPE_CONTROL shl 8) or flags).toShort())
                header.putInt((System.currentTimeMillis() % Int.MAX_VALUE).toInt())
                header.putInt(messageBytes.size)

                // ✅ NUEVO: Timeout breve para writes (no-blocking)
                val originalTimeout = socket?.soTimeout ?: 0
                socket?.soTimeout = 500  // 500ms timeout para writes
                
                try {
                    outputStream?.write(header.array())
                    outputStream?.write(messageBytes)
                    outputStream?.flush()
                    
                    Log.d(TAG, "📤 Mensaje $type enviado (${messageBytes.size} bytes)")
                    
                } finally {
                    // Restaurar timeout para reads
                    if (socket != null) {
                        socket!!.soTimeout = originalTimeout
                    }
                }

            } catch (e: java.net.SocketTimeoutException) {
                Log.w(TAG, "⏱️  Timeout enviando mensaje $type - buffer servidor lleno")
                handleConnectionLost("Timeout enviando control")
                
            } catch (e: Exception) {
                Log.e(TAG, "❌ Error enviando $type: ${e.message}")
                handleConnectionLost("Error enviando: ${e.message}")
            }
        }
    }

    // Nuevo método para enviar heartbeat
    private fun sendHeartbeat(samplePosition: Long = 0L) {
        if (isConnected) {
            CoroutineScope(Dispatchers.IO).launch {
                sendControlMessage(
                    "heartbeat",
                    mapOf(
                        "client_id" to clientId,
                        "sample_position" to samplePosition,
                        "timestamp" to System.currentTimeMillis()
                    )
                )
            }
        }
    }

    private fun buildJsonMessageOptimized(type: String, data: Map<String, Any>): String {
        synchronized(jsonLock) {
            jsonBuilder.setLength(0)
            jsonBuilder.append("{\"type\":\"").append(type).append('"')

            data.forEach { (key, value) ->
                jsonBuilder.append(",\"").append(key).append("\":")

                when (value) {
                    is String -> jsonBuilder.append('"').append(value).append('"')
                    is Number -> jsonBuilder.append(value)
                    is Boolean -> jsonBuilder.append(value)
                    is List<*> -> {
                        jsonBuilder.append('[')
                        value.forEachIndexed { idx, item ->
                            if (idx > 0) jsonBuilder.append(',')
                            when (item) {
                                is Number -> jsonBuilder.append(item)
                                is String -> jsonBuilder.append('"').append(item).append('"')
                                else -> jsonBuilder.append("null")
                            }
                        }
                        jsonBuilder.append(']')
                    }
                    else -> jsonBuilder.append('"').append(value).append('"')
                }
            }

            jsonBuilder.append('}')
            return jsonBuilder.toString()
        }
    }

    private fun acquireHeaderBuffer(): ByteArray {
        return synchronized(headerBufferPool) {
            headerBufferPool.removeFirstOrNull() ?: ByteArray(HEADER_SIZE)
        }
    }

    private fun releaseHeaderBuffer(buffer: ByteArray) {
        synchronized(headerBufferPool) {
            if (headerBufferPool.size < HEADER_BUFFER_POOL_SIZE) {
                headerBufferPool.addLast(buffer)
            }
        }
    }

    private fun acquirePayloadBuffer(size: Int): ByteArray {
        synchronized(payloadBufferPool) {
            val buffer = payloadBufferPool.find { it.size >= size }
            if (buffer != null) {
                payloadBufferPool.remove(buffer)
                return buffer
            }
            return ByteArray(size)
        }
    }

    private fun releasePayloadBuffer(buffer: ByteArray) {
        synchronized(payloadBufferPool) {
            if (payloadBufferPool.size < PAYLOAD_BUFFER_POOL_SIZE) {
                payloadBufferPool.addLast(buffer)
            }
        }
    }

    fun isConnected() = isConnected && !shouldStop

    fun getRFStatus(): String {
        return when {
            isConnected -> "ONLINE"
            reconnectJob?.isActive == true -> "BUSCANDO..."
            else -> "OFFLINE"
        }
    }

    data class PacketHeader(
        val magic: Int,
        val version: Int,
        val msgType: Int,
        val flags: Int,
        val timestamp: Int,
        val sequence: Int,
        val payloadLength: Int
    )

    data class FloatAudioData(
        val samplePosition: Long,
        val activeChannels: List<Int>,
        val audioData: Array<FloatArray>,
        val samplesPerChannel: Int
    ) {
        override fun equals(other: Any?): Boolean {
            if (this === other) return true
            if (javaClass != other?.javaClass) return false
            other as FloatAudioData
            if (samplePosition != other.samplePosition) return false
            if (activeChannels != other.activeChannels) return false
            if (!audioData.contentDeepEquals(other.audioData)) return false
            return samplesPerChannel == other.samplesPerChannel
        }

        override fun hashCode(): Int {
            var result = samplePosition.hashCode()
            result = 31 * result + activeChannels.hashCode()
            result = 31 * result + audioData.contentDeepHashCode()
            result = 31 * result + samplesPerChannel
            return result
        }
    }
}

