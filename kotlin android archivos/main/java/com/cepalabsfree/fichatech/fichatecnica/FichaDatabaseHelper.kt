package com.cepalabsfree.fichatech.fichatecnica

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import android.util.Log
import androidx.annotation.Keep

@Keep
class FichaDatabaseHelper(context: Context) : SQLiteOpenHelper(context, DATABASE_NAME, null, DATABASE_VERSION) {

    companion object {
        private const val TAG = "FichaDatabaseHelper"
        private const val DATABASE_NAME = "fichas.db"
        private const val DATABASE_VERSION = 37

        // Tabla fichas
        const val TABLE_FICHAS = "fichas"
        const val COLUMN_ID = "id"
        const val COLUMN_NOMBRE = "nombre"
        const val COLUMN_DESCRIPCION = "descripcion"
        const val COLUMN_COLOR_FONDO = "colorFondo"
        const val COLUMN_ORDEN = "orden"
        const val COLUMN_ULTIMA_MODIFICACION = "ultima_modificacion"

        // Tabla canales
        const val TABLE_CANALES = "canales"
        const val COLUMN_CANAL_ID = "canal_id"
        const val COLUMN_CANAL_NOMBRE = "nombre"
        const val COLUMN_MICROFONIA = "microfonia"
        const val COLUMN_FX = "fx"
        const val COLUMN_FICHA_ID = "ficha_id"
        const val COLUMN_CANAL_COLOR = "color"
        const val COLUMN_CANAL_ORDEN = "orden"
        const val COLUMN_FADER_LEVEL = "fader_level"
    }

    override fun onCreate(db: SQLiteDatabase) {
        // Crear tabla fichas
        val createFichasTable = """
            CREATE TABLE $TABLE_FICHAS (
                $COLUMN_ID INTEGER PRIMARY KEY AUTOINCREMENT,
                $COLUMN_NOMBRE TEXT,
                $COLUMN_DESCRIPCION TEXT,
                $COLUMN_COLOR_FONDO INTEGER,
                $COLUMN_ORDEN INTEGER DEFAULT 0,
                $COLUMN_ULTIMA_MODIFICACION INTEGER DEFAULT 0
            )
        """.trimIndent()
        db.execSQL(createFichasTable)

        // Crear tabla canales
        val createCanalesTable = """
            CREATE TABLE $TABLE_CANALES (
                $COLUMN_CANAL_ID INTEGER PRIMARY KEY AUTOINCREMENT,
                $COLUMN_CANAL_NOMBRE TEXT,
                $COLUMN_MICROFONIA TEXT,
                $COLUMN_FX TEXT,
                $COLUMN_FICHA_ID INTEGER,
                $COLUMN_CANAL_COLOR INTEGER DEFAULT ${0xFFF0F0F0.toInt()},
                $COLUMN_CANAL_ORDEN INTEGER DEFAULT 0,
                $COLUMN_FADER_LEVEL INTEGER DEFAULT 0,
                FOREIGN KEY($COLUMN_FICHA_ID) REFERENCES $TABLE_FICHAS($COLUMN_ID)
            )
        """.trimIndent()
        db.execSQL(createCanalesTable)

        // Crear índices para mejor rendimiento
        db.execSQL("CREATE INDEX idx_ficha_id ON $TABLE_CANALES($COLUMN_FICHA_ID)")
        db.execSQL("CREATE INDEX idx_orden_ficha ON $TABLE_FICHAS($COLUMN_ORDEN)")
        db.execSQL("CREATE INDEX idx_orden_canal ON $TABLE_CANALES($COLUMN_CANAL_ORDEN)")
        db.execSQL("CREATE INDEX idx_ficha_ultima_mod ON $TABLE_FICHAS($COLUMN_ULTIMA_MODIFICACION DESC, $COLUMN_ORDEN ASC)")
        db.execSQL("CREATE INDEX idx_canal_ficha_orden ON $TABLE_CANALES($COLUMN_FICHA_ID, $COLUMN_CANAL_ORDEN)")
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        // Migración desde versiones anteriores
        if (oldVersion < 25) {
            try {
                db.execSQL("ALTER TABLE $TABLE_CANALES ADD COLUMN $COLUMN_FADER_LEVEL INTEGER DEFAULT 0")
            } catch (e: Exception) {
                // La columna ya puede existir
            }
        }

        if (oldVersion < 31) {
            try {
                db.execSQL("ALTER TABLE $TABLE_FICHAS ADD COLUMN $COLUMN_ULTIMA_MODIFICACION INTEGER DEFAULT 0")
            } catch (e: Exception) {
                // La columna ya puede existir
            }
        }

        if (oldVersion < 32) {
            try {
                db.execSQL("CREATE INDEX IF NOT EXISTS idx_ficha_ultima_mod ON $TABLE_FICHAS($COLUMN_ULTIMA_MODIFICACION DESC, $COLUMN_ORDEN ASC)")
                db.execSQL("CREATE INDEX IF NOT EXISTS idx_canal_ficha_orden ON $TABLE_CANALES($COLUMN_FICHA_ID, $COLUMN_CANAL_ORDEN)")
            } catch (e: Exception) {
                Log.e("FichaDatabaseHelper", "Error creando índices", e)
            }
        }
    }

