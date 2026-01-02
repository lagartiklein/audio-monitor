package com.cepalabsfree.fichatech.audiostream

import android.os.Process
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

/**
 *
 * ✅ MODO RF: Auto-reconexión + Estado persistente
 */
class NativeAudioClient(private val deviceUUID: String? = null) {

    companion object {

        private const val TAG = "NativeAudioClient"

        private const val CONNECT_TIMEOUT = 5000

        private const val READ_TIMEOUT = 10000 // ✅ Timeout reducido para detectar fallas rápido

        private const val HEADER_SIZE = 16

        private const val MAGIC_NUMBER = 0xA1D10A7C.toInt()

        private const val PROTOCOL_VERSION = 2

        private const val MSG_TYPE_AUDIO = 0x01

        private const val MSG_TYPE_CONTROL = 0x02

        private const val FLAG_FLOAT32 = 0x01

        private const val FLAG_INT16 = 0x02 // ✅ NUEVO

        private const val FLAG_RF_MODE = 0x80

        private const val MAX_CONTROL_PAYLOAD = 500_000

        private const val MAX_AUDIO_PAYLOAD = 2_000_000

        // ✅ Socket optimizado

        private const val SOCKET_SNDBUF = 65536

        private const val SOCKET_RCVBUF = 131072

        private const val TRAFFIC_CLASS_EF = 0xB8 // QoS Expedited Forwarding

        // ✅ NUEVO: Configuración de reconexión RF

        private const val AUTO_RECONNECT = true

        private const val RECONNECT_DELAY_MS = 1000L // 1 segundo

        private const val MAX_RECONNECT_DELAY_MS = 8000L // Máximo 8 segundos

        private const val RECONNECT_BACKOFF = 1.5 // Backoff exponencial
    }

    private var socket: Socket? = null

    private var inputStream: DataInputStream? = null

    private var outputStream: DataOutputStream? = null

    @Volatile private var isConnected = false

    private var serverIp = ""

    private var serverPort = 5101

    // ✅ FASE 2 OPT 3: DirectByteBuffer para network I/O eficiente
    // Evita copia extra de datos JVM → nativa
    // Preallocated para reutilización (menos GC)
    private val networkBuffer =
        ByteBuffer.allocateDirect(8192).apply { order(ByteOrder.nativeOrder()) }
    private val floatNetworkBuffer = networkBuffer.asFloatBuffer()

    @Volatile private var shouldStop = false

    private var consecutiveMagicErrors = 0

    private val maxConsecutiveMagicErrors = 3

    // ✅ NUEVO: Estado persistente (sobrevive desconexiones)
    // Si deviceUUID viene, úsalo como clientId y device_uuid; si no, genera uno (legacy)
    private val clientId = deviceUUID ?: UUID.randomUUID().toString()

    private var persistentChannels = emptyList<Int>() // Canales deseados

    private val subscriptionLock = Any()

    private var reconnectJob: Job? = null

    private var currentReconnectDelay = RECONNECT_DELAY_MS

    // ✅ NUEVO: Modo RF activado

    @Volatile private var rfMode = true

    var onAudioData: ((FloatAudioData) -> Unit)? = null

    var onConnectionStatus: ((Boolean, String) -> Unit)? = null

    var onServerInfo: ((Map<String, Any>) -> Unit)? = null

    var onError: ((String) -> Unit)? = null

    /**
     *
     * ✅ NUEVO: Conectar en modo RF (con auto-reconexión)
     */
    suspend fun connect(ip: String, port: Int = 5101): Boolean {

        serverIp = ip.trim()

        serverPort = port

        shouldStop = false

        rfMode = true // ✅ Activar modo RF

        Log.d(TAG, "📡 Modo RF: Conectando a $ip:$port (AUTO-RECONNECT)")

        return connectInternal()
    }

