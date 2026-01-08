package com.cepalabsfree.fichatech.auth

import android.os.Bundle
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.Toast
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat

class PrivacyPolicyActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Configurar Edge to Edge
        enableEdgeToEdge()

        // Habilitar botón de retroceso en el ActionBar
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.title = "Política de Privacidad"

        // Crear contenedor para el WebView
        val container = FrameLayout(this).apply {
            layoutParams = FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        }

        val webView = WebView(this).apply {
            layoutParams = FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        }

        container.addView(webView)
        setContentView(container)

        // Configurar insets para edge-to-edge
        ViewCompat.setOnApplyWindowInsetsListener(container) { _, windowInsets ->
            val insets = windowInsets.getInsets(WindowInsetsCompat.Type.systemBars())
            webView.setPadding(
                insets.left,
                insets.top,
                insets.right,
                insets.bottom
            )
            WindowInsetsCompat.CONSUMED
        }

        webView.settings.apply {
            javaScriptEnabled = false // Por seguridad
            loadWithOverviewMode = true
            useWideViewPort = true
            builtInZoomControls = true
            displayZoomControls = false
        }

        webView.webViewClient = object : WebViewClient() {
            override fun onReceivedError(
                view: WebView?,
                errorCode: Int,
                description: String?,
                failingUrl: String?
            ) {
                super.onReceivedError(view, errorCode, description, failingUrl)
                Toast.makeText(
                    this@PrivacyPolicyActivity,
                    "Error al cargar la política de privacidad",
                    Toast.LENGTH_SHORT
                ).show()
            }
        }

        webView.loadUrl("https://cepalabs.cl/fichatech/privacy-policy")
    }


    override fun onSupportNavigateUp(): Boolean {
        onBackPressed()
        return true
    }
}
