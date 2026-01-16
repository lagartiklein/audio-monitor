package com.cepalabsfree.fichatech.recording

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.Query

@Dao
interface RecordingDao {
    @Insert
    suspend fun insert(recording: Recording)

    @Query("SELECT * FROM recordings")
    suspend fun getAllRecordings(): List<Recording>

    @Query("DELETE FROM recordings WHERE id = :recordingId")
    suspend fun deleteRecordingById(recordingId: Long)
}
