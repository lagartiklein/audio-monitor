package com.cepalabsfree.fichatech.audiostream







import android.content.Context



import android.util.AttributeSet



import android.view.LayoutInflater



import android.view.View



import android.widget.*



import androidx.constraintlayout.widget.ConstraintLayout



import com.cepalabsfree.fichatech.R



import com.google.android.material.slider.Slider



import kotlin.math.max







class ChannelView @JvmOverloads constructor(



    context: Context,



    attrs: AttributeSet? = null,



    defStyleAttr: Int = 0



) : ConstraintLayout(context, attrs, defStyleAttr) {







    lateinit var root: ConstraintLayout



    lateinit var channelLabel: TextView



    lateinit var powerButton: Button



    lateinit var vuMeter: ProgressBar



    lateinit var volumeSlider: Slider



    lateinit var volumeValue: TextView



    lateinit var panSlider: Slider



    lateinit var panValue: TextView



    lateinit var peakIndicator: View



    lateinit var muteIndicator: ImageView







    var isActive = false



    private var currentGainDb = 0f



    private var currentPan = 0f



    private var peakLevel = 0f







    init {



        initView(context)



    }







    private fun initView(context: Context) {



        val inflater = LayoutInflater.from(context)



        root = inflater.inflate(R.layout.view_channelficha, this, true) as ConstraintLayout







        channelLabel = findViewById(R.id.channelLabel)



        powerButton = findViewById(R.id.powerButton)



        vuMeter = findViewById(R.id.vuMeter)



        volumeSlider = findViewById(R.id.volumeSlider)



        volumeValue = findViewById(R.id.volumeValue)



        panSlider = findViewById(R.id.panSlider)



        panValue = findViewById(R.id.panValue)



        peakIndicator = findViewById(R.id.peakIndicator)



        muteIndicator = findViewById(R.id.muteIndicator)







        volumeSlider.valueFrom = -60f



        volumeSlider.valueTo = 12f



        volumeSlider.value = 0f







        panSlider.valueFrom = -100f



        panSlider.valueTo = 100f



        panSlider.value = 0f







        updateUIState()



        setupPeakIndicator()



    }







    fun setChannelNumber(number: Int) {



        channelLabel.text = "CH $number"



    }







    fun activateChannel(active: Boolean) {



        isActive = active



        updateUIState()







        if (!active) {



            resetVUMeter()



        }



    }







    fun setGainDb(gainDb: Float) {



        currentGainDb = gainDb



        volumeSlider.value = gainDb



        volumeValue.text = String.format("%.0f dB", gainDb)



        muteIndicator.visibility = if (gainDb <= -60f) View.VISIBLE else View.GONE



    }







    fun setGainLinear(gain: Float) {



        val gainDb = 20f * kotlin.math.log10(max(gain, 0.0001f))



        setGainDb(gainDb)



    }







    fun setPanValue(pan: Float) {



        currentPan = pan



        panSlider.value = pan







        val panText = when {



            pan < -90f -> "L 100%"



            pan < -50f -> "L 75%"



            pan < -20f -> "L 50%"



            pan < -5f -> "L 25%"



            pan > 5f -> "R 25%"



            pan > 20f -> "R 50%"



            pan > 50f -> "R 75%"



            pan > 90f -> "R 100%"



            else -> "C"



        }



        panValue.text = panText



    }







    fun updateMonitor(rms: Float, peak: Float, isActive: Boolean) {



        updateVUMeter(rms)



        if (peak > 0f) {



            showPeakIndicator()



        }



        activateChannel(isActive)



    }







    fun updateVUMeter(rms: Float) {



        val rmsDb = if (rms > 0f) {



            max(-60f, 20f * kotlin.math.log10(rms))



        } else {



            -60f



        }







        val percentage = ((rmsDb + 60f) / 60f * 100f).coerceIn(0f, 100f)



        vuMeter.progress = percentage.toInt()







        if (rms > peakLevel) {



            peakLevel = rms



            showPeakIndicator()



        }







        updateVUMeterColor(percentage)



    }







    fun resetVUMeter() {



        vuMeter.progress = 0



        peakLevel = 0f



        peakIndicator.alpha = 0f



        updateVUMeterColor(0f)



    }







    private fun updateUIState() {



        val backgroundColor = if (isActive) {



            R.color.channel_active_background



        } else {



            R.color.channel_inactive_background



        }







        val textColor = if (isActive) {



            R.color.channel_active_text



        } else {



            R.color.channel_inactive_text



        }







        val powerButtonColor = if (isActive) {



            R.color.channel_power_active



        } else {



            R.color.channel_power_inactive



        }







        root.setBackgroundResource(backgroundColor)



        channelLabel.setTextColor(resources.getColor(textColor, null))



        powerButton.setBackgroundColor(resources.getColor(powerButtonColor, null))







        val enabled = isActive



        volumeSlider.isEnabled = enabled



        panSlider.isEnabled = enabled



        volumeValue.isEnabled = enabled



        panValue.isEnabled = enabled







        powerButton.text = if (isActive) "ON" else "OFF"



    }







    private fun updateVUMeterColor(level: Float) {



        val color = when {



            level > 90f -> R.color.vu_red



            level > 70f -> R.color.vu_yellow



            level > 30f -> R.color.vu_green



            else -> R.color.vu_blue



        }







        vuMeter.progressTintList = android.content.res.ColorStateList.valueOf(



            resources.getColor(color, null)



        )



    }







    private fun setupPeakIndicator() {



        peakIndicator.alpha = 0f



    }







    fun showPeakIndicator() {



        peakIndicator.animate()



            .alpha(1f)



            .setDuration(100)



            .withEndAction {



                peakIndicator.animate()



                    .alpha(0f)



                    .setDuration(500)



                    .startDelay = 1000



            }



            .start()



    }








}