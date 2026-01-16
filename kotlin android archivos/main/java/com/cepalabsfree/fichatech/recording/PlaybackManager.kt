package com.cepalabsfree.fichatech.recording

import android.media.MediaPlayer
import java.io.File
import java.io.IOException

class PlaybackManager {
    private var mediaPlayer: MediaPlayer? = null
    private var isPlaying = false

    fun startPlayback(recordingFile: File) {
        if (isPlaying) {
            return
        }

        mediaPlayer = MediaPlayer().apply {
            try {
                setDataSource(recordingFile.absolutePath)
                prepare()
                start()
                this@PlaybackManager.isPlaying = true
            } catch (e: IOException) {
                e.printStackTrace()
            }
        }
    }

    fun stopPlayback() {
        if (!isPlaying) {
            return
        }

        mediaPlayer?.apply {
            stop()
            release()
        }
        mediaPlayer = null
        isPlaying = false
    }
}
