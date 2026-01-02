// UDPAudioClient.kt - COMPLETO PARA PRODUCCIÓN
package com.cepalabsfree.fichatech.audiostream

import android.util.Log
import kotlinx.coroutines.*
import java.net.*
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.*
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import kotlin.math.abs

class UDPAudioClient {
    companion object {
        private const val TAG = "UDPAudioClient"

        // ✅ FIXED: Timeouts aumentados
        private const val UDP_BUFFER_SIZE = 65536
        private const val UDP_TIMEOUT_MS = 10000  // ✅ 10 segundos (era 5s)
        private const val MAX_PACKET_SIZE = 1472
        private const val MAGIC_NUMBER = 0xA1D10A7D.toInt()

        // Tipos de paquetes
        private const val PACKET_TYPE_AUDIO = 0x01
        private const val PACKET_TYPE_CONTROL = 0x02
        private const val PACKET_TYPE_HEARTBEAT = 0x03
        private const val PACKET_TYPE_SYNC = 0x04

        // Flags
        private const val FLAG_INT16 = 0x01
        private const val FLAG_FLOAT32 = 0x02
        private const val FLAG_COMPRESSED = 0x04

        private const val PROTOCOL_VERSION = 2
    }

    // Estado
    private var udpSocket: DatagramSocket? = null
    private var serverAddress: InetAddress? = null
    private var serverPort = 0
    private val isRunning = AtomicBoolean(false)
    private var receiveJob: Job? = null
    private var heartbeatJob: Job? = null
    private var syncJob: Job? = null

    // ID único del cliente
    private val clientId = UUID.randomUUID().toString()

    // Configuración
    private var useInt16 = true
    private var compressionLevel = 1
    private var heartbeatInterval = 10000L  // ✅ 10 segundos (era 5s)
    private var syncInterval = 20000L       // ✅ 20 segundos (era 10s)

    // Expectativas recibidas desde el servidor (para validar mismatches)
    private var expectedBlocksize: Int = 128
    private var expectedSampleRate: Int = 48000

    // Jitter buffer
    private val jitterBuffer = JitterBuffer(10) // 10 paquetes de buffer

    // Estadísticas
    data class NetworkStats(
        var packetsReceived: Long = 0,
        var packetsLost: Long = 0,
        var packetsOutOfOrder: Long = 0,
        var avgLatencyMs: Float = 0f,
        var jitterMs: Float = 0f,
        var packetLossPercent: Float = 0f,
        var bytesReceived: Long = 0,
        var lastSequence: Int = -1,
        var lastTimestamp: Long = 0
    )

    private val stats = NetworkStats()
    private val statsLock = Any()

    // Canales suscritos
    private var subscribedChannels = mutableListOf<Int>()
    private val subscriptionLock = Any()

    // Callbacks
    var onAudioData: ((FloatAudioData) -> Unit)? = null
    var onNetworkStats: ((Map<String, Any>) -> Unit)? = null
    var onServerInfo: ((Map<String, Any>) -> Unit)? = null
    var onConnectionStatus: ((Boolean, String) -> Unit)? = null
    var onError: ((String) -> Unit)? = null

