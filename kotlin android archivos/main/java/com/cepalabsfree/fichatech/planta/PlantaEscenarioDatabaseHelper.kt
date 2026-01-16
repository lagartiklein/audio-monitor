package com.cepalabsfree.fichatech.planta

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import androidx.annotation.Keep

@Keep
class PlantaEscenarioDatabaseHelper(context: Context) :
    SQLiteOpenHelper(context, DATABASE_NAME, null, DATABASE_VERSION) {

    companion object {
        private const val DATABASE_NAME = "planta_escenario.db"
        private const val DATABASE_VERSION = 15

        const val TABLE_NAME = "planta_escenario"
        private const val COLUMN_ID = "id"
        const val COLUMN_NAME = "name"
        const val COLUMN_DESCRIPTION = "description"
        const val COLUMN_ICON = "icon"
        const val COLUMN_X = "x_position"
        const val COLUMN_Y = "y_position"
        const val COLUMN_SCALE = "scale"
        const val COLUMN_ROTATION = "rotation"
        const val COLUMN_BACKGROUND_URI = "background_uri"
        const val COLUMN_SOUND_ENABLED = "sound_enabled"
        const val COLUMN_X_REL = "x_rel"
        const val COLUMN_Y_REL = "y_rel"

        private const val SQL_CREATE_ENTRIES =
            "CREATE TABLE $TABLE_NAME (" +
                    "$COLUMN_ID INTEGER PRIMARY KEY AUTOINCREMENT," +
                    "$COLUMN_NAME TEXT NOT NULL," +
                    "$COLUMN_DESCRIPTION TEXT," +
                    "$COLUMN_ICON TEXT," +
                    "$COLUMN_X REAL," +
                    "$COLUMN_Y REAL," +
                    "$COLUMN_SCALE REAL," +
                    "$COLUMN_ROTATION REAL," +
                    "$COLUMN_BACKGROUND_URI TEXT," +
                    "$COLUMN_SOUND_ENABLED INTEGER," +
                    "$COLUMN_X_REL REAL," +
                    "$COLUMN_Y_REL REAL)"

        private const val SQL_DELETE_ENTRIES = "DROP TABLE IF EXISTS $TABLE_NAME"
    }

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(SQL_CREATE_ENTRIES)
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        if (oldVersion < 5) {
            db.execSQL("ALTER TABLE $TABLE_NAME ADD COLUMN $COLUMN_SCALE REAL DEFAULT 1.0")
        }
        if (oldVersion < 8) {
            db.execSQL("ALTER TABLE $TABLE_NAME ADD COLUMN $COLUMN_BACKGROUND_URI TEXT")
            db.execSQL("ALTER TABLE $TABLE_NAME ADD COLUMN $COLUMN_SOUND_ENABLED INTEGER DEFAULT 1")
        }
        if (oldVersion < 12) {
            db.execSQL("ALTER TABLE $TABLE_NAME ADD COLUMN $COLUMN_X_REL REAL DEFAULT 0.5")
            db.execSQL("ALTER TABLE $TABLE_NAME ADD COLUMN $COLUMN_Y_REL REAL DEFAULT 0.5")
        }
        if (oldVersion < 15) {
            db.execSQL("ALTER TABLE $TABLE_NAME ADD COLUMN $COLUMN_ROTATION REAL DEFAULT 0.0")
        }
    }

    fun insertScene(name: String, description: String, backgroundUri: String? = null, soundEnabled: Boolean = true): Long {
        val db = writableDatabase
        val values = ContentValues().apply {
            put(COLUMN_NAME, name)
            put(COLUMN_DESCRIPTION, description)
            put(COLUMN_BACKGROUND_URI, backgroundUri)
            put(COLUMN_SOUND_ENABLED, if (soundEnabled) 1 else 0)
            put(COLUMN_X_REL, 0.5)
            put(COLUMN_Y_REL, 0.5)
        }
        return db.insert(TABLE_NAME, null, values)
    }

    fun insertSceneElement(sceneName: String, iconName: String, x: Float, y: Float, scale: Float = 1.0f, rotation: Float = 0f, xRel: Float = 0.5f, yRel: Float = 0.5f): Long {
        val db = writableDatabase
        val values = ContentValues().apply {
            put(COLUMN_NAME, sceneName)
            put(COLUMN_ICON, iconName)
            put(COLUMN_X, x)
            put(COLUMN_Y, y)
            put(COLUMN_SCALE, scale)
            put(COLUMN_ROTATION, rotation)
            put(COLUMN_X_REL, xRel)
            put(COLUMN_Y_REL, yRel)
        }
        return db.insert(TABLE_NAME, null, values)
    }

    fun updateSceneElementPosition(elementId: Long, x: Float, y: Float, xRel: Float, yRel: Float) {
        val db = writableDatabase
        val values = ContentValues().apply {
            put(COLUMN_X, x)
            put(COLUMN_Y, y)
            put(COLUMN_X_REL, xRel)
            put(COLUMN_Y_REL, yRel)
        }
        db.update(TABLE_NAME, values, "$COLUMN_ID = ?", arrayOf(elementId.toString()))
        db.close()
    }

    fun updateSceneElementScale(elementId: Long, scale: Float) {
        val db = writableDatabase
        val values = ContentValues().apply {
            put(COLUMN_SCALE, scale)
        }
        db.update(TABLE_NAME, values, "$COLUMN_ID = ?", arrayOf(elementId.toString()))
        db.close()
    }

    fun updateSceneElementRotation(elementId: Long, rotation: Float) {
        val db = writableDatabase
        val values = ContentValues().apply {
            put(COLUMN_ROTATION, rotation)
        }
        db.update(TABLE_NAME, values, "$COLUMN_ID = ?", arrayOf(elementId.toString()))
        db.close()
    }

    fun updateSceneBackground(sceneName: String, backgroundUri: String?) {
        val db = writableDatabase
        val values = ContentValues().apply {
            put(COLUMN_BACKGROUND_URI, backgroundUri)
        }
        db.update(TABLE_NAME, values, "$COLUMN_NAME = ?", arrayOf(sceneName))
        db.close()
    }

    fun updateSceneSoundEnabled(sceneName: String, soundEnabled: Boolean) {
        val db = writableDatabase
        val values = ContentValues().apply {
            put(COLUMN_SOUND_ENABLED, if (soundEnabled) 1 else 0)
        }
        db.update(TABLE_NAME, values, "$COLUMN_NAME = ?", arrayOf(sceneName))
        db.close()
    }

    data class SceneSummary(
        val id: Long,
        val name: String,
        val description: String
    )

    fun getAllScenes(): List<SceneSummary> {
        val db = readableDatabase
        val cursor = db.rawQuery(
            "SELECT MIN($COLUMN_ID) as id, $COLUMN_NAME, $COLUMN_DESCRIPTION " +
                    "FROM $TABLE_NAME " +
                    "GROUP BY $COLUMN_NAME", null
        )

        val scenes = mutableListOf<SceneSummary>()
        while (cursor.moveToNext()) {
            val id = cursor.getLong(cursor.getColumnIndexOrThrow("id"))
            val name = cursor.getString(cursor.getColumnIndexOrThrow(COLUMN_NAME))
            val description = cursor.getString(cursor.getColumnIndexOrThrow(COLUMN_DESCRIPTION)) ?: ""
            scenes.add(SceneSummary(id, name, description))
        }
        cursor.close()
        return scenes
    }

    fun getSceneElements(sceneName: String): List<SceneElement> {
        val elements = mutableListOf<SceneElement>()
        val db = readableDatabase
        val cursor = db.query(
            TABLE_NAME,
            null,
            "$COLUMN_NAME=?",
            arrayOf(sceneName),
            null, null, null
        )

        cursor.use {
            while (it.moveToNext()) {
                elements.add(SceneElement(
                    id = it.getLong(it.getColumnIndexOrThrow(COLUMN_ID)),
                    iconName = it.getString(it.getColumnIndexOrThrow(COLUMN_ICON)),
                    x = it.getFloat(it.getColumnIndexOrThrow(COLUMN_X)),
                    y = it.getFloat(it.getColumnIndexOrThrow(COLUMN_Y)),
                    scale = it.getFloat(it.getColumnIndexOrThrow(COLUMN_SCALE)),
                    rotation = it.getFloat(it.getColumnIndexOrThrow(COLUMN_ROTATION)),
                    xRel = it.getFloat(it.getColumnIndexOrThrow(COLUMN_X_REL)),
                    yRel = it.getFloat(it.getColumnIndexOrThrow(COLUMN_Y_REL))
                ))
            }
        }
        return elements
    }

    fun getSceneBackground(sceneName: String): String? {
        val db = readableDatabase
        val cursor = db.query(
            TABLE_NAME,
            arrayOf(COLUMN_BACKGROUND_URI),
            "$COLUMN_NAME = ? AND $COLUMN_BACKGROUND_URI IS NOT NULL",
            arrayOf(sceneName),
            null, null, null
        )

        return cursor.use {
            if (it.moveToFirst()) {
                it.getString(it.getColumnIndexOrThrow(COLUMN_BACKGROUND_URI))
            } else {
                null
            }
        }
    }

    fun getSceneSoundEnabled(sceneName: String): Boolean {
        val db = readableDatabase
        val cursor = db.query(
            TABLE_NAME,
            arrayOf(COLUMN_SOUND_ENABLED),
            "$COLUMN_NAME = ?",
            arrayOf(sceneName),
            null, null, null
        )

        return cursor.use {
            if (it.moveToFirst()) {
                it.getInt(it.getColumnIndexOrThrow(COLUMN_SOUND_ENABLED)) == 1
            } else {
                true
            }
        }
    }

    fun deleteScene(sceneName: String): Int {
        val db = writableDatabase
        return db.delete(TABLE_NAME, "$COLUMN_NAME = ?", arrayOf(sceneName)).also {
            db.close()
        }
    }

    fun deleteSceneElement(elementId: Long): Int {
        val db = writableDatabase
        return db.delete(TABLE_NAME, "$COLUMN_ID = ?", arrayOf(elementId.toString())).also {
            db.close()
        }
    }

    fun deleteAllSceneElements(sceneName: String): Int {
        val db = writableDatabase
        return db.delete(TABLE_NAME, "$COLUMN_NAME = ? AND $COLUMN_ICON IS NOT NULL", arrayOf(sceneName)).also {
            db.close()
        }
    }

    data class SceneElement(
        val id: Long = 0,
        val iconName: String,
        val x: Float,
        val y: Float,
        val scale: Float,
        val rotation: Float,
        val xRel: Float,
        val yRel: Float
    )

    data class SceneInfo(
        val name: String,
        val description: String,
        val backgroundUri: String?,
        val soundEnabled: Boolean,
        val elements: List<SceneElement>
    )

    fun getSceneInfo(sceneName: String): SceneInfo? {
        val db = readableDatabase

        val sceneCursor = db.query(
            TABLE_NAME,
            arrayOf(COLUMN_DESCRIPTION, COLUMN_BACKGROUND_URI, COLUMN_SOUND_ENABLED),
            "$COLUMN_NAME = ?",
            arrayOf(sceneName),
            null, null, null
        )

        val sceneInfo = sceneCursor.use { cursor ->
            if (cursor.moveToFirst()) {
                val description = cursor.getString(cursor.getColumnIndexOrThrow(COLUMN_DESCRIPTION)) ?: ""
                val backgroundUri = cursor.getString(cursor.getColumnIndexOrThrow(COLUMN_BACKGROUND_URI))
                val soundEnabled = cursor.getInt(cursor.getColumnIndexOrThrow(COLUMN_SOUND_ENABLED)) == 1
                SceneInfo(sceneName, description, backgroundUri, soundEnabled, emptyList())
            } else {
                null
            }
        }

        val elements = getSceneElements(sceneName)

        return sceneInfo?.copy(elements = elements)
    }
}