    // ==================== OPERACIONES DE FICHAS ====================

    fun insertFicha(nombre: String, descripcion: String, colorFondo: Int? = null): Long {
        val db = writableDatabase
        val values = ContentValues().apply {
            put(COLUMN_NOMBRE, nombre)
            put(COLUMN_DESCRIPCION, descripcion)
            put(COLUMN_ULTIMA_MODIFICACION, System.currentTimeMillis() / 1000)
            colorFondo?.let { put(COLUMN_COLOR_FONDO, it) }
        }
        return db.insert(TABLE_FICHAS, null, values)
    }

    fun getAllFichas(): List<Ficha> {
        val fichas = mutableListOf<Ficha>()
        val db = readableDatabase

        val cursor = db.rawQuery(
            "SELECT * FROM $TABLE_FICHAS ORDER BY $COLUMN_ULTIMA_MODIFICACION DESC, $COLUMN_ORDEN ASC, $COLUMN_ID DESC",
            null
        )

        cursor.use {
            while (it.moveToNext()) {
                val id = it.getInt(it.getColumnIndexOrThrow(COLUMN_ID))
                val nombre = it.getString(it.getColumnIndexOrThrow(COLUMN_NOMBRE))
                val descripcion = it.getString(it.getColumnIndexOrThrow(COLUMN_DESCRIPCION))
                val colorFondoIndex = it.getColumnIndex(COLUMN_COLOR_FONDO)
                val colorFondo = if (colorFondoIndex != -1 && !it.isNull(colorFondoIndex)) {
                    it.getInt(colorFondoIndex)
                } else null
                val orden = it.getInt(it.getColumnIndexOrThrow(COLUMN_ORDEN))
                val ultimaModificacion = it.getLong(it.getColumnIndexOrThrow(COLUMN_ULTIMA_MODIFICACION))

                fichas.add(Ficha(
                    id,
                    nombre,
                    descripcion,
                    getCanalesByFichaId(id),
                    colorFondo,
                    orden,
                    ultimaModificacion
                ))
            }
        }
        return fichas
    }

