package com.cepalabsfree.fichatech

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.animation.Animation
import android.view.animation.AnimationUtils
import android.widget.ImageView
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.app.AppCompatDelegate
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import com.cepalabsfree.fichatech.auth.LoginActivity
import com.google.firebase.auth.FirebaseAuth
import java.util.Locale

class SplashActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        // Aplica el modo de tema guardado antes de super.onCreate
        val prefs = getSharedPreferences("theme_prefs", MODE_PRIVATE)
        val mode = prefs.getInt("theme_mode", AppCompatDelegate.MODE_NIGHT_NO)
        AppCompatDelegate.setDefaultNightMode(mode)

        // Aplica el idioma guardado antes de super.onCreate
        val languagePrefs = getSharedPreferences("language_prefs", MODE_PRIVATE)
        val savedLanguage = languagePrefs.getString("language", null)
        val languageCode = savedLanguage ?: Locale.getDefault().language
        applyLanguage(languageCode)

        // Aplica el tema splash SOLO aquí
        setTheme(R.style.Theme_Fichatech_Splash)
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_splash)

        // Configurar Edge-to-Edge antes de setContentView
        enableEdgeToEdge()

        // Ocultar las barras del sistema (status bar y navigation bar)
        hideSystemBars()

        // Configurar insets para pantalla completa
        setupWindowInsets()

        val logo = findViewById<ImageView>(R.id.splash_logo)
        val scaleAnim = AnimationUtils.loadAnimation(this, R.anim.splash_scale)
        val rotateAnim = AnimationUtils.loadAnimation(this, R.anim.splash_rotate)

        scaleAnim.setAnimationListener(object : Animation.AnimationListener {
            override fun onAnimationStart(animation: Animation?) {}

            override fun onAnimationEnd(animation: Animation?) {
                logo.startAnimation(rotateAnim)
            }

            override fun onAnimationRepeat(animation: Animation?) {}
        })

        rotateAnim.setAnimationListener(object : Animation.AnimationListener {
            override fun onAnimationStart(animation: Animation?) {}

            override fun onAnimationEnd(animation: Animation?) {
                navigateNext()
            }

            override fun onAnimationRepeat(animation: Animation?) {}
        })

        logo.startAnimation(scaleAnim)
    }

    private fun setupWindowInsets() {
        // Permitir que el contenido se dibuje detrás de las barras del sistema
        // Sin padding para ocupar completamente pantalla (edge to edge)
        val rootView = findViewById<androidx.constraintlayout.widget.ConstraintLayout>(R.id.activity_splash)
            ?: findViewById<ImageView>(R.id.splash_logo).rootView

        ViewCompat.setOnApplyWindowInsetsListener(rootView) { view, windowInsets ->
            // No aplicar padding - el contenido debe ocupar todo
            // Las barras del sistema (status bar y navigation bar) se dibujarán sobre el contenido
            view.setPadding(0, 0, 0, 0)

            // Retornar windowInsets sin consumir para que el sistema las maneje
            windowInsets
        }
    }

    private fun hideSystemBars() {
        // Ocultar las barras del sistema (status bar y navigation bar)
        val windowInsetsController = WindowCompat.getInsetsController(window, window.decorView)
        windowInsetsController?.let {
            // Ocultar barras de estado y navegación
            it.hide(WindowInsetsCompat.Type.systemBars())
            // Comportamiento: las barras reaparecen cuando el usuario interactúa
            it.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        }
    }

    private fun navigateNext() {
        val auth = FirebaseAuth.getInstance()
        val currentUser = auth.currentUser
        val userPrefs = getSharedPreferences("user_prefs", Context.MODE_PRIVATE)
        val isGuest = userPrefs.getBoolean("is_guest", false)

        val intent = if (currentUser != null && currentUser.isEmailVerified || isGuest) {
            Intent(this, MainActivity::class.java)
        } else {
            Intent(this, LoginActivity::class.java)
        }

        startActivity(intent)
        finish()
    }

    private fun applyLanguage(languageCode: String) {
        val locale = Locale(languageCode)
        Locale.setDefault(locale)
        val config = resources.configuration
        config.setLocale(locale)
        resources.updateConfiguration(config, resources.displayMetrics)
    }
}
