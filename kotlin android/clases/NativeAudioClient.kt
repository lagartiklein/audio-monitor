package com.cepalabsfree.fichatech.audiostream

import android.os.Process
import android.util.Log
import java.io.DataInputStream
import java.io.DataOutputStream
import java.net.InetSocketAddress
import java.net.Socket
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong
import kotlinx.coroutines.*
import org.json.JSONObject
import org.json.JSONArray

/**
 * ✅ NativeAudioClient v3.0 - API 36 Compatible
 *
 * CARACTERÍSTICAS:
 * - Singleton thread-safe con deviceUUID inmutable
 * - Auto-reconexión con backoff exponencial
 * - Heartbeat keep-alive para detección rápida de desconexiones
 * - Sincronización bidireccional de controles de mixer
 * - Restauración completa de estado en reconexión
 * - Compatible con servidor Python y Web UI
 */
class NativeAudioClient private constructor(val deviceUUID: String) {

    companion object {
        private const val TAG = "NativeAudioClient"

        // Timeouts optimizados para API 36
        private const val CONNECT_TIMEOUT = 5000
        private const val READ_TIMEOUT = 5000  // ⚠️ REDUCIDO: 8s → 5s

        // Protocolo binario
        private const val HEADER_SIZE = 16
        private const val MAGIC_NUMBER = 0xA1D10A7C.toInt()
        private const val PROTOCOL_VERSION = 2
        private const val MSG_TYPE_AUDIO = 0x01
        private const val MSG_TYPE_CONTROL = 0x02
        private const val FLAG_FLOAT32 = 0x01
        private const val FLAG_INT16 = 0x02
        private const val FLAG_RF_MODE = 0x80
        private const val MAX_CONTROL_PAYLOAD = 500_000
        private const val MAX_AUDIO_PAYLOAD = 2_000_000

        // Socket optimizado para baja latencia
        private const val SOCKET_SNDBUF = 65536
        private const val SOCKET_RCVBUF = 131072
        private const val TRAFFIC_CLASS_EF = 0xB8

        // Reconexión automática con backoff
        private const val AUTO_RECONNECT = true
        private const val RECONNECT_DELAY_MS = 1000L
        private const val MAX_RECONNECT_DELAY_MS = 8000L
        private const val RECONNECT_BACKOFF = 1.5

        // Heartbeat keep-alive
        private const val HEARTBEAT_INTERVAL_MS = 2000L  // ⚠️ REDUCIDO: 3s → 2s para respuesta más rápida
        private const val HEARTBEAT_TIMEOUT_MS = 6000L   // ⚠️ REDUCIDO: 9s → 6s

        // ✅ OPTIMIZACIÓN LATENCIA: Constante para división Int16->Float
        private const val INVERSE_32768 = 1f / 32768f

        // ✅ OPTIMIZACIÓN LATENCIA: Buffers pre-alocados para evitar GC
        private val shortBufferPool = ArrayDeque<ShortArray>()
        private val floatBufferPool = ArrayDeque<FloatArray>()
        private const val MAX_POOLED_BUFFERS = 4

        private fun acquireShortBuffer(size: Int): ShortArray {
            return synchronized(shortBufferPool) {
                shortBufferPool.removeFirstOrNull()?.takeIf { it.size >= size }
            } ?: ShortArray(size)
        }

        private fun releaseShortBuffer(buffer: ShortArray) {
            synchronized(shortBufferPool) {
                if (shortBufferPool.size < MAX_POOLED_BUFFERS) {
                    shortBufferPool.addLast(buffer)
                }
            }
        }

        private fun acquireFloatBuffer(size: Int): FloatArray {
            return synchronized(floatBufferPool) {
                floatBufferPool.removeFirstOrNull()?.takeIf { it.size >= size }
            } ?: FloatArray(size)
        }

        private fun releaseFloatBuffer(buffer: FloatArray) {
            synchronized(floatBufferPool) {
                if (floatBufferPool.size < MAX_POOLED_BUFFERS) {
                    floatBufferPool.addLast(buffer)
                }
            }
        }

        // Singleton thread-safe
        @Volatile private var instance: NativeAudioClient? = null
        private val instanceLock = Any()

        fun getInstance(deviceUUID: String): NativeAudioClient {
            instance?.let {
                if (it.deviceUUID == deviceUUID) return it
            }

            return synchronized(instanceLock) {
                instance?.let {
                    if (it.deviceUUID == deviceUUID) return@synchronized it
                    Log.w(TAG, "⚠️ Reemplazando cliente con nuevo deviceUUID")
                    it.forceClose()
                }
                NativeAudioClient(deviceUUID).also { instance = it }
            }
        }

        fun releaseInstance() {
            synchronized(instanceLock) {
                instance?.forceClose()
                instance = null
            }
        }
    }

