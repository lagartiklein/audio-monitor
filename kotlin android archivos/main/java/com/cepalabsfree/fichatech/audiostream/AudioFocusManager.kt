package com.cepalabsfree.fichatech.audiostream

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.os.Handler
import android.os.Looper
import android.util.Log

/**
 * ✅ AudioFocusManager SIMPLIFICADO
 * - Solo callbacks esenciales
 * - Gestión eficiente de audio focus
 * - Compatible con Android 4.0+
 */
class AudioFocusManager(context: Context) : AudioManager.OnAudioFocusChangeListener {
    private val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
    private var focusRequest: AudioFocusRequest? = null
    private var focusLocked = false
    private val focusRetryHandler = Handler(Looper.getMainLooper())
    private val focusRetryDelayMs = 800L
    private val focusRetryRunnable = Runnable {
        if (!focusLocked) {
            Log.d(TAG, "🔁 Reintentando Audio Focus")
            requestAudioFocus()
        }
    }

    // Solo callbacks críticos
    var onAudioFocusLost: (() -> Unit)? = null

    companion object {
        private const val TAG = "AudioFocusManager"
    }

    /**
     * Solicita Audio Focus para reproducción de medios
     */
    fun requestAudioFocus(): Boolean {
        return try {
            focusRequest = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
                .setAudioAttributes(AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                    .setFlags(AudioAttributes.FLAG_AUDIBILITY_ENFORCED)
                    .build())
                .setOnAudioFocusChangeListener(
                    this,
                    Handler(Looper.getMainLooper())
                )
                .build()

            val result = audioManager.requestAudioFocus(focusRequest!!)

            focusLocked = result == AudioManager.AUDIOFOCUS_REQUEST_GRANTED

            if (focusLocked) {
                Log.d(TAG, "✅ Audio Focus adquirido")
                focusRetryHandler.removeCallbacks(focusRetryRunnable)
            }

            focusLocked
        } catch (e: Exception) {
            Log.e(TAG, "❌ Error solicitando Audio Focus: ${e.message}", e)
            false
        }
    }

    /**
     * Abandona el Audio Focus
     */
    fun abandonAudioFocus() {
        try {
            focusRequest?.let {
                audioManager.abandonAudioFocusRequest(it)
                focusRequest = null
            }
            focusLocked = false
            focusRetryHandler.removeCallbacks(focusRetryRunnable)
            Log.d(TAG, "🔓 Audio Focus abandonado")
        } catch (e: Exception) {
            Log.e(TAG, "⚠️ Error abandonando Audio Focus: ${e.message}")
        }
    }

    /**
     * Callback simplificado - solo manejar pérdida permanente
     */
    override fun onAudioFocusChange(focusChange: Int) {
        when (focusChange) {
            AudioManager.AUDIOFOCUS_GAIN -> {
                Log.d(TAG, "🔊 Audio Focus ganado")
                focusLocked = true
            }

            AudioManager.AUDIOFOCUS_LOSS -> {
                Log.w(TAG, "🔇 Audio Focus PERDIDO (permanente)")
                focusLocked = false
                onAudioFocusLost?.invoke()
            }

            AudioManager.AUDIOFOCUS_LOSS_TRANSIENT,
            AudioManager.AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK -> {
                // Ignorar pérdidas transitorias - el audio continuará
                Log.d(TAG, "🔉 Audio Focus transitorio - continuando")
            }
        }
    }
}