    /**
     * Conectar al servidor UDP
     */
    suspend fun connect(
        serverIp: String,
        port: Int = 5102,  // ✅ Puerto UDP por defecto (separado de TCP 5101)
        handshakeJson: String? = null,
        channels: List<Int> = emptyList()
    ): Boolean {
        return withContext(Dispatchers.IO) {
            try {
                Log.d(TAG, "🔗 Conectando UDP a $serverIp:$port")

                serverAddress = InetAddress.getByName(serverIp)
                serverPort = port

                synchronized(subscriptionLock) {
                    subscribedChannels.clear()
                    subscribedChannels.addAll(channels)
                }

                // ✅ Crear socket con timeouts aumentados
                udpSocket = DatagramSocket().apply {
                    soTimeout = UDP_TIMEOUT_MS
                    receiveBufferSize = UDP_BUFFER_SIZE
                    sendBufferSize = UDP_BUFFER_SIZE
                    broadcast = false
                    reuseAddress = true
                }

                val localPort = udpSocket?.localPort ?: 0
                Log.d(TAG, "✅ Socket UDP creado en puerto local: $localPort")

                // ✅ ORDEN CORRECTO:
                // 1. Establecer flag PRIMERO
                isRunning.set(true)
                Log.d(TAG, "✅ isRunning = TRUE")

                // 2. Enviar handshake ANTES de iniciar threads
                sendHandshake(localPort, channels, handshakeJson)
                Log.d(TAG, "✅ Handshake enviado")

                // 3. Esperar respuesta (pequeño delay)
                delay(200)

                // 4. AHORA SÍ iniciar threads de recepción
                startReceiving()
                startHeartbeats()
                startSync()
                Log.d(TAG, "✅ Threads iniciados")

                // Notificar conexión exitosa
                withContext(Dispatchers.Main) {
                    onConnectionStatus?.invoke(true, "✅ UDP Conectado")
                }

                Log.d(TAG, """
                    |✅ UDP CONECTADO EXITOSAMENTE
                    |   Server: $serverIp:$port
                    |   Local Port: $localPort
                    |   Client ID: ${clientId.take(8)}
                    |   Channels: ${channels.size}
                    |   Timeout: ${UDP_TIMEOUT_MS}ms
                """.trimMargin())

                true

            } catch (e: Exception) {
                Log.e(TAG, "❌ Error conectando UDP: ${e.message}", e)

                withContext(Dispatchers.Main) {
                    onConnectionStatus?.invoke(false, "❌ Error UDP: ${e.message}")
                    onError?.invoke("Error conectando: ${e.message}")
                }

                disconnect("Connection failed")
                false
            }
        }
    }

    /**
     * Enviar handshake al servidor
     */
    private fun sendHandshake(localPort: Int, channels: List<Int>, customHandshakeJson: String? = null) {
        try {
            val handshakeData = if (customHandshakeJson != null) {
                // ✅ FASE 3: Usar handshake personalizado con UUID del dispositivo
                Log.d(TAG, "🆔 Usando handshake personalizado con UUID del dispositivo")
                // Parsear el JSON personalizado
                val json = org.json.JSONObject(customHandshakeJson)
                mapOf(
                    "type" to json.getString("type"),
                    "device_uuid" to json.getString("device_uuid"),
                    "device_name" to json.optString("device_name", ""),
                    "app_version" to json.optString("app_version", ""),
                    "protocol_version" to json.optString("protocol_version", "1.0"),
                    "client_id" to clientId,
                    "local_port" to localPort,
                    "channels" to channels,
                    "capabilities" to json.optJSONObject("capabilities"),
                    "timestamp" to json.optLong("timestamp", System.currentTimeMillis())
                )
            } else {
                // Fallback: usar formato por defecto
                mapOf(
                    "type" to "handshake",
                    "client_id" to clientId,
                    "protocol_version" to PROTOCOL_VERSION,
                    "local_port" to localPort,
                    "channels" to channels,
                    "client_type" to "android",
                    "timestamp" to System.currentTimeMillis(),
                    "features" to mapOf(
                        "int16_support" to true,
                        "compression_support" to true,
                        "jitter_buffer" to true
                    )
                )
            }

            val success = sendControlPacket(PACKET_TYPE_CONTROL, handshakeData)

            if (success) {
                Log.d(TAG, "🤝 Handshake enviado exitosamente")
                Log.d(TAG, "   Client ID: ${clientId.take(8)}")
                Log.d(TAG, "   Channels: ${channels.size}")
                Log.d(TAG, "   Protocol: v$PROTOCOL_VERSION")
            } else {
                Log.e(TAG, "❌ Fallo al enviar handshake")
            }

        } catch (e: Exception) {
            Log.e(TAG, "❌ Error enviando handshake: ${e.message}", e)
        }
    }

    /**
     * Suscribir a canales
     */
    fun subscribe(channels: List<Int>) {
        synchronized(subscriptionLock) {
            subscribedChannels.clear()
            subscribedChannels.addAll(channels)
        }

        if (isRunning.get()) {
            val subscribeData = mapOf(
                "type" to "subscribe",
                "client_id" to clientId,
                "channels" to channels,
                "timestamp" to System.currentTimeMillis()
            )

            sendControlPacket(PACKET_TYPE_CONTROL, subscribeData)
            Log.d(TAG, "📡 Suscripción enviada: ${channels.size} canales")
        } else {
            Log.w(TAG, "⚠️ No conectado - Suscripción guardada para reconexión")
        }
    }