    // Estado de conexión
    private var socket: Socket? = null
    private var inputStream: DataInputStream? = null
    private var outputStream: DataOutputStream? = null
    private val _isConnected = AtomicBoolean(false)
    private var serverIp = ""
    private var serverPort = 5101

    // Buffer pre-alocado para network I/O
    private val networkBuffer = ByteBuffer.allocateDirect(8192).apply {
        order(ByteOrder.nativeOrder())
    }

    // ✅ FIX: Mutex para sincronizar lectura del socket (DataInputStream NO es thread-safe)
    private val readLock = Any()

    private val _shouldStop = AtomicBoolean(false)
    private var consecutiveMagicErrors = 0
    private val maxConsecutiveMagicErrors = 5  // ⚠️ AUMENTADO: 3 → 5 errores antes de desconectar

    // Estado persistente para reconexión completa
    private val clientId = deviceUUID
    private var persistentChannels = emptyList<Int>()
    private var persistentGains = emptyMap<Int, Float>()
    private var persistentPans = emptyMap<Int, Float>()
    private var persistentMutes = emptyMap<Int, Boolean>()
    private val subscriptionLock = Any()

    private var reconnectJob: Job? = null
    private var heartbeatJob: Job? = null
    private var currentReconnectDelay = RECONNECT_DELAY_MS

    @Volatile private var rfMode = true
    private val lastHeartbeatResponse = AtomicLong(0L)

    // Callbacks para eventos
    var onAudioData: ((FloatAudioData) -> Unit)? = null
    var onConnectionStatus: ((Boolean, String) -> Unit)? = null
    var onServerInfo: ((Map<String, Any>) -> Unit)? = null
    var onMixState: ((MixState) -> Unit)? = null
    var onError: ((String) -> Unit)? = null
    var onControlSync: ((ControlUpdate) -> Unit)? = null

    /**
     * Conectar en modo RF con auto-reconexión y heartbeat
     */
    suspend fun connect(ip: String, port: Int = 5101): Boolean {
        serverIp = ip.trim()
        serverPort = port
        _shouldStop.set(false)
        rfMode = true

        Log.d(TAG, "📡 Conectando a $ip:$port (AUTO-RECONNECT + HEARTBEAT)")
        return connectInternal()
    }

    private suspend fun connectInternal(): Boolean = withContext(Dispatchers.IO) {
        try {
            Log.d(TAG, "🔌 Conectando RF a $serverIp:$serverPort...")

            socket = Socket().apply {
                soTimeout = READ_TIMEOUT
                tcpNoDelay = true
                keepAlive = true
                sendBufferSize = SOCKET_SNDBUF
                receiveBufferSize = SOCKET_RCVBUF

                try {
                    trafficClass = TRAFFIC_CLASS_EF
                } catch (e: Exception) {
                    Log.w(TAG, "⚠️ Traffic class no configurado: ${e.message}")
                }

                setSoLinger(false, 0)
                connect(InetSocketAddress(serverIp, serverPort), CONNECT_TIMEOUT)
            }

            inputStream = DataInputStream(socket?.getInputStream()?.buffered(SOCKET_RCVBUF))
            outputStream = DataOutputStream(socket?.getOutputStream()?.buffered(SOCKET_SNDBUF))

            _isConnected.set(true)
            consecutiveMagicErrors = 0
            currentReconnectDelay = RECONNECT_DELAY_MS
            lastHeartbeatResponse.set(System.currentTimeMillis())

            sendHandshake()
            startReaderThread()
            startHeartbeat()

            Log.d(TAG, "✅ Conectado RF (ID: ${clientId.take(8)})")

            withContext(Dispatchers.Main) {
                onConnectionStatus?.invoke(true, "ONLINE")
            }

            // Re-suscribir con estado completo
            restoreSubscriptionState()

            true
        } catch (e: Exception) {
            Log.e(TAG, "❌ Error conectando: ${e.message}")
            handleConnectionLost("Error: ${e.message}")
            false
        }
    }