    private suspend fun connectInternal(): Boolean =
        withContext(Dispatchers.IO) {
            try {

                Log.d(TAG, "🔌 Conectando RF a $serverIp:$serverPort...")

                socket =
                    Socket().apply {
                        soTimeout = READ_TIMEOUT

                        tcpNoDelay = true

                        keepAlive = true

                        sendBufferSize = SOCKET_SNDBUF

                        receiveBufferSize = SOCKET_RCVBUF

                        try {
                            trafficClass = TRAFFIC_CLASS_EF
                            Log.d(TAG, "✅ Traffic class EF configurado")
                        } catch (e: Exception) {
                            Log.w(TAG, "⚠️ No se pudo configurar traffic class: ${e.message}")
                        }

                        setSoLinger(false, 0)

                        connect(InetSocketAddress(serverIp, serverPort), CONNECT_TIMEOUT)
                    }

                inputStream = DataInputStream(
                    socket?.getInputStream()?.buffered(SOCKET_RCVBUF)
                )

                outputStream = DataOutputStream(
                    socket?.getOutputStream()?.buffered(SOCKET_SNDBUF)
                )

                isConnected = true

                consecutiveMagicErrors = 0

                currentReconnectDelay = RECONNECT_DELAY_MS // ✅ Reset delay

                sendHandshake()

                startReaderThread()

                Log.d(TAG, "✅ Conectado RF (ID: ${clientId.take(8)})")

                withContext(Dispatchers.Main) {
                    onConnectionStatus?.invoke(true, "🔴 ONLINE RF")
                }

                // ✅ Re-suscribir canales INMEDIATAMENTE (sin delay)

                val channelsToResubscribe =
                    synchronized(subscriptionLock) { persistentChannels.toList() }

                if (channelsToResubscribe.isNotEmpty()) {

                    Log.d(TAG, "🔄 Auto-restaurando canales: $channelsToResubscribe")

                    subscribe(channelsToResubscribe)
                }

                true
            } catch (e: Exception) {

                Log.e(TAG, "❌ Error conectando: ${e.message}")

                handleConnectionLost("Error: ${e.message}")

                false
            }
        }

    /**
     *
     * ✅ NUEVO: Manejo RF de pérdida de conexión (con auto-reconexión)
     */
    private fun handleConnectionLost(reason: String) {

        Log.w(TAG, "📡 Señal RF perdida: $reason")

        val wasConnected = isConnected

        isConnected = false

        closeResources()

        CoroutineScope(Dispatchers.Main).launch {
            if (wasConnected) {

                // ✅ Modo RF: "Buscando señal..." en vez de "Desconectado"

                onConnectionStatus?.invoke(false, "📡 BUSCANDO SEÑAL...")
            }
        }

        // ✅ NUEVO: Auto-reconexión en modo RF

        if (AUTO_RECONNECT && !shouldStop && rfMode) {

            startAutoReconnect()
        }
    }

    /**
     *
     * ✅ NUEVO: Reconexión automática con backoff exponencial
     */
    private fun startAutoReconnect() {

        // Cancelar reconexión anterior si existe

        reconnectJob?.cancel()

        reconnectJob =
            CoroutineScope(Dispatchers.IO).launch {
                var attempt = 1

                while (!shouldStop && !isConnected && rfMode) {

                    Log.d(
                        TAG,
                        "🔄 Intento de reconexión RF #$attempt (delay: ${currentReconnectDelay}ms)"
                    )

                    delay(currentReconnectDelay)

                    try {

                        val success = connectInternal()

                        if (success) {

                            Log.i(TAG, "✅ Reconexión RF exitosa después de $attempt intentos")

                            currentReconnectDelay = RECONNECT_DELAY_MS // Reset

                            return@launch
                        }
                    } catch (e: Exception) {

                        Log.w(TAG, "❌ Intento #$attempt falló: ${e.message}")
                    }

                    // Backoff exponencial

                    currentReconnectDelay =
                        (currentReconnectDelay * RECONNECT_BACKOFF)
                            .toLong()
                            .coerceAtMost(MAX_RECONNECT_DELAY_MS)

                    attempt++
                }

                if (shouldStop) {

                    Log.d(TAG, "🛑 Auto-reconexión cancelada (stop solicitado)")
                }
            }
    }

    /**
     *
     * ✅ Desconectar (desactiva auto-reconexión)
     */
    fun disconnect(reason: String = "Desconexión manual") {

        Log.d(TAG, "🔌 Desconectando RF: $reason")

        shouldStop = true

        rfMode = false // ✅ Desactivar modo RF

        reconnectJob?.cancel()

        closeResources()

        isConnected = false

        CoroutineScope(Dispatchers.Main).launch { onConnectionStatus?.invoke(false, "⚫ OFFLINE") }
    }

    private fun closeResources() {

        try {
            outputStream?.close()
        } catch (_: Exception) {}

        try {
            inputStream?.close()
        } catch (_: Exception) {}

        try {
            socket?.close()
        } catch (_: Exception) {}

        outputStream = null

        inputStream = null

        socket = null
    }