    /**
     * Actualizar ganancia de canal
     */
    fun updateGain(channel: Int, gain: Float) {
        if (!isRunning.get()) return

        val gainData = mapOf(
            "type" to "update_gain",
            "client_id" to clientId,
            "channel" to channel,
            "gain" to gain,
            "timestamp" to System.currentTimeMillis()
        )

        sendControlPacket(PACKET_TYPE_CONTROL, gainData)
    }

    /**
     * Actualizar panorama de canal
     */
    fun updatePan(channel: Int, pan: Float) {
        if (!isRunning.get()) return

        val panData = mapOf(
            "type" to "update_pan",
            "client_id" to clientId,
            "channel" to channel,
            "pan" to pan,
            "timestamp" to System.currentTimeMillis()
        )

        sendControlPacket(PACKET_TYPE_CONTROL, panData)
    }

    private fun startReceiving() {
        receiveJob?.cancel()

        receiveJob = CoroutineScope(Dispatchers.IO).launch {
            Log.d(TAG, "📥 Thread recepción UDP iniciado")
            Log.d(TAG, "   isRunning = ${isRunning.get()}")

            val buffer = ByteArray(UDP_BUFFER_SIZE)
            var consecutiveTimeouts = 0
            val maxConsecutiveTimeouts = 20  // ✅ Permitir más timeouts

            while (isRunning.get() && udpSocket != null) {
                try {
                    val packet = DatagramPacket(buffer, buffer.size)
                    udpSocket?.receive(packet)

                    // ✅ Reset contador en éxito
                    if (consecutiveTimeouts > 0) {
                        Log.d(TAG, "✅ Recepción recuperada después de $consecutiveTimeouts timeouts")
                        consecutiveTimeouts = 0
                    }

                    // Verificar origen
                    if (serverAddress == null || packet.address.hostAddress != serverAddress?.hostAddress) {
                        Log.w(TAG, "⚠️ Paquete de dirección desconocida: ${packet.address.hostAddress}")
                        continue
                    }

                    // Procesar paquete
                    val data = packet.data.copyOf(packet.length)
                    processPacket(data, packet.address, packet.port)

                } catch (e: SocketTimeoutException) {
                    // ✅ Contar timeouts pero seguir intentando
                    consecutiveTimeouts++

                    if (consecutiveTimeouts % 5 == 0) {
                        Log.d(TAG, "⏱️ $consecutiveTimeouts timeouts consecutivos")
                    }

                    if (consecutiveTimeouts >= maxConsecutiveTimeouts) {
                        Log.w(TAG, "⚠️ Demasiados timeouts, verificar conexión")
                        consecutiveTimeouts = 0  // Reset para dar otra oportunidad
                    }
                    continue

                } catch (e: SocketException) {
                    if (isRunning.get()) {
                        Log.e(TAG, "❌ Socket error: ${e.message}")
                        break
                    }
                } catch (e: Exception) {
                    if (isRunning.get()) {
                        Log.e(TAG, "❌ Error recibiendo: ${e.message}")
                        delay(100)
                    }
                }
            }

            Log.d(TAG, "📥 Thread recepción UDP finalizado")
        }
    }

