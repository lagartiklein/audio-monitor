package com.cepalabsfree.fichatech

import android.app.Activity
import android.content.Context
import com.google.android.gms.ads.AdRequest
import com.google.android.gms.ads.interstitial.InterstitialAd
import com.google.android.gms.ads.interstitial.InterstitialAdLoadCallback
import com.google.android.gms.ads.FullScreenContentCallback
import com.google.android.gms.ads.LoadAdError

class InterstitialAdManager(private val context: Context, private val adUnitId: String) {
    private var interstitialAd: InterstitialAd? = null
    private var isLoading = false
    private var loadAttempts = 0
    private val maxLoadAttempts = 3

    fun loadAd() {
        if (isLoading || interstitialAd != null) return
        isLoading = true
        val adRequest = AdRequest.Builder().build()
        InterstitialAd.load(context, adUnitId, adRequest, object : InterstitialAdLoadCallback() {
            override fun onAdLoaded(ad: InterstitialAd) {
                interstitialAd = ad
                isLoading = false
                loadAttempts = 0
            }
            override fun onAdFailedToLoad(adError: LoadAdError) {
                interstitialAd = null
                isLoading = false
                loadAttempts++
                if (loadAttempts < maxLoadAttempts) {
                    loadAd()
                }
            }
        })
    }

    fun showAdIfAvailable(activity: Activity, onAdDismissed: (() -> Unit)? = null) {
        if (interstitialAd != null) {
            interstitialAd?.fullScreenContentCallback = object : FullScreenContentCallback() {
                override fun onAdDismissedFullScreenContent() {
                    interstitialAd = null
                    loadAd()
                    onAdDismissed?.invoke()
                }
                override fun onAdFailedToShowFullScreenContent(adError: com.google.android.gms.ads.AdError) {
                    interstitialAd = null
                    loadAd()
                    onAdDismissed?.invoke()
                }
            }
            interstitialAd?.show(activity)
        } else {
            loadAd()
            onAdDismissed?.invoke()
        }
    }
}