    /**
     * Restaurar suscripción con estado completo de mixer
     */
    private suspend fun restoreSubscriptionState() {
        val (channels, gains, pans, mutes) = synchronized(subscriptionLock) {
            Quadruple(
                persistentChannels.toList(),
                persistentGains.toMap(),
                persistentPans.toMap(),
                persistentMutes.toMap()
            )
        }

        if (channels.isNotEmpty()) {
            Log.d(TAG, "🔄 Restaurando: ${channels.size} canales")
            subscribeWithFullState(channels, gains, pans, mutes)
        }
    }

    /**
     * Heartbeat keep-alive para detección rápida
     */
    private fun startHeartbeat() {
        heartbeatJob?.cancel()
        heartbeatJob = CoroutineScope(Dispatchers.IO).launch {
            while (!_shouldStop.get() && _isConnected.get()) {
                delay(HEARTBEAT_INTERVAL_MS)

                val timeSinceLastResponse = System.currentTimeMillis() - lastHeartbeatResponse.get()
                if (timeSinceLastResponse > HEARTBEAT_TIMEOUT_MS) {
                    Log.w(TAG, "💔 Heartbeat timeout (${timeSinceLastResponse}ms) - sin datos del servidor")
                    handleConnectionLost("Heartbeat timeout")
                    break
                }

                if (_isConnected.get()) {
                    try {
                        sendControlMessage("heartbeat", mapOf(
                            "timestamp" to System.currentTimeMillis(),
                            "device_uuid" to deviceUUID
                        ))
                    } catch (e: Exception) {
                        Log.w(TAG, "⚠️ Error enviando heartbeat: ${e.message}")
                    }
                }
            }
        }
    }

    /**
     * Manejo de pérdida de conexión con auto-reconexión
     */
    private fun handleConnectionLost(reason: String) {
        Log.w(TAG, "📡 Señal RF perdida: $reason")

        val wasConnected = _isConnected.getAndSet(false)
        heartbeatJob?.cancel()
        closeResources()

        CoroutineScope(Dispatchers.Main).launch {
            if (wasConnected) {
                onConnectionStatus?.invoke(false, "📡 BUSCANDO SEÑAL...")
            }
        }

        if (AUTO_RECONNECT && !_shouldStop.get() && rfMode) {
            startAutoReconnect()
        }
    }

    private fun startAutoReconnect() {
        reconnectJob?.cancel()

        reconnectJob = CoroutineScope(Dispatchers.IO).launch {
            var attempt = 1

            while (!_shouldStop.get() && !_isConnected.get() && rfMode) {
                Log.d(TAG, "🔄 Reconexión #$attempt (delay: ${currentReconnectDelay}ms)")

                delay(currentReconnectDelay)

                try {
                    if (connectInternal()) {
                        Log.i(TAG, "✅ Reconexión exitosa (#$attempt)")
                        currentReconnectDelay = RECONNECT_DELAY_MS
                        return@launch
                    }
                } catch (e: Exception) {
                    Log.w(TAG, "❌ Intento #$attempt falló: ${e.message}")
                }

                // ✅ FIX: Backoff exponencial pero con máximo limitado para reconexión rápida
                currentReconnectDelay = (currentReconnectDelay * RECONNECT_BACKOFF)
                    .toLong()
                    .coerceAtMost(MAX_RECONNECT_DELAY_MS)
                    .coerceAtLeast(500L)  // ✅ NUEVO: Mínimo 500ms

                attempt++

                // ✅ Log de progreso
                if (attempt % 5 == 0) {
                    Log.w(TAG, "⚠️ Llevamos $attempt intentos, retryando...")
                }
            }
        }
    }


    /**
     * Desconectar (desactiva auto-reconexión y heartbeat)
     */
    fun disconnect(reason: String = "Desconexión manual") {
        Log.d(TAG, "🔌 Desconectando: $reason")

        _shouldStop.set(true)
        rfMode = false

        heartbeatJob?.cancel()
        reconnectJob?.cancel()
        closeResources()

        _isConnected.set(false)

        CoroutineScope(Dispatchers.Main).launch {
            onConnectionStatus?.invoke(false, "⚫ OFFLINE")
        }
    }

    private fun forceClose() {
        _shouldStop.set(true)
        rfMode = false
        heartbeatJob?.cancel()
        reconnectJob?.cancel()
        closeResources()
        _isConnected.set(false)
    }