    private fun processPacket(
        packetData: ByteArray,
        address: InetAddress,
        port: Int
    ) {
        if (packetData.size < 32) {
            Log.w(TAG, "⚠️ Paquete muy pequeño: ${packetData.size} bytes")
            return
        }

        // VALIDACIÓN: evitar procesar paquetes mayores al MTU/esperado
        if (packetData.size > MAX_PACKET_SIZE) {
            Log.w(TAG, "⚠️ Paquete demasiado grande (${packetData.size} bytes) — probable fragmentación o blocksize mismatch. Se descarta.")
            return
        }

        try {
            val buffer = ByteBuffer.wrap(packetData).order(ByteOrder.BIG_ENDIAN)

            // ✅ Leer header (32 bytes exactos)
            val magic = buffer.int
            if (magic != MAGIC_NUMBER) {
                Log.w(TAG, "⚠️ Magic number inválido: 0x${magic.toString(16)} (esperado: 0x${MAGIC_NUMBER.toString(16)})")
                return
            }

            val sequence = buffer.int
            val timestamp = buffer.long
            val samplePosition = buffer.long
            val channelMask = buffer.int
            val packetType = buffer.get().toInt() and 0xFF
            val flags = buffer.get().toInt() and 0xFF
            val clientHash = buffer.short.toInt() and 0xFFFF

            // Debug: Log primer paquete de cada tipo
            if (stats.packetsReceived < 5L) {
                Log.d(TAG, """
                    |📦 Paquete recibido #${stats.packetsReceived}:
                    |   Type: $packetType
                    |   Sequence: $sequence
                    |   Size: ${packetData.size} bytes
                    |   Flags: 0x${flags.toString(16)}
                """.trimMargin())
            }

            // Procesar según tipo
            when (packetType) {
                PACKET_TYPE_AUDIO -> {
                    processAudioPacket(
                        buffer,
                        sequence,
                        timestamp,
                        samplePosition,
                        channelMask,
                        flags,
                        packetData.size - 32
                    )
                }

                PACKET_TYPE_CONTROL -> {
                    processControlPacket(buffer, packetData.size - 32)
                }

                PACKET_TYPE_HEARTBEAT -> {
                    processHeartbeatPacket(buffer, packetData.size - 32)
                }

                PACKET_TYPE_SYNC -> {
                    processSyncPacket(buffer, packetData.size - 32)
                }

                else -> {
                    Log.w(TAG, "⚠️ Tipo de paquete desconocido: $packetType")
                }
            }

        } catch (e: Exception) {
            Log.e(TAG, "❌ Error procesando paquete: ${e.message}", e)
        }
    }

    private fun processAudioPacket(
        buffer: ByteBuffer,
        sequence: Int,
        timestamp: Long,
        samplePosition: Long,
        channelMask: Int,
        flags: Int,
        payloadSize: Int
    ) {
        // Obtener canales activos de la máscara
        val activeChannels = mutableListOf<Int>()
        for (i in 0 until 32) {
            if ((channelMask and (1 shl i)) != 0) {
                activeChannels.add(i)
            }
        }

        if (activeChannels.isEmpty()) {
            return
        }

        // Decodificar audio según flags
        val isInt16 = (flags and FLAG_INT16) != 0
        val isCompressed = (flags and FLAG_COMPRESSED) != 0

        val audioData = if (isInt16) {
            // Int16 -> Float32
            val shortCount = payloadSize / 2
            val shortArray = ShortArray(shortCount)
            buffer.asShortBuffer().get(shortArray)

            FloatArray(shortCount) { i ->
                shortArray[i].toFloat() / 32767.0f
            }
        } else {
            // Float32
            val floatCount = payloadSize / 4
            val floatArray = FloatArray(floatCount)
            buffer.asFloatBuffer().get(floatArray)
            floatArray
        }

        val samplesPerChannel = audioData.size / activeChannels.size

        // VALIDACIÓN: comparar contra blocksize esperado
        if (expectedBlocksize > 0 && samplesPerChannel != expectedBlocksize) {
            Log.w(TAG, "⚠️ Blocksize mismatch: recibido=$samplesPerChannel, esperado=$expectedBlocksize (seq=$sequence)")
            // No descartamos por ahora, pero lo logueamos para depuración
        }

        // Desentrelazar canales
        val channelData = Array(activeChannels.size) { FloatArray(samplesPerChannel) }
        for (s in 0 until samplesPerChannel) {
            for (c in 0 until activeChannels.size) {
                channelData[c][s] = audioData[s * activeChannels.size + c]
            }
        }

        // Crear objeto de audio
        val floatAudioData = FloatAudioData(
            samplePosition = samplePosition,
            activeChannels = activeChannels,
            audioData = channelData,
            samplesPerChannel = samplesPerChannel,
            timestamp = timestamp,
            sequence = sequence
        )

        // Manejar jitter buffer y entregar
        jitterBuffer.addPacket(sequence, floatAudioData)?.let { orderedData ->
            deliverAudioData(orderedData)
        }

        // Actualizar estadísticas
        updateStats(sequence, timestamp, payloadSize)
    }