    fun getFichaById(id: Int): Ficha? {
        val db = readableDatabase
        val cursor = db.query(
            TABLE_FICHAS,
            null,
            "$COLUMN_ID = ?",
            arrayOf(id.toString()),
            null,
            null,
            null
        )

        return cursor.use {
            if (it.moveToFirst()) {
                val colorFondoIndex = it.getColumnIndex(COLUMN_COLOR_FONDO)
                val colorFondo = if (colorFondoIndex != -1 && !it.isNull(colorFondoIndex)) {
                    it.getInt(colorFondoIndex)
                } else null

                Ficha(
                    it.getInt(it.getColumnIndexOrThrow(COLUMN_ID)),
                    it.getString(it.getColumnIndexOrThrow(COLUMN_NOMBRE)),
                    it.getString(it.getColumnIndexOrThrow(COLUMN_DESCRIPCION)),
                    getCanalesByFichaId(it.getInt(it.getColumnIndexOrThrow(COLUMN_ID))),
                    colorFondo,
                    it.getInt(it.getColumnIndexOrThrow(COLUMN_ORDEN)),
                    it.getLong(it.getColumnIndexOrThrow(COLUMN_ULTIMA_MODIFICACION))
                )
            } else {
                null
            }
        }
    }

    fun updateFicha(id: Int, nuevoNombre: String, nuevaDescripcion: String): Int {
        val db = writableDatabase
        val values = ContentValues().apply {
            put(COLUMN_NOMBRE, nuevoNombre)
            put(COLUMN_DESCRIPCION, nuevaDescripcion)
            put(COLUMN_ULTIMA_MODIFICACION, System.currentTimeMillis() / 1000)
        }
        return db.update(TABLE_FICHAS, values, "$COLUMN_ID = ?", arrayOf(id.toString()))
    }

    fun updateFichaColor(fichaId: Int, color: Int) {
        val db = writableDatabase
        val values = ContentValues().apply {
            put(COLUMN_COLOR_FONDO, color)
            put(COLUMN_ULTIMA_MODIFICACION, System.currentTimeMillis() / 1000)
        }
        db.update(TABLE_FICHAS, values, "$COLUMN_ID = ?", arrayOf(fichaId.toString()))
    }