    /**
     *
     * ✅ Suscribir a canales (guarda estado persistente)
     */
    fun subscribe(channels: List<Int>) {

        synchronized(subscriptionLock) {
            persistentChannels = channels.toList() // ✅ Guardar estado
        }

        if (isConnected) {

            CoroutineScope(Dispatchers.IO).launch {
                val subscribeData = mutableMapOf(
                    "client_id" to clientId,
                    "channels" to channels,
                    "timestamp" to System.currentTimeMillis(),
                    "rf_mode" to true,
                    "persistent" to true
                )
                deviceUUID?.let { subscribeData["device_uuid"] = it }
                sendControlMessage("subscribe", subscribeData)
            }
        } else {

            Log.w(TAG, "⚠️ Sin conexión - Canales guardados para reconexión: $channels")
        }
    }

    private fun sendHandshake() {
        val payload = mutableMapOf<String, Any>(
            "client_id" to clientId,
            "client_type" to "android",
            "protocol_version" to PROTOCOL_VERSION,
            "timestamp" to System.currentTimeMillis(),
            "rf_mode" to true,
            "persistent" to true,
            "auto_reconnect" to true,
            "optimized" to true
        )
        deviceUUID?.let { payload["device_uuid"] = it }
        sendControlMessage("handshake", payload)
    }

    private fun startReaderThread() {

        CoroutineScope(Dispatchers.IO).launch {
            setThreadPriority()

            val headerBuffer = ByteArray(HEADER_SIZE)

            while (!shouldStop) {

                try {

                    if (!isConnected) {

                        delay(1000)

                        continue
                    }

                    val input = inputStream

                    if (input == null) {

                        Log.e(TAG, "❌ InputStream es null")

                        handleConnectionLost("InputStream null")

                        break
                    }

                    input.readFully(headerBuffer)

                    val header = decodeHeader(headerBuffer)

                    if (header.magic != MAGIC_NUMBER) {

                        consecutiveMagicErrors++

                        Log.e(TAG, "❌ Magic inválido (#$consecutiveMagicErrors)")

                        if (consecutiveMagicErrors >= maxConsecutiveMagicErrors) {

                            Log.e(TAG, "🛑 Demasiados errores de magic number")

                            handleConnectionLost("Protocolo inválido")

                            break
                        }

                        continue
                    }

                    consecutiveMagicErrors = 0

                    val maxPayload =
                        if (header.msgType == MSG_TYPE_CONTROL) {

                            MAX_CONTROL_PAYLOAD
                        } else {

                            MAX_AUDIO_PAYLOAD
                        }

                    if (header.payloadLength < 0 || header.payloadLength > maxPayload) {

                        Log.e(TAG, "❌ Payload length inválido: ${header.payloadLength}")

                        continue
                    }

                    val payload = ByteArray(header.payloadLength)

                    if (header.payloadLength > 0) {

                        input.readFully(payload)
                    }

                    when (header.msgType) {
                        MSG_TYPE_AUDIO -> {

                            val audioData = decodeAudioPayload(payload, header.flags)

                            if (audioData != null) {
                                try {
                                    onAudioData?.invoke(audioData)
                                } catch (e: Exception) {
                                    Log.e(TAG, "Error callback audio: ${e.message}")
                                }
                            }
                        }
                        MSG_TYPE_CONTROL -> {

                            handleControlMessage(payload)
                        }
                    }
                } catch (e: java.io.EOFException) {

                    Log.w(TAG, "🔌 Servidor cerró conexión")

                    handleConnectionLost("Servidor desconectado")

                    break
                } catch (e: java.net.SocketTimeoutException) {

                    // ✅ Timeout normal, continuar

                    continue
                } catch (e: Exception) {

                    if (!shouldStop) {

                        Log.e(TAG, "❌ Error lectura: ${e.message}")

                        handleConnectionLost("Error: ${e.message}")
                    }

                    break
                }
            }

            Log.d(TAG, "📖 Thread lectura finalizado")
        }
    }

