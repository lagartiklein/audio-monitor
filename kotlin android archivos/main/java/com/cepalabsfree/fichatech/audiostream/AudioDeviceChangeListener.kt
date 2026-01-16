package com.cepalabsfree.fichatech.audiostream

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.media.AudioManager
import android.os.Build
import android.util.Log

/**
 * ✅ Listener para detectar cambios de dispositivo de audio
 * - Detecta desconexión de auriculares
 * - Detecta conexión de dispositivos Bluetooth
 * - Permite reinicio automático del motor de audio
 */
class AudioDeviceChangeListener(
    private val onAudioDeviceChanged: () -> Unit
) : BroadcastReceiver() {

    companion object {
        private const val TAG = "AudioDeviceChangeListener"
    }

    private var isRegistered = false

    fun register(context: Context) {
        if (isRegistered) return

        try {
            val intentFilter = IntentFilter().apply {
                addAction(AudioManager.ACTION_HEADSET_PLUG)
                addAction(AudioManager.ACTION_AUDIO_BECOMING_NOISY)
            }

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                context.registerReceiver(this, intentFilter, Context.RECEIVER_EXPORTED)
            } else {
                @Suppress("UnspecifiedRegisterReceiverFlag")
                context.registerReceiver(this, intentFilter)
            }
            isRegistered = true
            Log.d(TAG, "✅ Listener de dispositivo de audio registrado")
        } catch (e: Exception) {
            Log.e(TAG, "❌ Error registrando listener: ${e.message}")
        }
    }

    fun unregister(context: Context) {
        if (!isRegistered) return

        try {
            context.unregisterReceiver(this)
            isRegistered = false
            Log.d(TAG, "✅ Listener de dispositivo de audio desregistrado")
        } catch (e: Exception) {
            Log.e(TAG, "⚠️ Error desregistrando listener: ${e.message}")
        }
    }

    override fun onReceive(context: Context?, intent: Intent?) {
        if (intent == null || context == null) return

        when (intent.action) {
            AudioManager.ACTION_HEADSET_PLUG -> {
                val state = intent.getIntExtra("state", -1)

                if (state == 1) {
                    Log.d(TAG, "🎧 Auriculares conectados")
                    onAudioDeviceChanged() // <--- Agregado para reiniciar stream al conectar audífonos
                } else if (state == 0) {
                    Log.d(TAG, "🔊 Auriculares desconectados - cambiando a parlante")
                    onAudioDeviceChanged()
                }
            }
            AudioManager.ACTION_AUDIO_BECOMING_NOISY -> {
                Log.d(TAG, "📢 Audio pasando a dispositivo diferente (probablemente parlante)")
                onAudioDeviceChanged()
            }
        }
    }
}