    private fun processControlPacket(buffer: ByteBuffer, payloadSize: Int) {
        try {
            val jsonBytes = ByteArray(payloadSize)
            buffer.get(jsonBytes)

            val jsonString = String(jsonBytes, Charsets.UTF_8)
            val data = parseJson(jsonString)

            when (data["type"] as? String) {
                "server_info" -> {
                    handleServerInfo(data)
                }
                "subscription_confirmed" -> {
                    Log.d(TAG, "✅ Suscripción confirmada por servidor")
                }
                "ack" -> {
                    // Acknowledgment normal, ignorar
                }
            }

        } catch (e: Exception) {
            Log.e(TAG, "❌ Error procesando control: ${e.message}")
        }
    }

    private fun processHeartbeatPacket(buffer: ByteBuffer, payloadSize: Int) {
        try {
            val jsonBytes = ByteArray(payloadSize)
            buffer.get(jsonBytes)

            val jsonString = String(jsonBytes, Charsets.UTF_8)
            val data = parseJson(jsonString)

            if (data["type"] == "heartbeat_ack") {
                // Actualizar estadísticas de latencia
                val serverTime = data["server_time"] as? Long ?: 0L
                val latency = System.currentTimeMillis() - serverTime

                synchronized(statsLock) {
                    stats.avgLatencyMs = (stats.avgLatencyMs * 0.9f + latency * 0.1f)
                    stats.lastTimestamp = System.currentTimeMillis()
                }

                if (latency > 100) {
                    Log.w(TAG, "⚠️ Latencia alta: ${latency}ms")
                }
            }

        } catch (e: Exception) {
            Log.e(TAG, "❌ Error procesando heartbeat: ${e.message}")
        }
    }

    private fun processSyncPacket(buffer: ByteBuffer, payloadSize: Int) {
        try {
            val jsonBytes = ByteArray(payloadSize)
            buffer.get(jsonBytes)

            val jsonString = String(jsonBytes, Charsets.UTF_8)
            val data = parseJson(jsonString)

            if (data["type"] == "sync_response") {
                val serverSamplePos = data["sample_position"] as? Long ?: 0L
                val serverSequence = data["sequence"] as? Int ?: 0

                // Podemos usar esto para sincronización avanzada
                Log.d(TAG, "🔄 Sync recibido - Sample: $serverSamplePos, Seq: $serverSequence")
            }

        } catch (e: Exception) {
            Log.e(TAG, "❌ Error procesando sync: ${e.message}")
        }
    }

    private fun handleServerInfo(data: Map<String, Any>) {
        try {
            val serverVersion = data["server_version"] as? String ?: "unknown"
            val sampleRate = data["sample_rate"] as? Int ?: 48000
            val maxChannels = data["max_channels"] as? Int ?: 8
            val blocksize = data["blocksize"] as? Int ?: 128
            val latencyMs = data["latency_ms"] as? Double ?: 0.0
            val useInt16Server = data["use_int16"] as? Boolean ?: true
            val heartbeatIntervalServer = data["heartbeat_interval"] as? Long ?: 5000L

            // Actualizar configuración
            this.useInt16 = useInt16Server
            this.heartbeatInterval = heartbeatIntervalServer

            // Guardar expectativas para validación
            this.expectedBlocksize = blocksize
            this.expectedSampleRate = sampleRate

            // Notificar a la UI
            CoroutineScope(Dispatchers.Main).launch {
                onServerInfo?.invoke(mapOf(
                    "server_version" to serverVersion,
                    "sample_rate" to sampleRate,
                    "max_channels" to maxChannels,
                    "blocksize" to blocksize,
                    "latency_ms" to latencyMs,
                    "use_int16" to useInt16Server,
                    "protocol" to "UDP"
                ))
            }

            Log.d(TAG, "✅ Información del servidor:")
            Log.d(TAG, "   Versión: $serverVersion")
            Log.d(TAG, "   Sample Rate: $sampleRate Hz")
            Log.d(TAG, "   Blocksize: $blocksize (~${latencyMs}ms)")
            Log.d(TAG, "   Int16: $useInt16Server")
            Log.d(TAG, "   Heartbeat: ${heartbeatIntervalServer}ms")

        } catch (e: Exception) {
            Log.e(TAG, "❌ Error procesando server info: ${e.message}")
        }
    }

