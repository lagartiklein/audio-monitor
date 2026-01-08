package com.cepalabsfree.fichatech.recording

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "recordings")
data class Recording(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val name: String,
    val filePath: String,
    val duration: Long,
    val timestamp: Long
)
