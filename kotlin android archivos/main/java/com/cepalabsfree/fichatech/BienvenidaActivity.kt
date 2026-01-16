package com.cepalabsfree.fichatech

import android.animation.AnimatorSet
import android.animation.ObjectAnimator
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import androidx.appcompat.app.AppCompatActivity
import android.view.animation.AccelerateDecelerateInterpolator
import android.widget.Button
import android.widget.TextView
import com.cepalabsfree.fichatech.fichatecnica.CrearFichaActivity
import com.cepalabsfree.fichatech.fichatecnica.ViewFichaActivity
import com.cepalabsfree.fichatech.audiostream.NativeAudioStreamActivity
import androidx.appcompat.app.AppCompatDelegate

class BienvenidaActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        // Aplica el modo de tema guardado antes de super.onCreate
        val prefs = getSharedPreferences("theme_prefs", MODE_PRIVATE)
        val mode = prefs.getInt("theme_mode", AppCompatDelegate.MODE_NIGHT_NO)
        AppCompatDelegate.setDefaultNightMode(mode)
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_bienvenida)

        val tvAnimBienvenida = findViewById<TextView>(R.id.tvAnimBienvenida)
        val tvBienvenida = findViewById<TextView>(R.id.tvBienvenida)
        val btnListas = findViewById<Button>(R.id.btnListasCanales)
        val btnPlantas = findViewById<Button>(R.id.btnPlantasEscenario)
        val btnMonitor = findViewById<Button>(R.id.btnMonitorWifi)

        // Animación moderna: fade in + scale + overshoot para el mensaje principal
        tvAnimBienvenida.scaleX = 0.7f
        tvAnimBienvenida.scaleY = 0.7f
        tvAnimBienvenida.animate()
            .alpha(1f)
            .scaleX(1.1f)
            .scaleY(1.1f)
            .setDuration(900)
            .setInterpolator(AccelerateDecelerateInterpolator())
            .withEndAction {
                tvAnimBienvenida.animate()
                    .scaleX(1f)
                    .scaleY(1f)
                    .setDuration(300)
                    .setInterpolator(AccelerateDecelerateInterpolator())
                    .start()
                // Esperar 1.5 segundos antes de mostrar las opciones
                Handler(Looper.getMainLooper()).postDelayed({
                    // Animación en cascada: fade in + slide up para cada opción
                    val anim1 = ObjectAnimator.ofFloat(tvBienvenida, "alpha", 1f).setDuration(400)
                    val anim1Y = ObjectAnimator.ofFloat(tvBienvenida, "translationY", 40f, 0f).setDuration(400)
                    val anim2 = ObjectAnimator.ofFloat(btnListas, "alpha", 1f).setDuration(350)
                    val anim2Y = ObjectAnimator.ofFloat(btnListas, "translationY", 40f, 0f).setDuration(350)
                    val anim3 = ObjectAnimator.ofFloat(btnPlantas, "alpha", 1f).setDuration(350)
                    val anim3Y = ObjectAnimator.ofFloat(btnPlantas, "translationY", 40f, 0f).setDuration(350)
                    val anim4 = ObjectAnimator.ofFloat(btnMonitor, "alpha", 1f).setDuration(350)
                    val anim4Y = ObjectAnimator.ofFloat(btnMonitor, "translationY", 40f, 0f).setDuration(350)
                    val set = AnimatorSet()
                    set.playSequentially(
                        AnimatorSet().apply { playTogether(anim1, anim1Y) },
                        AnimatorSet().apply { playTogether(anim2, anim2Y) },
                        AnimatorSet().apply { playTogether(anim3, anim3Y) },
                        AnimatorSet().apply { playTogether(anim4, anim4Y) }
                    )
                    set.interpolator = AccelerateDecelerateInterpolator()
                    set.start()
                }, 1500)
            }
            .start()

        btnListas.setOnClickListener {
            // Navega a la gestión de listas de canales (CrearFichaActivity)
            val intent = Intent(this, CrearFichaActivity::class.java)
            intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_NEW_TASK)
            startActivity(intent)
            finish()
        }
        btnPlantas.setOnClickListener {
            // Navega a la visualización de plantas de escenario (MainActivity con fragmento)
            val intent = Intent(this, MainActivity::class.java)
            intent.putExtra("open_fragment", "planta_escenario")
            intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_NEW_TASK)
            startActivity(intent)
            finish()
        }
        btnMonitor.setOnClickListener {
            // Navega al monitor de audio (NativeAudioStreamActivity)
            val intent = Intent(this, NativeAudioStreamActivity::class.java)
            intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_NEW_TASK)
            startActivity(intent)
            finish()
        }
    }
}