    private fun deliverAudioData(audioData: FloatAudioData) {
        try {
            CoroutineScope(Dispatchers.Main).launch {
                onAudioData?.invoke(audioData)
            }
        } catch (e: Exception) {
            Log.e(TAG, "❌ Error entregando audio: ${e.message}")
        }
    }

    private fun updateStats(sequence: Int, timestamp: Long, payloadSize: Int) {
        synchronized(statsLock) {
            stats.packetsReceived++
            stats.bytesReceived += payloadSize

            // Calcular pérdida de paquetes
            if (stats.lastSequence != -1 && sequence > stats.lastSequence + 1) {
                val lost = sequence - stats.lastSequence - 1
                stats.packetsLost += lost
                stats.packetLossPercent = (stats.packetsLost.toFloat() / stats.packetsReceived) * 100f

                if (lost > 1) {
                    Log.w(TAG, "⚠️ Paquetes perdidos: $lost (seq: ${stats.lastSequence} -> $sequence)")
                }
            }

            stats.lastSequence = sequence

            // Calcular latencia
            val latency = System.currentTimeMillis() - timestamp
            stats.avgLatencyMs = (stats.avgLatencyMs * 0.9f + latency * 0.1f)

            // Calcular jitter
            if (stats.lastTimestamp > 0) {
                val interval = System.currentTimeMillis() - stats.lastTimestamp
                val jitter = abs(interval - heartbeatInterval)
                stats.jitterMs = (stats.jitterMs * 0.9f + jitter * 0.1f)
            }

            stats.lastTimestamp = System.currentTimeMillis()

            // Notificar estadísticas periódicamente
            if (stats.packetsReceived % 100 == 0L) {
                notifyStats()
            }
        }
    }

    private fun notifyStats() {
        val currentStats = getNetworkStats()
        CoroutineScope(Dispatchers.Main).launch {
            onNetworkStats?.invoke(currentStats)
        }
    }

    private fun startHeartbeats() {
        heartbeatJob?.cancel()

        heartbeatJob = CoroutineScope(Dispatchers.IO).launch {
            Log.d(TAG, "💓 Thread heartbeat UDP iniciado")

            while (isRunning.get() && udpSocket != null) {
                try {
                    delay(heartbeatInterval)

                    val heartbeatData = mapOf(
                        "type" to "heartbeat",
                        "client_id" to clientId,
                        "timestamp" to System.currentTimeMillis(),
                        "sequence" to jitterBuffer.getLastSequence(),
                        "stats" to getNetworkStats()
                    )

                    sendControlPacket(PACKET_TYPE_HEARTBEAT, heartbeatData)

                } catch (e: Exception) {
                    if (isRunning.get()) {
                        Log.e(TAG, "❌ Error en heartbeat: ${e.message}")
                    }
                }
            }

            Log.d(TAG, "💓 Thread heartbeat UDP finalizado")
        }
    }

    private fun startSync() {
        syncJob?.cancel()

        syncJob = CoroutineScope(Dispatchers.IO).launch {
            Log.d(TAG, "🔄 Thread sync UDP iniciado")

            while (isRunning.get() && udpSocket != null) {
                try {
                    delay(syncInterval)

                    val syncData = mapOf(
                        "type" to "sync_request",
                        "client_id" to clientId,
                        "timestamp" to System.currentTimeMillis(),
                        "client_sample_pos" to 0L, // Podríamos trackear esto
                        "client_sequence" to jitterBuffer.getLastSequence()
                    )

                    sendControlPacket(PACKET_TYPE_SYNC, syncData)

                } catch (e: Exception) {
                    if (isRunning.get()) {
                        Log.e(TAG, "❌ Error en sync: ${e.message}")
                    }
                }
            }

            Log.d(TAG, "🔄 Thread sync UDP finalizado")
        }
    }

