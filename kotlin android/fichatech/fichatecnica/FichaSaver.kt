package com.cepalabsfree.fichatech.fichatecnica

import android.content.ContentValues
import android.util.Log
import kotlinx.coroutines.*
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/**
 * Sistema unificado de guardado para toda la app
 * Reemplaza: UnitOfWork, TransactionCoordinator, DataRepository, CanalLockManager
 */
object FichaSaver {
    private const val TAG = "FichaSaver"

    // Control de concurrencia
    private val mutex = Mutex()
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    // Sistema de debounce para operaciones frecuentes
    private val pendingFaders = mutableMapOf<Int, Int>()
    private val pendingFieldChanges = mutableMapOf<Int, MutableMap<String, Any>>()
    private val pendingInserts = mutableListOf<InsertOperation>()

    private var faderJob: Job? = null
    private var fieldJob: Job? = null
    private var insertJob: Job? = null

    // ==================== MÉTODOS PÚBLICOS ====================

    /**
     * Para CrearFichaActivity: Crear ficha completa con canales
     */
    suspend fun crearFichaCompleta(
        dbHelper: FichaDatabaseHelper,
        nombre: String,
        descripcion: String,
        canales: MutableList<Canal>
    ): Int = mutex.withLock mutex@{
        return try {
            val db = dbHelper.writableDatabase
            db.beginTransaction()

            try {
                // 1. Crear ficha
                val fichaValues = ContentValues().apply {
                    put("nombre", nombre)
                    put("descripcion", descripcion)
                    put("ultima_modificacion", System.currentTimeMillis() / 1000)
                }

                val fichaId = db.insert("fichas", null, fichaValues)
                if (fichaId == -1L) {
                    Log.e(TAG, "❌ Error creando ficha")
                    return@mutex -1
                }

                // 2. Crear canales con IDs reales
                canales.forEachIndexed { index, canal ->
                    val canalValues = ContentValues().apply {
                        put("ficha_id", fichaId)
                        put("nombre", canal.nombre)
                        put("microfonia", canal.microfonia)
                        put("fx", canal.fx)
                        put("color", canal.color)
                        put("orden", index)
                        put("fader_level", canal.faderLevel)
                    }

                    val canalId = db.insert("canales", null, canalValues)
                    if (canalId == -1L) {
                        Log.e(TAG, "❌ Error creando canal $index")
                    } else {
                        canal.id = canalId.toInt()
                    }
                }

                db.setTransactionSuccessful()
                Log.d(TAG, "✅ Ficha creada: ID=$fichaId con ${canales.size} canales")

                fichaId.toInt()
            } finally {
                try {
                    db.endTransaction()
                } catch (e: Exception) {
                    Log.e(TAG, "Error cerrando transacción", e)
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "❌ Error en crearFichaCompleta", e)
            -1
        }
    }

    /**
     * Para ViewFichaActivity: Actualizar todo de una vez
     */
    suspend fun guardarFichaCompleta(
        dbHelper: FichaDatabaseHelper,
        fichaId: Int,
        nombre: String? = null,
        descripcion: String? = null,
        canales: List<Canal>
    ): Boolean = mutex.withLock {
        Log.d(TAG, "💾 Iniciando guardado completo para ficha $fichaId con ${canales.size} canales")

        // Verificar si hay canales sin ID
        val canalesSinId = canales.filter { it.id == -1 }
        if (canalesSinId.isNotEmpty()) {
            Log.w(TAG, "⚠️ Hay ${canalesSinId.size} canales sin ID en guardarFichaCompleta")
        }

        return try {
            val db = dbHelper.writableDatabase
            db.beginTransaction()

            try {
                // 1. SIEMPRE actualizar timestamp de la ficha (incluso si solo cambian canales)
                val fichaValues = ContentValues().apply {
                    nombre?.let { put("nombre", it) }
                    descripcion?.let { put("descripcion", it) }
                    put("ultima_modificacion", System.currentTimeMillis() / 1000)
                }
                val fichasActualizadas = db.update("fichas", fichaValues, "id = ?", arrayOf(fichaId.toString()))
                Log.d(TAG, "📝 Ficha actualizada: $fichasActualizadas filas afectadas")

                // 2. Sincronizar todos los canales
                var canalesInsertados = 0
                var canalesActualizados = 0

                canales.forEachIndexed { index, canal ->
                    if (canal.id == -1) {
                        // Insertar nuevo canal
                        val values = ContentValues().apply {
                            put("ficha_id", fichaId)
                            put("nombre", canal.nombre)
                            put("microfonia", canal.microfonia)
                            put("fx", canal.fx)
                            put("color", canal.color)
                            put("orden", index)
                            put("fader_level", canal.faderLevel)
                        }

                        val nuevoId = db.insert("canales", null, values)
                        if (nuevoId != -1L) {
                            canal.id = nuevoId.toInt()
                            canalesInsertados++
                            Log.d(TAG, "➕ Canal insertado: ID=$nuevoId, posición=$index")
                        } else {
                            Log.e(TAG, "❌ Error insertando canal en posición $index")
                        }
                    } else {
                        // Actualizar canal existente - CORREGIDO: usar "id" en lugar de "canal_id"
                        val values = ContentValues().apply {
                            put("nombre", canal.nombre)
                            put("microfonia", canal.microfonia)
                            put("fx", canal.fx)
                            put("color", canal.color)
                            put("orden", index)
                            put("fader_level", canal.faderLevel)
                        }

                        val filasActualizadas = db.update("canales", values, "id = ?", arrayOf(canal.id.toString()))
                        if (filasActualizadas > 0) {
                            canalesActualizados++
                        }
                    }
                }

                db.setTransactionSuccessful()
                Log.d(TAG, "✅ Ficha $fichaId guardada: $canalesInsertados insertados, $canalesActualizados actualizados")
                true
            } finally {
                try {
                    db.endTransaction()
                } catch (e: Exception) {
                    Log.e(TAG, "Error cerrando transacción", e)
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "❌ Error en guardarFichaCompleta", e)
            false
        }
    }

    /**
     * Método debounced para faders (para UI)
     */
    fun programarGuardadoFader(dbHelper: FichaDatabaseHelper, canalId: Int, nivel: Int, esFinal: Boolean = false) {
        synchronized(pendingFaders) {
            pendingFaders[canalId] = nivel
        }

        faderJob?.cancel()

        if (esFinal) {
            scope.launch { ejecutarGuardadoFadersPendientes(dbHelper) }
        } else {
            faderJob = scope.launch {
                delay(200)
                ejecutarGuardadoFadersPendientes(dbHelper)
            }
        }
    }

    /**
     * Método debounced para cambios de campos
     */
    fun programarGuardadoCampo(dbHelper: FichaDatabaseHelper, canalId: Int, campo: String, valor: Any) {
        synchronized(pendingFieldChanges) {
            val cambios = pendingFieldChanges.getOrPut(canalId) { mutableMapOf() }
            cambios[campo] = valor
        }

        fieldJob?.cancel()
        fieldJob = scope.launch {
            delay(300)
            ejecutarGuardadoCamposPendientes(dbHelper)
        }
    }

    /**
     * Agregar canal nuevo (con debounce para múltiples inserciones)
     */
    fun programarInsercionCanal(
        dbHelper: FichaDatabaseHelper,
        fichaId: Int,
        canal: Canal,
        orden: Int,
        callback: ((Int) -> Unit)? = null
    ) {
        synchronized(pendingInserts) {
            pendingInserts.add(InsertOperation(fichaId, canal, orden, callback))
        }

        insertJob?.cancel()
        insertJob = scope.launch {
            delay(100)
            ejecutarInsercionesPendientes(dbHelper)
        }
    }

    /**
     * Guardar orden de canales
     */
    suspend fun guardarOrdenCanales(dbHelper: FichaDatabaseHelper, fichaId: Int, canales: List<Canal>): Boolean {
        return mutex.withLock {
            try {
                val db = dbHelper.writableDatabase
                db.beginTransaction()

                try {
                    canales.forEachIndexed { index, canal ->
                        if (canal.id != -1) {
                            val values = ContentValues().apply {
                                put("orden", index)
                            }
                            db.update("canales", values, "canal_id = ?", arrayOf(canal.id.toString()))
                        }
                    }

                    // Actualizar timestamp de la ficha
                    val fichaValues = ContentValues().apply {
                        put("ultima_modificacion", System.currentTimeMillis() / 1000)
                    }
                    db.update("fichas", fichaValues, "id = ?", arrayOf(fichaId.toString()))

                    db.setTransactionSuccessful()
                    Log.d(TAG, "✅ Orden guardado: ${canales.size} canales")
                    true
                } finally {
                    db.endTransaction()
                }
            } catch (e: Exception) {
                Log.e(TAG, "❌ Error guardando orden", e)
                false
            }
        }
    }

    /**
     * Eliminar canal
     */
    suspend fun eliminarCanal(dbHelper: FichaDatabaseHelper, canalId: Int): Boolean {
        return mutex.withLock {
            try {
                val rows = dbHelper.deleteCanal(canalId)
                rows > 0
            } catch (e: Exception) {
                Log.e(TAG, "❌ Error eliminando canal", e)
                false
            }
        }
    }

    /**
     * Forzar guardado de todo lo pendiente
     */
    suspend fun flushTodo(dbHelper: FichaDatabaseHelper) {
        mutex.withLock {
            ejecutarGuardadoFadersPendientes(dbHelper)
            ejecutarGuardadoCamposPendientes(dbHelper)
            ejecutarInsercionesPendientes(dbHelper)
        }
    }

    /**
     * Cancelar todas las operaciones pendientes
     */
    fun cancelarTodo() {
        faderJob?.cancel()
        fieldJob?.cancel()
        insertJob?.cancel()

        synchronized(pendingFaders) { pendingFaders.clear() }
        synchronized(pendingFieldChanges) { pendingFieldChanges.clear() }
        synchronized(pendingInserts) { pendingInserts.clear() }
    }

    // ==================== MÉTODOS PRIVADOS ====================

    private suspend fun ejecutarGuardadoFadersPendientes(dbHelper: FichaDatabaseHelper) {
        val cambios: Map<Int, Int>

        synchronized(pendingFaders) {
            cambios = pendingFaders.toMap()
            pendingFaders.clear()
        }

        if (cambios.isEmpty()) return

        try {
            val db = dbHelper.writableDatabase
            db.beginTransaction()

            try {
                cambios.forEach { (canalId, nivel) ->
                    val values = ContentValues().apply {
                        put("fader_level", nivel)
                    }
                    db.update("canales", values, "canal_id = ?", arrayOf(canalId.toString()))
                }

                db.setTransactionSuccessful()
                Log.d(TAG, "✅ ${cambios.size} faders guardados en batch")
            } finally {
                db.endTransaction()
            }
        } catch (e: Exception) {
            Log.e(TAG, "❌ Error en batch faders", e)
        }
    }

    private suspend fun ejecutarGuardadoCamposPendientes(dbHelper: FichaDatabaseHelper) {
        val cambios: Map<Int, Map<String, Any>>

        synchronized(pendingFieldChanges) {
            cambios = pendingFieldChanges.toMap()
            pendingFieldChanges.clear()
        }

        if (cambios.isEmpty()) return

        try {
            val db = dbHelper.writableDatabase
            db.beginTransaction()

            try {
                cambios.forEach { (canalId, campos) ->
                    val values = ContentValues()
                    campos.forEach { (campo, valor) ->
                        when (valor) {
                            is String -> values.put(campo, valor)
                            is Int -> values.put(campo, valor)
                            else -> values.put(campo, valor.toString())
                        }
                    }

                    if (values.size() > 0) {
                        db.update("canales", values, "canal_id = ?", arrayOf(canalId.toString()))
                    }
                }

                db.setTransactionSuccessful()
                Log.d(TAG, "✅ ${cambios.size} campos guardados en batch")
            } finally {
                db.endTransaction()
            }
        } catch (e: Exception) {
            Log.e(TAG, "❌ Error en batch campos", e)
        }
    }

    private suspend fun ejecutarInsercionesPendientes(dbHelper: FichaDatabaseHelper) {
        val operaciones: List<InsertOperation>

        synchronized(pendingInserts) {
            operaciones = pendingInserts.toList()
            pendingInserts.clear()
            Log.d(TAG, "📦 Ejecutando ${operaciones.size} inserciones pendientes")
        }

        if (operaciones.isEmpty()) return

        try {
            val db = dbHelper.writableDatabase
            db.beginTransaction()

            try {
                var exitosas = 0
                operaciones.forEach { op ->
                    val values = ContentValues().apply {
                        put("ficha_id", op.fichaId)
                        put("nombre", op.canal.nombre)
                        put("microfonia", op.canal.microfonia)
                        put("fx", op.canal.fx)
                        put("color", op.canal.color)
                        put("orden", op.orden)
                        put("fader_level", op.canal.faderLevel)
                    }

                    val nuevoId = db.insert("canales", null, values)
                    if (nuevoId != -1L) {
                        op.canal.id = nuevoId.toInt()
                        exitosas++

                        // Ejecutar callback en el dispatcher principal
                        op.callback?.let { callback ->
                            CoroutineScope(Dispatchers.Main).launch {
                                try {
                                    callback.invoke(nuevoId.toInt())
                                } catch (e: Exception) {
                                    Log.e(TAG, "Error ejecutando callback", e)
                                }
                            }
                        }
                    } else {
                        Log.e(TAG, "❌ Error insertando canal en batch")
                    }
                }

                // Actualizar timestamp de la ficha
                if (exitosas > 0 && operaciones.isNotEmpty()) {
                    val fichaValues = ContentValues().apply {
                        put("ultima_modificacion", System.currentTimeMillis() / 1000)
                    }
                    db.update("fichas", fichaValues, "id = ?", arrayOf(operaciones[0].fichaId.toString()))
                }

                db.setTransactionSuccessful()
                Log.d(TAG, "✅ $exitosas/${operaciones.size} inserciones en batch completadas")
            } finally {
                db.endTransaction()
            }
        } catch (e: Exception) {
            Log.e(TAG, "❌ Error en batch inserciones", e)

            // Notificar error en callbacks
            operaciones.forEach { op ->
                op.callback?.let { callback ->
                    CoroutineScope(Dispatchers.Main).launch {
                        try {
                            // Pasar -1 para indicar error
                            callback.invoke(-1)
                        } catch (e: Exception) {
                            Log.e(TAG, "Error ejecutando callback de error", e)
                        }
                    }
                }
            }
        }
    }

    private data class InsertOperation(
        val fichaId: Int,
        val canal: Canal,
        val orden: Int,
        val callback: ((Int) -> Unit)?
    )
}