package com.cepalabsfree.fichatech

import android.os.Bundle
import android.webkit.WebView
import androidx.appcompat.app.AppCompatActivity

class WebViewActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_web_view)

        val webView: WebView = findViewById(R.id.webView)
        val fileName = intent.getStringExtra("file")

        if (fileName != null) {
            webView.loadUrl("file:///android_asset/$fileName")
        }
    }
}

