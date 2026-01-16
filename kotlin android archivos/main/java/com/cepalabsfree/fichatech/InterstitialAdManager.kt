package com.cepalabsfree.fichatech

import android.app.Activity
import android.content.Context
import android.os.Build
import androidx.annotation.RequiresApi
import com.google.android.gms.ads.AdRequest
import com.google.android.gms.ads.interstitial.InterstitialAd
import com.google.android.gms.ads.interstitial.InterstitialAdLoadCallback
import com.google.android.gms.ads.FullScreenContentCallback
import com.google.android.gms.ads.LoadAdError
import androidx.core.view.WindowInsetsCompat
import android.content.res.Configuration

class InterstitialAdManager(private val context: Context, private val adUnitId: String) {
    private var interstitialAd: InterstitialAd? = null
    private var isLoading = false
    private var loadAttempts = 0
    private val maxLoadAttempts = 3

    fun loadAd() {
        if (isLoading || interstitialAd != null) return
        isLoading = true
        android.util.Log.d("InterstitialAdManager", "Cargando anuncio intersticial")
        val adRequest = AdRequest.Builder().build()
        InterstitialAd.load(context, adUnitId, adRequest, object : InterstitialAdLoadCallback() {
            override fun onAdLoaded(ad: InterstitialAd) {
                android.util.Log.d("InterstitialAdManager", "Anuncio intersticial cargado exitosamente")
                interstitialAd = ad
                isLoading = false
                loadAttempts = 0
            }
            override fun onAdFailedToLoad(adError: LoadAdError) {
                android.util.Log.d("InterstitialAdManager", "Error al cargar anuncio intersticial: ${adError.message}")
                interstitialAd = null
                isLoading = false
                loadAttempts++
                if (loadAttempts < maxLoadAttempts) {
                    loadAd()
                }
            }
        })
    }

    @RequiresApi(Build.VERSION_CODES.R)
    fun showAdIfAvailable(activity: Activity, onAdDismissed: (() -> Unit)? = null) {
        if (interstitialAd != null) {
            android.util.Log.d("InterstitialAdManager", "Mostrando anuncio intersticial")
            val window = activity.window
            val controller = androidx.core.view.WindowCompat.getInsetsController(window, window.decorView)
            // Guardar el estado previo de barras
            val wasAppearanceLightStatusBars = controller.isAppearanceLightStatusBars
            val wasAppearanceLightNavigationBars = controller.isAppearanceLightNavigationBars
            // No cambiar setDecorFitsSystemWindows, mantener el estado de Edge-to-Edge

            interstitialAd?.fullScreenContentCallback = object : FullScreenContentCallback() {
                override fun onAdDismissedFullScreenContent() {
                    android.util.Log.d("InterstitialAdManager", "Anuncio intersticial cerrado")
                    // Restaurar estado previo
                    controller.isAppearanceLightStatusBars = wasAppearanceLightStatusBars
                    controller.isAppearanceLightNavigationBars = wasAppearanceLightNavigationBars
                    // Restaurar visibilidad de barras del sistema según orientación
                    val orientation = activity.resources.configuration.orientation
                    if (orientation == Configuration.ORIENTATION_PORTRAIT) {
                        controller.show(WindowInsetsCompat.Type.systemBars())
                    } else {
                        controller.hide(WindowInsetsCompat.Type.systemBars())
                        controller.systemBarsBehavior = androidx.core.view.WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
                    }
                    // No restaurar setDecorFitsSystemWindows, mantener Edge-to-Edge
                    interstitialAd = null
                    loadAd()
                    onAdDismissed?.invoke()
                }
                override fun onAdFailedToShowFullScreenContent(adError: com.google.android.gms.ads.AdError) {
                    android.util.Log.d("InterstitialAdManager", "Error al mostrar anuncio intersticial: ${adError.message}")
                    // Restaurar estado previo
                    controller.isAppearanceLightStatusBars = wasAppearanceLightStatusBars
                    controller.isAppearanceLightNavigationBars = wasAppearanceLightNavigationBars
                    // Restaurar visibilidad de barras del sistema según orientación
                    val orientation = activity.resources.configuration.orientation
                    if (orientation == Configuration.ORIENTATION_PORTRAIT) {
                        controller.show(WindowInsetsCompat.Type.systemBars())
                    } else {
                        controller.hide(WindowInsetsCompat.Type.systemBars())
                        controller.systemBarsBehavior = androidx.core.view.WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
                    }
                    // No restaurar setDecorFitsSystemWindows, mantener Edge-to-Edge
                    interstitialAd = null
                    loadAd()
                    onAdDismissed?.invoke()
                }
            }
            interstitialAd?.show(activity)
        } else {
            android.util.Log.d("InterstitialAdManager", "Anuncio intersticial no disponible, cargando nuevo")
            loadAd()
            onAdDismissed?.invoke()
        }
    }
}
