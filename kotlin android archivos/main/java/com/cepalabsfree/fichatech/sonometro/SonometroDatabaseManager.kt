package com.cepalabsfree.fichatech.sonometro

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import android.util.Log

data class SonometroReport(val id: Long, val date: String, val averageDb: Double)

class SonometroDatabaseManager(context: Context) :
    SQLiteOpenHelper(context, DATABASE_NAME, null, DATABASE_VERSION) {

    private val TAG = "SonometroDatabaseManager"

    companion object {
        private const val DATABASE_NAME = "sonometro.db"
        private const val DATABASE_VERSION = 4

        private const val TABLE_REPORTS = "reports"
        private const val COLUMN_ID = "id"
        private const val COLUMN_DATE = "date"
        private const val COLUMN_AVERAGE_DB = "average_db"

        private const val CREATE_TABLE_REPORTS = "CREATE TABLE $TABLE_REPORTS (" +
                "$COLUMN_ID INTEGER PRIMARY KEY AUTOINCREMENT, " +
                "$COLUMN_DATE TEXT, " +
                "$COLUMN_AVERAGE_DB REAL)"
    }

    override fun onCreate(db: SQLiteDatabase?) {
        db?.execSQL(CREATE_TABLE_REPORTS)
        Log.d(TAG, "Base de datos creada")
    }

    override fun onUpgrade(db: SQLiteDatabase?, oldVersion: Int, newVersion: Int) {
        db?.execSQL("DROP TABLE IF EXISTS $TABLE_REPORTS")
        onCreate(db)
        Log.d(TAG, "Base de datos actualizada de versión $oldVersion a $newVersion")
    }

    fun insertReport(report: SonometroReport): Long {
        val db = writableDatabase
        val values = ContentValues().apply {
            put(COLUMN_DATE, report.date)
            put(COLUMN_AVERAGE_DB, report.averageDb)
        }
        val id = db.insert(TABLE_REPORTS, null, values)
        Log.d(TAG, "Reporte insertado con ID: $id, fecha: ${report.date}, dB: ${report.averageDb}")
        return id
    }

    fun deleteReport(id: Long) {
        val db = writableDatabase
        val rowsDeleted = db.delete(TABLE_REPORTS, "$COLUMN_ID = ?", arrayOf(id.toString()))
        Log.d(TAG, "Reportes eliminados: $rowsDeleted")
    }

    fun getAllReports(): List<SonometroReport> {
        val reports = mutableListOf<SonometroReport>()
        val db = readableDatabase
        val cursor = db.query(TABLE_REPORTS, null, null, null, null, null, "$COLUMN_ID DESC")

        Log.d(TAG, "Cursor count: ${cursor.count}")

        with(cursor) {
            while (moveToNext()) {
                val id = getLong(getColumnIndexOrThrow(COLUMN_ID))
                val date = getString(getColumnIndexOrThrow(COLUMN_DATE))
                val averageDb = getDouble(getColumnIndexOrThrow(COLUMN_AVERAGE_DB))
                reports.add(SonometroReport(id, date, averageDb))
                Log.d(TAG, "Reporte cargado: ID=$id, fecha=$date, dB=$averageDb")
            }
        }
        cursor.close()
        Log.d(TAG, "Total reportes cargados: ${reports.size}")
        return reports
    }
}