    private fun closeResources() {
        try { outputStream?.close() } catch (_: Exception) {}
        try { inputStream?.close() } catch (_: Exception) {}
        try { socket?.close() } catch (_: Exception) {}
        outputStream = null
        inputStream = null
        socket = null
    }

    /**
     * Suscribir a canales (guarda estado persistente)
     */
    fun subscribe(channels: List<Int>) {
        synchronized(subscriptionLock) {
            persistentChannels = channels.toList()
        }

        if (_isConnected.get()) {
            CoroutineScope(Dispatchers.IO).launch {
                sendControlMessage("subscribe", mapOf(
                    "client_id" to clientId,
                    "device_uuid" to deviceUUID,
                    "channels" to channels,
                    "timestamp" to System.currentTimeMillis(),
                    "rf_mode" to true,
                    "persistent" to true
                ))
            }
        } else {
            Log.w(TAG, "⚠️ Sin conexión - Canales guardados: $channels")
        }
    }

    /**
     * Suscribir con estado completo de mixer
     */
    private fun subscribeWithFullState(
        channels: List<Int>,
        gains: Map<Int, Float>,
        pans: Map<Int, Float>,
        mutes: Map<Int, Boolean>
    ) {
        if (!_isConnected.get()) return

        CoroutineScope(Dispatchers.IO).launch {
            sendControlMessage("subscribe", mapOf(
                "client_id" to clientId,
                "device_uuid" to deviceUUID,
                "channels" to channels,
                "gains" to gains.mapKeys { it.key.toString() },
                "pans" to pans.mapKeys { it.key.toString() },
                "mutes" to mutes.mapKeys { it.key.toString() },
                "timestamp" to System.currentTimeMillis(),
                "rf_mode" to true,
                "persistent" to true
            ))
        }
    }

    /**
     * Enviar actualización de mixer al servidor
     * El servidor propaga a todos los clientes (web + android)
     */
    fun sendMixUpdate(
        channels: List<Int>? = null,
        gains: Map<Int, Float>? = null,
        pans: Map<Int, Float>? = null,
        mutes: Map<Int, Boolean>? = null
    ) {
        // Actualizar estado local persistente
        synchronized(subscriptionLock) {
            channels?.let { persistentChannels = it.toList() }
            gains?.let { persistentGains = persistentGains + it }
            pans?.let { persistentPans = persistentPans + it }
            mutes?.let { persistentMutes = persistentMutes + it }
        }

        val data = mutableMapOf<String, Any>(
            "device_uuid" to deviceUUID,
            "timestamp" to System.currentTimeMillis()
        )

        channels?.let { data["channels"] = it }
        gains?.let { data["gains"] = it.mapKeys { e -> e.key.toString() } }
        pans?.let { data["pans"] = it.mapKeys { e -> e.key.toString() } }
        mutes?.let { data["mutes"] = it.mapKeys { e -> e.key.toString() } }

        if (data.size > 2) {
            sendControlMessage("update_mix", data)
        }
    }

    private fun sendHandshake() {
        sendControlMessage("handshake", mapOf(
            "client_id" to clientId,
            "device_uuid" to deviceUUID,
            "client_type" to "android",
            "protocol_version" to PROTOCOL_VERSION,
            "timestamp" to System.currentTimeMillis(),
            "rf_mode" to true,
            "persistent" to true,
            "auto_reconnect" to true,
            "optimized" to true
        ))
    }