    fun updateFichaTimestamp(fichaId: Int) {
        val db = writableDatabase
        val values = ContentValues().apply {
            put(COLUMN_ULTIMA_MODIFICACION, System.currentTimeMillis() / 1000)
        }
        db.update(TABLE_FICHAS, values, "$COLUMN_ID = ?", arrayOf(fichaId.toString()))
    }
    fun updateFichasOrder(fichas: List<Ficha>) {
        val db = writableDatabase
        try {
            db.beginTransaction()
            fichas.forEachIndexed { index, ficha ->
                val values = ContentValues().apply {
                    put(COLUMN_ORDEN, index)
                    put(COLUMN_ULTIMA_MODIFICACION, System.currentTimeMillis() / 1000)
                }
                db.update(TABLE_FICHAS, values, "$COLUMN_ID = ?", arrayOf(ficha.id.toString()))
            }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    /**
     * Insertar canal inmediatamente (sin batch)
     * Para usar cuando se necesita asegurar la persistencia inmediata
     */
    fun insertarCanalInmediato(
        fichaId: Int,
        nombre: String,
        microfonia: String,
        fx: String,
        color: Int = 0xFF2196F3.toInt(),
        orden: Int,
        faderLevel: Int = 0
    ): Long {
        val db = writableDatabase
        db.beginTransaction()

        try {
            val values = ContentValues().apply {
                put(COLUMN_CANAL_NOMBRE, nombre)
                put(COLUMN_MICROFONIA, microfonia)
                put(COLUMN_FX, fx)
                put(COLUMN_FICHA_ID, fichaId)
                put(COLUMN_CANAL_COLOR, color)
                put(COLUMN_CANAL_ORDEN, orden)
                put(COLUMN_FADER_LEVEL, faderLevel)
            }

            val nuevoId = db.insert(TABLE_CANALES, null, values)

            if (nuevoId != -1L) {
                // Actualizar timestamp de la ficha
                val fichaValues = ContentValues().apply {
                    put(COLUMN_ULTIMA_MODIFICACION, System.currentTimeMillis() / 1000)
                }
                db.update(TABLE_FICHAS, fichaValues, "$COLUMN_ID = ?", arrayOf(fichaId.toString()))
            }

            db.setTransactionSuccessful()
            return nuevoId
        } finally {
            db.endTransaction()
        }
    }

    fun deleteFicha(id: Int): Int {
        val db = writableDatabase
        try {
            // Primero eliminar los canales asociados
            db.delete(TABLE_CANALES, "$COLUMN_FICHA_ID = ?", arrayOf(id.toString()))
            // Luego eliminar la ficha
            return db.delete(TABLE_FICHAS, "$COLUMN_ID = ?", arrayOf(id.toString()))
        } finally {
            db.close()
        }
    }

    // ==================== OPERACIONES DE CANALES ====================

    fun insertCanal(
        fichaId: Int,
        nombre: String,
        microfonia: String,
        fx: String,
        color: Int = 0xFF2196F3.toInt(),
        orden: Int = Int.MAX_VALUE,
        faderLevel: Int = 0
    ): Long {
        val db = writableDatabase

        // Calcular el orden si no se especifica
        val ordenFinal = if (orden == Int.MAX_VALUE) {
            val cursor = db.rawQuery(
                "SELECT MAX($COLUMN_CANAL_ORDEN) FROM $TABLE_CANALES WHERE $COLUMN_FICHA_ID = ?",
                arrayOf(fichaId.toString())
            )
            cursor.use {
                if (it.moveToFirst()) it.getInt(0) + 1 else 0
            }
        } else orden

        val values = ContentValues().apply {
            put(COLUMN_CANAL_NOMBRE, nombre)
            put(COLUMN_MICROFONIA, microfonia)
            put(COLUMN_FX, fx)
            put(COLUMN_FICHA_ID, fichaId)
            put(COLUMN_CANAL_COLOR, color)
            put(COLUMN_CANAL_ORDEN, ordenFinal)
            put(COLUMN_FADER_LEVEL, faderLevel)
        }

        return db.insert(TABLE_CANALES, null, values)
    }

    fun getCanalesByFichaId(fichaId: Int): List<Canal> {
        val canales = mutableListOf<Canal>()
        val db = readableDatabase
        val cursor = db.rawQuery(
            "SELECT * FROM $TABLE_CANALES WHERE $COLUMN_FICHA_ID = ? ORDER BY $COLUMN_CANAL_ORDEN ASC, $COLUMN_CANAL_ID ASC",
            arrayOf(fichaId.toString())
        )

        cursor.use {
            while (it.moveToNext()) {
                val orden = it.getInt(it.getColumnIndexOrThrow(COLUMN_CANAL_ORDEN))
                val canalId = it.getInt(it.getColumnIndexOrThrow(COLUMN_CANAL_ID))

                canales.add(Canal(
                    canalId,
                    orden + 1,  // Convertir orden BD a numeración visible
                    it.getString(it.getColumnIndexOrThrow(COLUMN_CANAL_NOMBRE)),
                    it.getString(it.getColumnIndexOrThrow(COLUMN_MICROFONIA)),
                    it.getString(it.getColumnIndexOrThrow(COLUMN_FX)),
                    it.getInt(it.getColumnIndexOrThrow(COLUMN_CANAL_COLOR)),
                    it.getInt(it.getColumnIndexOrThrow(COLUMN_FADER_LEVEL))
                ))
            }
        }

        return canales.sortedBy { it.numeroCanal - 1 }
    }

    fun updateCanal(id: Int, nombre: String, microfonia: String, fx: String, color: Int): Int {
        val db = writableDatabase
        val values = ContentValues().apply {
            put(COLUMN_CANAL_NOMBRE, nombre)
            put(COLUMN_MICROFONIA, microfonia)
            put(COLUMN_FX, fx)
            put(COLUMN_CANAL_COLOR, color)
        }
        return db.update(TABLE_CANALES, values, "$COLUMN_CANAL_ID = ?", arrayOf(id.toString()))
    }

    fun updateCanalOrder(canalId: Int, orden: Int) {
        val db = writableDatabase
        val values = ContentValues().apply {
            put(COLUMN_CANAL_ORDEN, orden)
        }
        db.update(TABLE_CANALES, values, "$COLUMN_CANAL_ID = ?", arrayOf(canalId.toString()))
    }

    fun updateCanalFader(canalId: Int, faderLevel: Int) {
        val db = writableDatabase
        val values = ContentValues().apply {
            put(COLUMN_FADER_LEVEL, faderLevel)
        }
        db.update(TABLE_CANALES, values, "$COLUMN_CANAL_ID = ?", arrayOf(canalId.toString()))
    }

    fun deleteCanal(canalId: Int): Int {
        val db = writableDatabase
        return db.delete(TABLE_CANALES, "$COLUMN_CANAL_ID = ?", arrayOf(canalId.toString()))
    }

    // ==================== MÉTODOS AUXILIARES ====================

    /**
     * Actualizar solo el nombre de un canal
     */
    fun actualizarNombreCanal(canalId: Int, nombre: String) {
        val db = writableDatabase
        val values = ContentValues().apply {
            put(COLUMN_CANAL_NOMBRE, nombre)
        }
        db.update(TABLE_CANALES, values, "$COLUMN_CANAL_ID = ?", arrayOf(canalId.toString()))
    }

    /**
     * Actualizar solo el FX de un canal
     */
    fun actualizarFxCanal(canalId: Int, fx: String) {
        val db = writableDatabase
        val values = ContentValues().apply {
            put(COLUMN_FX, fx)
        }
        db.update(TABLE_CANALES, values, "$COLUMN_CANAL_ID = ?", arrayOf(canalId.toString()))
    }

    /**
     * Actualizar solo el color de un canal
     */
    fun actualizarColorCanal(canalId: Int, color: Int) {
        val db = writableDatabase
        val values = ContentValues().apply {
            put(COLUMN_CANAL_COLOR, color)
        }
        db.update(TABLE_CANALES, values, "$COLUMN_CANAL_ID = ?", arrayOf(canalId.toString()))
    }

    /**
     * Obtener ficha con sus canales de forma optimizada
     */
    fun getFichaWithCanales(fichaId: Int): FichaWithCanales? {
        val ficha = getFichaById(fichaId) ?: return null
        return FichaWithCanales(ficha, ficha.canales)
    }

    /**
     * Métodos de batch para FichaSaver
     */

    /**
     * Actualizar múltiples faders en una transacción
     */
    fun actualizarFadersBatch(cambios: Map<Int, Int>): Boolean {
        val db = writableDatabase
        db.beginTransaction()

        try {
            cambios.forEach { (canalId, nivel) ->
                val values = ContentValues().apply {
                    put(COLUMN_FADER_LEVEL, nivel)
                }
                db.update(TABLE_CANALES, values, "$COLUMN_CANAL_ID = ?", arrayOf(canalId.toString()))
            }

            db.setTransactionSuccessful()
            return true
        } catch (e: Exception) {
            Log.e(TAG, "Error en batch faders", e)
            return false
        } finally {
            db.endTransaction()
        }
    }

    /**
     * Actualizar múltiples campos en una transacción
     */
    fun actualizarCamposBatch(cambios: Map<Int, Map<String, Any>>): Boolean {
        val db = writableDatabase
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
                    db.update(TABLE_CANALES, values, "$COLUMN_CANAL_ID = ?", arrayOf(canalId.toString()))
                }
            }

            db.setTransactionSuccessful()
            return true
        } catch (e: Exception) {
            Log.e(TAG, "Error en batch campos", e)
            return false
        } finally {
            db.endTransaction()
        }
    }

    data class FichaWithCanales(val ficha: Ficha, val canales: List<Canal>)
}