    private fun sendControlPacket(packetType: Int, data: Map<String, Any>): Boolean {
        if (!isRunning.get() && packetType != PACKET_TYPE_CONTROL) {
            Log.w(TAG, "⚠️ Socket no listo para envío")
            return false
        }

        if (serverAddress == null) {
            Log.e(TAG, "❌ serverAddress es null")
            return false
        }

        try {
            val buffer = ByteBuffer.allocate(2048).order(ByteOrder.BIG_ENDIAN)

            // Header (32 bytes)
            buffer.putInt(MAGIC_NUMBER)
            buffer.putInt(0) // Sequence = 0 para control
            buffer.putLong(System.currentTimeMillis())
            buffer.putLong(0) // Sample position = 0
            buffer.putInt(0)  // Channel mask = 0
            buffer.put(packetType.toByte())
            buffer.put(0) // Flags = 0
            buffer.putShort(clientId.hashCode().toShort())

            // Payload JSON
            val jsonString = toJsonString(data)
            val jsonBytes = jsonString.toByteArray(Charsets.UTF_8)
            buffer.put(jsonBytes)

            // Enviar
            val packet = DatagramPacket(
                buffer.array(),
                buffer.position(),
                serverAddress,
                serverPort
            )

            udpSocket?.send(packet)

            Log.d(TAG, "📤 Paquete enviado: type=$packetType, size=${buffer.position()} bytes")
            return true

        } catch (e: Exception) {
            Log.e(TAG, "❌ Error enviando paquete: ${e.message}", e)
            return false
        }
    }

    fun disconnect(reason: String) {
        Log.d(TAG, "🔌 Desconectando cliente UDP: $reason")

        isRunning.set(false)

        // Cancelar jobs
        receiveJob?.cancel()
        heartbeatJob?.cancel()
        syncJob?.cancel()

        // Cerrar socket
        try {
            udpSocket?.close()
        } catch (e: Exception) {
            Log.w(TAG, "⚠️ Error cerrando socket: ${e.message}")
        }

        udpSocket = null
        serverAddress = null

        // Limpiar buffers
        jitterBuffer.clear()

        // Resetear estadísticas
        synchronized(statsLock) {
            stats.packetsReceived = 0
            stats.packetsLost = 0
            stats.lastSequence = -1
        }

        // Notificar desconexión
        CoroutineScope(Dispatchers.Main).launch {
            onConnectionStatus?.invoke(false, "🔌 Desconectado")
        }

        Log.d(TAG, "✅ Cliente UDP desconectado")
    }

    fun isConnected(): Boolean = isRunning.get() && udpSocket != null

    // ✅ FASE 3: Compatible con NativeAudioClient.getRFStatus()
    fun getRFStatus(): String {
        return when {
            isRunning.get() && udpSocket != null -> "🔴 ONLINE"
            isRunning.get() -> "🔄 BUSCANDO..."
            else -> "⚫ OFFLINE"
        }
    }

    fun getNetworkStats(): Map<String, Any> = synchronized(statsLock) {
        return mapOf(
            "packets_received" to stats.packetsReceived,
            "packets_lost" to stats.packetsLost,
            "packet_loss_percent" to stats.packetLossPercent,
            "avg_latency_ms" to stats.avgLatencyMs,
            "jitter_ms" to stats.jitterMs,
            "bytes_received" to stats.bytesReceived,
            "last_sequence" to stats.lastSequence,
            "jitter_buffer_size" to jitterBuffer.size(),
            "is_connected" to isConnected(),
            "client_id" to clientId.take(8)
        )
    }

    fun getSubscribedChannels(): List<Int> = synchronized(subscriptionLock) {
        return subscribedChannels.toList()
    }

    // ============================================================================
    // CLASES AUXILIARES
    // ============================================================================

    class JitterBuffer(private val maxSize: Int) {
        private val packets = ConcurrentHashMap<Int, FloatAudioData>()
        private var expectedSequence = AtomicInteger(0)
        private var bufferLock = Any()