    private fun startReaderThread() {
        CoroutineScope(Dispatchers.IO).launch {
            setThreadPriority()
            val headerBuffer = ByteArray(HEADER_SIZE)

            while (!_shouldStop.get()) {
                try {
                    if (!_isConnected.get()) {
                        delay(1000)
                        continue
                    }

                    val input = inputStream ?: run {
                        handleConnectionLost("InputStream null")
                        break
                    }

                    // ✅ FIX: Proteger lectura con mutex (DataInputStream no es thread-safe)
                    synchronized(readLock) {
                        input.readFully(headerBuffer)
                    }

                    val header = decodeHeader(headerBuffer)

                    if (header.magic != MAGIC_NUMBER) {
                        consecutiveMagicErrors++
                        Log.w(TAG, "⚠️ Magic error #$consecutiveMagicErrors/$maxConsecutiveMagicErrors")

                        if (consecutiveMagicErrors >= maxConsecutiveMagicErrors) {
                            handleConnectionLost("Protocolo inválido ($consecutiveMagicErrors errores consecutivos)")
                            break
                        }
                        // ✅ FIX: Skip este byte y esperar el siguiente frame (resincronización suave)
                        delay(50)
                        continue
                    }

                    consecutiveMagicErrors = 0

                    val maxPayload = if (header.msgType == MSG_TYPE_CONTROL)
                        MAX_CONTROL_PAYLOAD else MAX_AUDIO_PAYLOAD

                    if (header.payloadLength < 0 || header.payloadLength > maxPayload) {
                        Log.w(TAG, "⚠️ Payload inválido: ${header.payloadLength}")
                        continue
                    }

                    val payload = ByteArray(header.payloadLength)
                    if (header.payloadLength > 0) {
                        // ✅ FIX: Proteger lectura de payload también
                        synchronized(readLock) {
                            input.readFully(payload)
                        }
                    }

                    // ✅ FIX: Actualizar heartbeat cuando recibimos CUALQUIER dato (más robusto)
                    lastHeartbeatResponse.set(System.currentTimeMillis())

                    when (header.msgType) {
                        MSG_TYPE_AUDIO -> {
                            decodeAudioPayload(payload, header.flags)?.let { audioData ->
                                try {
                                    onAudioData?.invoke(audioData)
                                } catch (e: Exception) {
                                    Log.e(TAG, "Error callback audio: ${e.message}")
                                }
                            }
                        }
                        MSG_TYPE_CONTROL -> handleControlMessage(payload)
                    }
                } catch (e: java.io.EOFException) {
                    handleConnectionLost("Servidor desconectado")
                    break
                } catch (e: java.net.SocketTimeoutException) {
                    continue
                } catch (e: Exception) {
                    if (!_shouldStop.get()) {
                        handleConnectionLost("Error: ${e.message}")
                    }
                    break
                }
            }
        }
    }

