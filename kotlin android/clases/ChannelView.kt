package com.cepalabsfree.fichatech.audiostream

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.util.AttributeSet
import android.view.LayoutInflater
import android.view.MotionEvent
import android.view.View
import android.widget.*
import androidx.constraintlayout.widget.ConstraintLayout
import com.cepalabsfree.fichatech.R
import com.google.android.material.slider.Slider
import kotlin.math.max

/**
 * ✅ ChannelView v2.0 - API 36 Compatible
 *
 * CARACTERÍSTICAS:
 * - Sincronización bidireccional con servidor
 * - Debounce inteligente para evitar spam de red
 * - Diferenciación entre cambios locales y remotos
 * - Manejo correcto de estado ON/OFF/MUTE
 * - Compatibilidad con Edge-to-Edge y pantallas grandes
 */
class ChannelView
@JvmOverloads
constructor(context: Context, attrs: AttributeSet? = null, defStyleAttr: Int = 0) :
    ConstraintLayout(context, attrs, defStyleAttr) {

    lateinit var root: ConstraintLayout
    lateinit var channelLabel: TextView
    lateinit var powerButton: Button
    lateinit var volumeSlider: Slider
    lateinit var volumeValue: TextView
    lateinit var panSlider: Slider
    lateinit var panValue: TextView
    lateinit var muteIndicator: ImageView

    var isActive = false
        private set

    private var channelIndex: Int = 0
    private var currentGainDb = 0f
    private var currentPan = 0f

    // ✅ Flag para evitar loops de sincronización
    private var isUpdatingFromServer = false

    // Callbacks para comunicación con servidor
    var onActiveChanged: ((channel: Int, active: Boolean) -> Unit)? = null
    var onGainDbChanged: ((channel: Int, gainDb: Float) -> Unit)? = null
    var onPanChanged: ((channel: Int, pan: Float) -> Unit)? = null

    // Debounce para evitar spam al servidor
    private val mainHandler = Handler(Looper.getMainLooper())
    private var gainDebounceRunnable: Runnable? = null
    private var panDebounceRunnable: Runnable? = null
    private val DEBOUNCE_DELAY_MS = 100L // Reducido para mejor respuesta

    // Control de touch para scroll
    private var isSliderTouched = false
    private var lastSentGainDb = 0f
    private var lastSentPan = 0f

    private var thumbTouchRadius = 12f // Radio de detección del thumb (en píxeles)
    private val thumbTouchRadiusDefault = 12f
    private val thumbTouchRadiusExpanded = 36f // Puedes ajustar este valor para más o menos margen
    private var thumbTouchRadiusPan = 12f // Radio de detección del thumb de pan (en píxeles)
    private val thumbTouchRadiusPanDefault = 12f
    private val thumbTouchRadiusPanExpanded = 36f // Puedes ajustar este valor para más o menos margen

    init {
        initView(context)
    }

    fun setChannelNumber(number1Based: Int) {
        val safe = if (number1Based < 1) 1 else number1Based
        channelIndex = safe - 1
        channelLabel.text = "CH $safe"
    }

    fun getChannelIndex(): Int = channelIndex

    /**
     * ✅ Activar/Desactivar canal - Puede ser llamado desde UI o servidor
     */
    fun activateChannel(active: Boolean, fromServer: Boolean = false) {
        if (isActive == active) return

        isActive = active
        updateUIState()

        // Solo notificar si NO viene del servidor (evita loops)
        if (!fromServer && !isUpdatingFromServer) {
            onActiveChanged?.invoke(channelIndex, active)
        }
    }

    private fun initView(context: Context) {
        val inflater = LayoutInflater.from(context)
        root = inflater.inflate(R.layout.view_channelficha, this, true) as ConstraintLayout

        channelLabel = findViewById(R.id.channelLabel)
        powerButton = findViewById(R.id.powerButton)
        volumeSlider = findViewById(R.id.volumeSlider)
        volumeValue = findViewById(R.id.volumeValue)
        panSlider = findViewById(R.id.panSlider)
        panValue = findViewById(R.id.panValue)
        muteIndicator = findViewById(R.id.muteIndicator)

        volumeSlider.valueFrom = -60f
        volumeSlider.valueTo = 12f
        volumeSlider.value = 0f

        panSlider.valueFrom = -100f
        panSlider.valueTo = 100f
        panSlider.value = 0f

        updateUIState()
        setupSliderTouchHandling()

        powerButton.setOnClickListener {
            val nextActive = !isActive
            activateChannel(nextActive, fromServer = false)
        }

        volumeSlider.addOnChangeListener { _, value, fromUser ->
            if (!fromUser || isUpdatingFromServer) return@addOnChangeListener

            setGainDbInternal(value)

            // Debounce para enviar al servidor
            gainDebounceRunnable?.let { mainHandler.removeCallbacks(it) }
            gainDebounceRunnable = Runnable {
                if (kotlin.math.abs(lastSentGainDb - value) > 0.5f) {
                    lastSentGainDb = value
                    onGainDbChanged?.invoke(channelIndex, value)
                }
            }
            mainHandler.postDelayed(gainDebounceRunnable!!, DEBOUNCE_DELAY_MS)
        }

        panSlider.addOnChangeListener { _, value, fromUser ->
            if (!fromUser || isUpdatingFromServer) return@addOnChangeListener

            val panNormalized = (value / 100f).coerceIn(-1f, 1f)
            setPanValueInternal(panNormalized)

            // Debounce para enviar al servidor
            panDebounceRunnable?.let { mainHandler.removeCallbacks(it) }
            panDebounceRunnable = Runnable {
                if (kotlin.math.abs(lastSentPan - panNormalized) > 0.02f) {
                    lastSentPan = panNormalized
                    onPanChanged?.invoke(channelIndex, panNormalized)
                }
            }
            mainHandler.postDelayed(panDebounceRunnable!!, DEBOUNCE_DELAY_MS)
        }
    }

    /**
     * ✅ Establecer ganancia - Llamado desde UI o servidor
     */
    fun setGainDb(gainDb: Float, fromServer: Boolean = false) {
        if (fromServer) {
            isUpdatingFromServer = true
        }
        setGainDbInternal(gainDb)
        if (fromServer) {
            isUpdatingFromServer = false
            lastSentGainDb = gainDb
        }
    }

    private fun setGainDbInternal(gainDb: Float) {
        currentGainDb = gainDb.coerceIn(-60f, 12f)
        volumeSlider.value = currentGainDb
        volumeValue.text = String.format("%.0f dB", currentGainDb)
        muteIndicator.visibility = if (currentGainDb <= -60f) View.VISIBLE else View.GONE
    }

    fun setGainLinear(gain: Float, fromServer: Boolean = false) {
        val gainDb = 20f * kotlin.math.log10(max(gain, 0.0001f))
        setGainDb(gainDb, fromServer)
    }

    /**
     * ✅ Establecer pan - Llamado desde UI o servidor
     */
    fun setPanValue(pan: Float, fromServer: Boolean = false) {
        if (fromServer) {
            isUpdatingFromServer = true
        }
        setPanValueInternal(pan)
        if (fromServer) {
            isUpdatingFromServer = false
            lastSentPan = pan
        }
    }

    private fun setPanValueInternal(pan: Float) {
        currentPan = pan.coerceIn(-1f, 1f)
        val panPct = currentPan * 100f
        panSlider.value = panPct

        panValue.text = when {
            panPct < -90f -> "L 100%"
            panPct < -50f -> "L 75%"
            panPct < -20f -> "L 50%"
            panPct < -5f -> "L 25%"
            panPct > 90f -> "R 100%"
            panPct > 50f -> "R 75%"
            panPct > 20f -> "R 50%"
            panPct > 5f -> "R 25%"
            else -> "C"
        }
    }

    /**
     * ✅ Actualizar desde estado de servidor (sincronización completa)
     */
    fun updateFromServerState(active: Boolean, gainDb: Float? = null, pan: Float? = null) {
        isUpdatingFromServer = true

        if (isActive != active) {
            isActive = active
            updateUIState()
        }

        gainDb?.let { setGainDbInternal(it) }
        pan?.let { setPanValueInternal(it) }

        isUpdatingFromServer = false
    }

    fun updateMonitor(rms: Float, peak: Float, isActive: Boolean) {
        if (this.isActive != isActive) {
            activateChannel(isActive, fromServer = true)
        }
    }


    private fun updateUIState() {

        val backgroundColor =
            if (isActive) {

                R.color.channel_active_background
            } else {

                R.color.channel_inactive_background
            }

        val textColor =
            if (isActive) {

                R.color.channel_active_text
            } else {

                R.color.channel_inactive_text
            }

        val powerButtonColor =
            if (isActive) {

                R.color.channel_power_active
            } else {

                R.color.channel_power_inactive
            }

        root.setBackgroundResource(backgroundColor)


        powerButton.setBackgroundColor(resources.getColor(powerButtonColor, null))

        val enabled = isActive

        volumeSlider.isEnabled = enabled

        panSlider.isEnabled = enabled

        volumeValue.isEnabled = enabled

        panValue.isEnabled = enabled

        powerButton.text = if (isActive) "ON" else "OFF"
    }


    /**
     * ✅ Configura los touch listeners en los sliders SOLO para el thumb
     * - Solo permite interacción directa sobre el thumb
     * - Rechaza touches sobre el track
     * - Bloquea scroll cuando se toca el thumb
     */
    private fun setupSliderTouchHandling() {
        volumeSlider.setOnTouchListener { view, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    thumbTouchRadius = thumbTouchRadiusExpanded // Agranda el área de touch de volumen
                    if (isPointOnThumb(volumeSlider, event)) {
                        isSliderTouched = true
                        parent?.requestDisallowInterceptTouchEvent(true)
                        false
                    } else {
                        thumbTouchRadius = thumbTouchRadiusDefault
                        true
                    }
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    isSliderTouched = false
                    parent?.requestDisallowInterceptTouchEvent(false)
                    thumbTouchRadius = thumbTouchRadiusDefault // <-- Restaurar tamaño normal al soltar
                    false // Permitir que el slider procese el evento normalmente
                }
                else -> {
                    if (isSliderTouched) false else true
                }
            }
        }
        panSlider.setOnTouchListener { view, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    thumbTouchRadiusPan = thumbTouchRadiusPanExpanded // Agranda el área de touch de pan
                    if (isPointOnThumbPan(panSlider, event)) {
                        isSliderTouched = true
                        parent?.requestDisallowInterceptTouchEvent(true)
                        false
                    } else {
                        thumbTouchRadiusPan = thumbTouchRadiusPanDefault
                        true
                    }
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    isSliderTouched = false
                    parent?.requestDisallowInterceptTouchEvent(false)
                    thumbTouchRadiusPan = thumbTouchRadiusPanDefault // <-- Restaurar tamaño normal al soltar
                    false // Permitir que el slider procese el evento normalmente
                }
                else -> {
                    if (isSliderTouched) false else true
                }
            }
        }
    }

    private fun isPointOnThumb(slider: Slider, event: MotionEvent): Boolean {
        val trackPosition = slider.trackSidePadding
        val thumbX = trackPosition + ((slider.value - slider.valueFrom) / (slider.valueTo - slider.valueFrom) * (slider.width - 2 * trackPosition))
        val distance = kotlin.math.sqrt(((event.x - thumbX).pow(2)) + ((event.y - slider.height / 2f).pow(2)))
        return distance <= thumbTouchRadius
    }

    private fun isPointOnThumbPan(slider: Slider, event: MotionEvent): Boolean {
        val trackPosition = slider.trackSidePadding
        val thumbX = trackPosition + ((slider.value - slider.valueFrom) / (slider.valueTo - slider.valueFrom) * (slider.width - 2 * trackPosition))
        val distance = kotlin.math.sqrt(((event.x - thumbX).pow(2)) + ((event.y - slider.height / 2f).pow(2)))
        return distance <= thumbTouchRadiusPan
    }

    fun cleanup() {
        gainDebounceRunnable?.let { mainHandler.removeCallbacks(it) }
        panDebounceRunnable?.let { mainHandler.removeCallbacks(it) }
    }
    
    // ✅ Alias para compatibilidad con código de sincronización web
    fun setPan(pan: Float, fromServer: Boolean = false) = setPanValue(pan, fromServer)
    fun setActive(active: Boolean, fromServer: Boolean = false) = activateChannel(active, fromServer)
}