        fun addPacket(sequence: Int, audioData: FloatAudioData): FloatAudioData? {
            synchronized(bufferLock) {
                packets[sequence] = audioData

                // Mantener tamaño máximo
                if (packets.size > maxSize) {
                    val oldestKey = packets.keys.minOrNull()
                    if (oldestKey != null) {
                        packets.remove(oldestKey)
                    }
                }

                // Entregar en orden
                return getNextPacket()
            }
        }

        private fun getNextPacket(): FloatAudioData? {
            synchronized(bufferLock) {
                val nextSeq = expectedSequence.get()
                val packet = packets.remove(nextSeq)

                if (packet != null) {
                    expectedSequence.incrementAndGet()
                    return packet
                }

                // Buscar siguiente paquete disponible (hasta 5 saltos)
                for (i in 1..5) {
                    val seq = nextSeq + i
                    val found = packets.remove(seq)
                    if (found != null) {
                        expectedSequence.set(seq + 1)
                        Log.w(TAG, "⚠️ Paquete fuera de orden: $nextSeq -> $seq")
                        return found
                    }
                }

                return null
            }
        }

        fun getLastSequence(): Int = expectedSequence.get() - 1

        fun size(): Int = synchronized(bufferLock) { packets.size }

        fun clear() {
            synchronized(bufferLock) {
                packets.clear()
                expectedSequence.set(0)
            }
        }
    }

    data class FloatAudioData(
        val samplePosition: Long,
        val activeChannels: List<Int>,
        val audioData: Array<FloatArray>,
        val samplesPerChannel: Int,
        val timestamp: Long = 0,
        val sequence: Int = 0
    ) {
        override fun equals(other: Any?): Boolean {
            if (this === other) return true
            if (javaClass != other?.javaClass) return false
            other as FloatAudioData
            if (samplePosition != other.samplePosition) return false
            if (activeChannels != other.activeChannels) return false
            if (!audioData.contentDeepEquals(other.audioData)) return false
            if (samplesPerChannel != other.samplesPerChannel) return false
            return true
        }

        override fun hashCode(): Int {
            var result = samplePosition.hashCode()
            result = 31 * result + activeChannels.hashCode()
            result = 31 * result + audioData.contentDeepHashCode()
            result = 31 * result + samplesPerChannel
            return result
        }
    }

    // ============================================================================
    // UTILIDADES JSON
    // ============================================================================

    private fun toJsonString(data: Map<String, Any>): String {
        return buildString {
            append("{")
            var first = true
            data.forEach { (key, value) ->
                if (!first) append(",")
                first = false
                append("\"$key\":")
                when (value) {
                    is String -> append("\"$value\"")
                    is Number -> append(value)
                    is Boolean -> append(value)
                    is List<*> -> {
                        append("[")
                        append(value.joinToString(",") {
                            when (it) {
                                is Number -> it.toString()
                                is String -> "\"$it\""
                                is Boolean -> it.toString()
                                else -> "null"
                            }
                        })
                        append("]")
                    }
                    is Map<*, *> -> {
                        append(toJsonString(value as Map<String, Any>))
                    }
                    else -> append("\"$value\"")
                }
            }
            append("}")
        }
    }

    private fun parseJson(jsonString: String): Map<String, Any> {
        return try {
            // Parseo simple de JSON (para evitar dependencias)
            val result = mutableMapOf<String, Any>()
            var current = jsonString.trim().removePrefix("{").removeSuffix("}")

            val pairs = current.split(",")
            for (pair in pairs) {
                val keyValue = pair.split(":", limit = 2)
                if (keyValue.size == 2) {
                    var key = keyValue[0].trim().removePrefix("\"").removeSuffix("\"")
                    var value = keyValue[1].trim()

                    when {
                        value.startsWith("\"") -> {
                            value = value.removePrefix("\"").removeSuffix("\"")
                            result[key] = value
                        }
                        value == "true" -> result[key] = true
                        value == "false" -> result[key] = false
                        value.contains(".") -> result[key] = value.toDoubleOrNull() ?: 0.0
                        else -> result[key] = value.toLongOrNull() ?: value.toIntOrNull() ?: 0
                    }
                }
            }

            result
        } catch (e: Exception) {
            Log.e(TAG, "Error parseando JSON: ${e.message}")
            emptyMap()
        }
    }
}