    private fun setThreadPriority() {
        try {
            Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_AUDIO)
        } catch (e: Exception) {
            Log.w(TAG, "⚠️ No se pudo establecer prioridad: ${e.message}")
        }
    }

    private fun handleControlMessage(payload: ByteArray) {
        try {
            val message = String(payload, Charsets.UTF_8)
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
                        "state_restored" to json.optBoolean("state_restored", false),
                        "is_reconnection" to json.optBoolean("is_reconnection", false),
                        "web_controlled" to json.optBoolean("web_controlled", true)
                    )
                    CoroutineScope(Dispatchers.Main).launch {
                        onServerInfo?.invoke(serverInfo)
                    }
                }

                "heartbeat_response" -> {
                    lastHeartbeatResponse.set(System.currentTimeMillis())
                }

                "subscription_confirmed" -> {
                    Log.d(TAG, "✅ Suscripción confirmada")
                }

                "mix_state" -> {
                    val mixState = parseMixState(json)

                    // Actualizar estado local
                    synchronized(subscriptionLock) {
                        persistentChannels = mixState.channels
                        persistentGains = mixState.gains
                        persistentPans = mixState.pans
                        persistentMutes = mixState.mutes
                    }

                    CoroutineScope(Dispatchers.Main).launch {
                        onMixState?.invoke(mixState)
                    }
                }

                "control_update" -> {
                    // Sincronización de controles desde web o servidor
                    val update = parseControlUpdate(json)
                    CoroutineScope(Dispatchers.Main).launch {
                        onControlSync?.invoke(update)
                    }
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error procesando control: ${e.message}")
        }
    }

    private fun parseMixState(json: JSONObject): MixState {
        val channelsJson = json.optJSONArray("channels")
        val channels = mutableListOf<Int>()
        if (channelsJson != null) {
            for (i in 0 until channelsJson.length()) {
                channels.add(channelsJson.optInt(i))
            }
        }

        val solosJson = json.optJSONArray("solos")
        val solos = mutableListOf<Int>()
        if (solosJson != null) {
            for (i in 0 until solosJson.length()) {
                solos.add(solosJson.optInt(i))
            }
        }

        return MixState(
            channels = channels,
            gains = parseFloatMap(json.optJSONObject("gains")),
            pans = parseFloatMap(json.optJSONObject("pans")),
            mutes = parseBoolMap(json.optJSONObject("mutes")),
            preListen = if (json.has("pre_listen") && !json.isNull("pre_listen"))
                json.optInt("pre_listen") else null,
            solos = solos,
            masterGain = if (json.has("master_gain") && !json.isNull("master_gain"))
                json.optDouble("master_gain", 1.0).toFloat() else null
        )
    }

    private fun parseControlUpdate(json: JSONObject): ControlUpdate {
        return ControlUpdate(
            source = json.optString("source", "server"),
            channel = json.optInt("channel", -1),
            gain = if (json.has("gain")) json.optDouble("gain").toFloat() else null,
            pan = if (json.has("pan")) json.optDouble("pan").toFloat() else null,
            active = if (json.has("active")) json.optBoolean("active") else null,
            mute = if (json.has("mute")) json.optBoolean("mute") else null
        )
    }

    private fun parseFloatMap(obj: JSONObject?): Map<Int, Float> {
        if (obj == null) return emptyMap()
        val out = mutableMapOf<Int, Float>()
        val it = obj.keys()
        while (it.hasNext()) {
            val k = it.next()
            val ch = k.toIntOrNull() ?: continue
            out[ch] = obj.optDouble(k, 0.0).toFloat()
        }
        return out
    }

    private fun parseBoolMap(obj: JSONObject?): Map<Int, Boolean> {
        if (obj == null) return emptyMap()
        val out = mutableMapOf<Int, Boolean>()
        val it = obj.keys()
        while (it.hasNext()) {
            val k = it.next()
            val ch = k.toIntOrNull() ?: continue
            out[ch] = obj.optBoolean(k, false)
        }
        return out
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

    /**
     * ✅ OPTIMIZADO: Decodificación de audio con buffers reutilizables y menos allocations
     */
    private fun decodeAudioPayload(payload: ByteArray, flags: Int): FloatAudioData? {
        if (payload.size < 12) return null

        try {
            val buffer = ByteBuffer.wrap(payload).order(ByteOrder.BIG_ENDIAN)
            val samplePosition = buffer.long
            val channelMask = buffer.int

            // ✅ OPTIMIZADO: Usar Integer.bitCount para contar canales activos
            val numActiveChannels = Integer.bitCount(channelMask)
            if (numActiveChannels == 0) return null

            // ✅ OPTIMIZADO: Construir lista de canales activos más eficientemente
            val activeChannels = ArrayList<Int>(numActiveChannels)
            var mask = channelMask
            var channelIndex = 0
            while (mask != 0) {
                if ((mask and 1) != 0) {
                    activeChannels.add(channelIndex)
                }
                mask = mask ushr 1
                channelIndex++
            }

            val remainingBytes = payload.size - 12
            val isInt16 = (flags and FLAG_INT16) != 0

            val floatArray: FloatArray
            var shortArrayToRelease: ShortArray? = null

            if (isInt16) {
                val shortCount = remainingBytes / 2
                if (shortCount % numActiveChannels != 0) return null

                val shortBuffer = buffer.asShortBuffer()
                val shortArray = acquireShortBuffer(shortCount)
                shortArrayToRelease = shortArray
                shortBuffer.get(shortArray, 0, shortCount)

                // ✅ OPTIMIZADO: Loop desenrollado para conversión Int16->Float
                floatArray = acquireFloatBuffer(shortCount)
                var i = 0
                val limit = shortCount - (shortCount % 4)

                // Procesar en bloques de 4 (SIMD-friendly)
                while (i < limit) {
                    floatArray[i] = shortArray[i] * INVERSE_32768
                    floatArray[i + 1] = shortArray[i + 1] * INVERSE_32768
                    floatArray[i + 2] = shortArray[i + 2] * INVERSE_32768
                    floatArray[i + 3] = shortArray[i + 3] * INVERSE_32768
                    i += 4
                }
                // Resto
                while (i < shortCount) {
                    floatArray[i] = shortArray[i] * INVERSE_32768
                    i++
                }

                // Devolver buffer al pool
                releaseShortBuffer(shortArray)
                shortArrayToRelease = null
            } else {
                val floatCount = remainingBytes / 4
                if (floatCount % numActiveChannels != 0) return null

                val floatBuffer = buffer.asFloatBuffer()
                floatArray = acquireFloatBuffer(floatCount)
                floatBuffer.get(floatArray, 0, floatCount)
            }

            val samplesPerChannel = floatArray.size / numActiveChannels
            if (samplesPerChannel == 0) {
                releaseFloatBuffer(floatArray)
                return null
            }

            // ✅ OPTIMIZADO: Desentrelazado más eficiente
            val audioData = Array(numActiveChannels) { FloatArray(samplesPerChannel) }
            for (c in 0 until numActiveChannels) {
                val channelData = audioData[c]
                var srcIndex = c
                for (s in 0 until samplesPerChannel) {
                    channelData[s] = floatArray[srcIndex]
                    srcIndex += numActiveChannels
                }
            }

            // Devolver buffer al pool (el audioData es nuevo, no del pool)
            releaseFloatBuffer(floatArray)

            return FloatAudioData(samplePosition, activeChannels, audioData, samplesPerChannel)
        } catch (e: Exception) {
            return null
        }
    }

    private fun sendControlMessage(type: String, data: Map<String, Any>) {
        if (!_isConnected.get() || _shouldStop.get()) return

        CoroutineScope(Dispatchers.IO).launch {
            try {
                val message = buildJsonMessage(type, data)
                val messageBytes = message.toByteArray(Charsets.UTF_8)

                val header = ByteBuffer.allocate(HEADER_SIZE).order(ByteOrder.BIG_ENDIAN)
                header.putInt(MAGIC_NUMBER)
                header.putShort(PROTOCOL_VERSION.toShort())
                header.putShort(((MSG_TYPE_CONTROL shl 8) or FLAG_RF_MODE).toShort())
                header.putInt((System.currentTimeMillis() % Int.MAX_VALUE).toInt())
                header.putInt(messageBytes.size)

                synchronized(this@NativeAudioClient) {
                    outputStream?.write(header.array())
                    outputStream?.write(messageBytes)
                    outputStream?.flush()
                }
            } catch (e: Exception) {
                Log.e(TAG, "❌ Error enviando '$type': ${e.message}")
                handleConnectionLost("Error enviando")
            }
        }
    }

    private fun buildJsonMessage(type: String, data: Map<String, Any>): String {
        return buildString {
            append("{\"type\":\"$type\"")
            data.forEach { (key, value) ->
                append(",\"$key\":")
                when (value) {
                    is String -> append("\"$value\"")
                    is Number -> append(value)
                    is Boolean -> append(value)
                    is Map<*, *> -> {
                        append("{")
                        val entries = value.entries.mapNotNull { (k, v) ->
                            val keyStr = k?.toString() ?: return@mapNotNull null
                            keyStr to v
                        }
                        append(entries.joinToString(",") { (k, v) ->
                            "\"$k\":${when (v) {
                                is String -> "\"$v\""
                                is Number -> v
                                is Boolean -> v
                                else -> "null"
                            }}"
                        })
                        append("}")
                    }
                    is List<*> -> {
                        append("[")
                        append(value.joinToString(",") {
                            when (it) {
                                is Number -> it.toString()
                                is String -> "\"$it\""
                                else -> "null"
                            }
                        })
                        append("]")
                    }
                    else -> append("\"$value\"")
                }
            }
            append("}")
        }
    }

    fun isConnected() = _isConnected.get() && !_shouldStop.get()

    fun getRFStatus(): String {
        return when {
            _isConnected.get() -> "ONLINE"
            reconnectJob?.isActive == true -> "🔄 BUSCANDO..."
            else -> "OFFLINE"
        }
    }

    // Data classes
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
            return samplePosition == other.samplePosition &&
                    activeChannels == other.activeChannels &&
                    audioData.contentDeepEquals(other.audioData) &&
                    samplesPerChannel == other.samplesPerChannel
        }

        override fun hashCode(): Int {
            var result = samplePosition.hashCode()
            result = 31 * result + activeChannels.hashCode()
            result = 31 * result + audioData.contentDeepHashCode()
            result = 31 * result + samplesPerChannel
            return result
        }
    }

    data class MixState(
        val channels: List<Int>,
        val gains: Map<Int, Float>,
        val pans: Map<Int, Float>,
        val mutes: Map<Int, Boolean>,
        val preListen: Int?,
        val solos: List<Int>,
        val masterGain: Float?
    )

    data class ControlUpdate(
        val source: String,
        val channel: Int,
        val gain: Float?,
        val pan: Float?,
        val active: Boolean?,
        val mute: Boolean?
    )

    private data class Quadruple<A, B, C, D>(val first: A, val second: B, val third: C, val fourth: D)
}