    private fun setThreadPriority() {

        try {

            Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_AUDIO)

            Log.d(TAG, "✅ Thread priority: URGENT_AUDIO")
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

                    val serverInfo =
                        mapOf(
                            "server_version" to json.optString("server_version", "unknown"),
                            "protocol_version" to json.optInt("protocol_version", 0),
                            "sample_rate" to json.optInt("sample_rate", 48000),
                            "max_channels" to json.optInt("max_channels", 8),
                            "rf_mode" to json.optBoolean("rf_mode", false),
                            "latency_ms" to json.optDouble("latency_ms", 0.0)
                        )

                    Log.d(TAG, "✅ Server info: latency=${serverInfo["latency_ms"]}ms")

                    CoroutineScope(Dispatchers.Main).launch { onServerInfo?.invoke(serverInfo) }
                }
                "subscription_confirmed" -> {

                    Log.d(TAG, "✅ Suscripción confirmada RF")
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

            Log.e(TAG, "❌ Error decodificando header: ${e.message}")

            return PacketHeader(0, 0, 0, 0, 0, 0, 0)
        }
    }

    private fun decodeAudioPayload(payload: ByteArray, flags: Int): FloatAudioData? {

        if (payload.size < 12) {

            Log.e(TAG, "❌ Payload muy pequeño: ${payload.size} bytes")

            return null
        }

        try {

            val buffer = ByteBuffer.wrap(payload).order(ByteOrder.BIG_ENDIAN)

            val samplePosition = buffer.long

            val channelMask = buffer.int

            val activeChannels = mutableListOf<Int>()

            for (i in 0 until 32) {

                if ((channelMask and (1 shl i)) != 0) {

                    activeChannels.add(i)
                }
            }

            if (activeChannels.isEmpty()) {

                return null
            }

            val remainingBytes = payload.size - 12

            // ✅ NUEVO: Detectar formato basado en flags

            val isInt16 = (flags and FLAG_INT16) != 0

            val floatArray: FloatArray =
                if (isInt16) {

                    // ✅ Decodificar Int16 → Float32

                    val shortCount = remainingBytes / 2

                    if (shortCount % activeChannels.size != 0) {

                        Log.e(
                            TAG,
                            "❌ Int16 count inválido: $shortCount shorts, ${activeChannels.size} canales"
                        )

                        return null
                    }

                    val shortBuffer = buffer.asShortBuffer()

                    val shortArray = ShortArray(shortCount)

                    shortBuffer.get(shortArray)

                    // Convertir Int16 [-32768, 32767] → Float32 [-1.0, 1.0]

                    FloatArray(shortCount) { i ->
                        shortArray[i].toFloat() / 32768.0f // ✅ CORREGIDO
                    }
                } else {

                    // Float32 original

                    val floatCount = remainingBytes / 4

                    if (floatCount % activeChannels.size != 0) {

                        Log.e(
                            TAG,
                            "❌ Float count inválido: $floatCount floats, ${activeChannels.size} canales"
                        )

                        return null
                    }

                    val floatBuffer = buffer.asFloatBuffer()

                    val floatArray = FloatArray(floatCount)

                    floatBuffer.get(floatArray)

                    floatArray
                }

            val samplesPerChannel = floatArray.size / activeChannels.size

            if (samplesPerChannel == 0) {

                return null
            }

            // Desentrelazar canales

            val audioData = Array(activeChannels.size) { FloatArray(samplesPerChannel) }

            for (s in 0 until samplesPerChannel) {

                for (c in 0 until activeChannels.size) {

                    audioData[c][s] = floatArray[s * activeChannels.size + c]
                }
            }

            return FloatAudioData(samplePosition, activeChannels, audioData, samplesPerChannel)
        } catch (e: Exception) {

            Log.e(TAG, "❌ Error decodificando audio: ${e.message}")

            return null
        }
    }

    private fun sendControlMessage(type: String, data: Map<String, Any>) {

        if (!isConnected || shouldStop) {

            Log.w(TAG, "⚠️ No conectado: $type")

            return
        }

        CoroutineScope(Dispatchers.IO).launch {
            try {

                val message = buildJsonMessage(type, data)

                val messageBytes = message.toByteArray(Charsets.UTF_8)

                val header = ByteBuffer.allocate(HEADER_SIZE).order(ByteOrder.BIG_ENDIAN)

                header.putInt(MAGIC_NUMBER)

                header.putShort(PROTOCOL_VERSION.toShort())

                val flags = FLAG_RF_MODE

                header.putShort(((MSG_TYPE_CONTROL shl 8) or flags).toShort())

                header.putInt((System.currentTimeMillis() % Int.MAX_VALUE).toInt())

                header.putInt(messageBytes.size)

                outputStream?.write(header.array())

                outputStream?.write(messageBytes)

                outputStream?.flush()
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
                    is List<*> -> {

                        append("[")

                        append(
                            value.joinToString(",") {
                                when (it) {
                                    is Number -> it.toString()
                                    is String -> "\"$it\""
                                    else -> "null"
                                }
                            }
                        )

                        append("]")
                    }
                    else -> append("\"$value\"")
                }
            }

            append("}")
        }
    }

    fun isConnected() = isConnected && !shouldStop

    // ✅ NUEVO: Obtener estado RF

    fun getRFStatus(): String {

        return when {
            isConnected -> "🔴 ONLINE"
            reconnectJob?.isActive == true -> "🔄 BUSCANDO..."
            else -> "⚫ OFFLINE"
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
