package com.cepalabsfree.fichatech.recording

import android.content.Context
import android.media.MediaPlayer
import java.io.File

class RecordingStorage(private val context: Context) {

    fun getNewRecordingFile(recordingName: String): File {
        val recordingsDir = File(context.filesDir, "recordings")
        if (!recordingsDir.exists()) {
            recordingsDir.mkdirs()
        }
        return File(recordingsDir, "$recordingName.mp4")
    }

    fun loadRecordings(): List<Recording> {
        val recordingsDir = File(context.filesDir, "recordings")
        return if (recordingsDir.exists()) {
            recordingsDir.listFiles()?.map { file ->
                Recording(
                    id = file.hashCode().toLong(), // Just an example, this should be replaced with real ID
                    name = file.nameWithoutExtension,
                    filePath = file.absolutePath,
                    duration = getDuration(file),
                    timestamp = file.lastModified()
                )
            } ?: listOf()
        } else {
            listOf()
        }
    }

    fun deleteRecording(recording: Recording) {
        val file = File(recording.filePath)
        if (file.exists()) {
            file.delete()
        }
    }

    private fun getDuration(file: File): Long {
        val mediaPlayer = MediaPlayer()
        mediaPlayer.setDataSource(file.path)
        mediaPlayer.prepare()
        val durationMillis = mediaPlayer.duration
        mediaPlayer.release()
        return durationMillis.toLong()
    }
}
