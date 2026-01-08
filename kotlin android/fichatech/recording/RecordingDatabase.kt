package com.cepalabsfree.fichatech.recording

import androidx.annotation.Keep
import androidx.room.Database
import androidx.room.RoomDatabase

@Keep
@Database(entities = [Recording::class], version = 4)
abstract class RecordingDatabase : RoomDatabase() {
    abstract fun recordingDao(): RecordingDao
}
