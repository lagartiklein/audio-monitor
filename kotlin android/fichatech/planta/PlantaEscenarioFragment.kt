package com.cepalabsfree.fichatech.planta

import android.annotation.SuppressLint
import android.content.res.Configuration
import kotlinx.parcelize.Parcelize
import android.content.ClipData
import android.content.ContentValues
import android.content.Context
import android.graphics.BlendMode
import android.graphics.BlendModeColorFilter
import android.graphics.Color
import android.graphics.PorterDuff
import android.graphics.Rect
import android.media.MediaPlayer
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Parcelable
import android.util.Log
import android.view.DragEvent
import android.view.Gravity
import android.view.LayoutInflater
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.text.InputType
import android.text.Editable
import android.text.TextWatcher
import android.widget.FrameLayout
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.fragment.app.Fragment
import androidx.recyclerview.widget.RecyclerView
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.GridLayoutManager
import com.google.android.material.textfield.TextInputEditText
import com.google.android.material.card.MaterialCardView
import com.google.android.material.slider.Slider
import com.cepalabsfree.fichatech.R
import kotlin.math.min
import kotlin.math.max

class PlantaEscenarioFragment : Fragment() {

    private lateinit var escenarioImageView: ImageView
    private lateinit var elementContainer: FrameLayout
    private lateinit var btnAddElement: ImageButton
    private lateinit var databaseHelper: PlantaEscenarioDatabaseHelper
    private var savedSceneName: String? = null

    private var screenWidth: Float = 0f
    private var screenHeight: Float = 0f

    // Variable para el elemento actualmente seleccionado
    private var selectedElement: ImageView? = null
    private var currentDialog: AlertDialog? = null

    // Cache para iconos frecuentes
    private val iconCache = mutableMapOf<String, Int>()

    private data class ScreenDimensions(val width: Float, val height: Float)

    private var cachedScreenDimensions: ScreenDimensions? = null
    private var cachedImageRect: Rect? = null

    private var selectedBackgroundUri: Uri? = null
    private var tempElementsData: ArrayList<ElementData>? = null
    private var isSoundEnabled: Boolean = true

    @Parcelize
    private data class ElementData(
        val iconName: String,
        val xRel: Float,
        val yRel: Float,
        val scale: Float,
        val rotation: Float,
        val width: Int,
        val height: Int
    ) : Parcelable

    companion object {
        private const val BASE_IMAGE_WIDTH = 740f
        private const val BASE_IMAGE_HEIGHT = 415f
    }

    private fun getScreenDimensions(): ScreenDimensions {
        return cachedScreenDimensions ?: run {
            val displayMetrics = resources.displayMetrics
            ScreenDimensions(
                width = displayMetrics.widthPixels.toFloat(),
                height = displayMetrics.heightPixels.toFloat()
            ).also { cachedScreenDimensions = it }
        }
    }

    private fun getImageRect(): Rect {
        return cachedImageRect ?: run {
            val drawable = escenarioImageView.drawable ?: return Rect(
                0,
                0,
                screenWidth.toInt(),
                screenHeight.toInt()
            )

            val viewWidth = escenarioImageView.width.toFloat()
            val viewHeight = escenarioImageView.height.toFloat()

            if (viewWidth == 0f || viewHeight == 0f) {
                return Rect(0, 0, screenWidth.toInt(), screenHeight.toInt())
            }

            val imageWidth = drawable.intrinsicWidth.toFloat()
            val imageHeight = drawable.intrinsicHeight.toFloat()

            val scale = min(viewWidth / imageWidth, viewHeight / imageHeight)
            val scaledWidth = imageWidth * scale
            val scaledHeight = imageHeight * scale

            val left = ((viewWidth - scaledWidth) / 2).toInt()
            val top = ((viewHeight - scaledHeight) / 2).toInt()
            val right = left + scaledWidth.toInt()
            val bottom = top + scaledHeight.toInt()

            Rect(left, top, right, bottom).also { cachedImageRect = it }
        }
    }

    private fun getBaseImageDimensions(): Pair<Float, Float> {
        return Pair(BASE_IMAGE_WIDTH, BASE_IMAGE_HEIGHT)
    }

    private fun calculatePositionFromBase(
        xRel: Float,
        yRel: Float,
        elementWidth: Int,
        elementHeight: Int
    ): Pair<Int, Int> {
        val imageRect = getImageRect()

        if (imageRect.width() <= 0 || imageRect.height() <= 0) {
            val centerX = (screenWidth / 2 - elementWidth / 2).toInt()
            val centerY = (screenHeight / 2 - elementHeight / 2).toInt()
            return Pair(centerX, centerY)
        }

        val scaleX = imageRect.width() / BASE_IMAGE_WIDTH
        val scaleY = imageRect.height() / BASE_IMAGE_HEIGHT
        val scale = min(scaleX, scaleY)

        val scaledBaseWidth = BASE_IMAGE_WIDTH * scale
        val scaledBaseHeight = BASE_IMAGE_HEIGHT * scale
        val offsetX = ((imageRect.width() - scaledBaseWidth) / 2).toInt()
        val offsetY = ((imageRect.height() - scaledBaseHeight) / 2).toInt()

        val leftMargin =
            imageRect.left + offsetX + (xRel * scaledBaseWidth).toInt() - elementWidth / 2
        val topMargin =
            imageRect.top + offsetY + (yRel * scaledBaseHeight).toInt() - elementHeight / 2

        return Pair(leftMargin, topMargin)
    }

    @SuppressLint("MissingInflatedId")
    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View? {
        val view = inflater.inflate(R.layout.fragment_planta_escenario, container, false)

        escenarioImageView = view.findViewById(R.id.escenarioImageView)
        elementContainer = view.findViewById(R.id.elementContainer)
        btnAddElement = view.findViewById(R.id.btnAddElement)
        val btnEscena = view.findViewById<ImageButton>(R.id.btnEscena)
        val btnToggleSound = view.findViewById<ImageButton>(R.id.btnToggleSound)

        databaseHelper = PlantaEscenarioDatabaseHelper(requireContext())

        btnToggleSound.setOnClickListener {
            isSoundEnabled = !isSoundEnabled
            btnToggleSound.setImageResource(
                if (isSoundEnabled) R.drawable.ic_toggle_sound_modern
                else R.drawable.ic_toggle_sound_mute
            )
            Toast.makeText(
                requireContext(),
                if (isSoundEnabled) "Sonido activado" else "Sonido desactivado",
                Toast.LENGTH_SHORT
            ).show()
        }

        btnAddElement.setOnClickListener { showCategorySelectionDialog() }
        btnEscena.setOnClickListener { showEscenaOptionsDialog() }

        elementContainer.setOnDragListener { v, event -> handleDragEvent(v, event) }

        val displayMetrics = resources.displayMetrics
        screenWidth = displayMetrics.widthPixels.toFloat()
        screenHeight = displayMetrics.heightPixels.toFloat()

        return view
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        val displayMetrics = resources.displayMetrics
        screenWidth = displayMetrics.widthPixels.toFloat()
        screenHeight = displayMetrics.heightPixels.toFloat()

        savedInstanceState?.let { bundle ->
            savedSceneName = bundle.getString("SAVED_SCENE_NAME")
            isSoundEnabled = bundle.getBoolean("SOUND_ENABLED", true)
            selectedBackgroundUri = bundle.getString("BACKGROUND_URI")?.let { Uri.parse(it) }
            tempElementsData = bundle.getParcelableArrayList<ElementData>("TEMP_ELEMENTS_DATA")
        }

        val btnToggleSound = view.findViewById<ImageButton>(R.id.btnToggleSound)
        btnToggleSound?.setImageResource(
            if (isSoundEnabled) R.drawable.ic_toggle_sound_modern
            else R.drawable.ic_toggle_sound_mute
        )

        view.post {
            val dimensions = getScreenDimensions()
            screenWidth = dimensions.width
            screenHeight = dimensions.height

            cachedImageRect = null

            tempElementsData?.let { elementsData ->
                restoreElementsFromData(elementsData)
                tempElementsData = null
            }

            if (savedInstanceState != null) {
                repositionAllElements()
            }
        }
    }




    // Continuación de PlantaEscenarioFragment.kt

    // NUEVA FUNCIÓN: Seleccionar elemento y mostrar diálogo
    private fun selectElement(element: ImageView) {
        // Deseleccionar elemento anterior
        selectedElement?.let { clearSelection(it) }

        // Seleccionar nuevo elemento
        selectedElement = element
        applySelection(element)

        // Mostrar diálogo de opciones
        showElementOptionsDialog(element)
    }

    // NUEVA FUNCIÓN: Aplicar efecto visual de selección
    private fun applySelection(element: ImageView) {
        // Aplicar brillo (tint blanco con transparencia)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            element.colorFilter =
                BlendModeColorFilter(Color.argb(100, 255, 255, 255), BlendMode.SRC_ATOP)
        } else {
            @Suppress("DEPRECATION")
            element.setColorFilter(Color.argb(100, 255, 255, 255), PorterDuff.Mode.SRC_ATOP)
        }
    }

    // NUEVA FUNCIÓN: Limpiar selección visual
    private fun clearSelection(element: ImageView) {
        element.colorFilter = null
    }

    private fun showElementOptionsDialog(element: ImageView) {
        currentDialog?.dismiss()

        val dialogView =
            LayoutInflater.from(requireContext()).inflate(R.layout.dialog_element_options, null)

        val scaleSlider = dialogView.findViewById<Slider>(R.id.scaleSlider)
        val scaleValueText = dialogView.findViewById<TextView>(R.id.scaleValueText)
        val rotationSlider = dialogView.findViewById<Slider>(R.id.rotationSlider)
        val rotationValueText = dialogView.findViewById<TextView>(R.id.rotationValueText)
        val btnDelete = dialogView.findViewById<Button>(R.id.btnDelete)
        val btnClose = dialogView.findViewById<Button>(R.id.btnClose)

        // Redondear el valor de escala a múltiplos de 0.01
        val roundedScale = (Math.round(element.scaleX * 100.0) / 100.0).toFloat()
        val roundedRotation = Math.round(element.rotation).toFloat()

        // ✅ IMPORTANTE: Limitar la escala al rango del slider (0.5 a 2.0)
        val sliderValue = roundedScale.coerceIn(0.5f, 2.0f)

        scaleSlider.value = sliderValue
        scaleValueText.text = "${(roundedScale * 100).toInt()}%"
        rotationSlider.value = roundedRotation
        rotationValueText.text = "${roundedRotation.toInt()}°"

        // ✅ SLIDER ACTUALIZA ESCALA Y GUARDA EN TAGS
        scaleSlider.addOnChangeListener { _, value, _ ->
            element.scaleX = value
            element.scaleY = value
            // ✅ GUARDAR LA NUEVA ESCALA EN LOS TAGS
            element.setTag(R.id.original_scale_x, value)
            element.setTag(R.id.original_scale_y, value)
            scaleValueText.text = "${(value * 100).toInt()}%"
        }

        rotationSlider.addOnChangeListener { _, value, _ ->
            element.rotation = value
            rotationValueText.text = "${value.toInt()}°"
        }

        btnDelete.setOnClickListener {
            elementContainer.removeView(element)
            currentDialog?.dismiss()
            currentDialog = null
            selectedElement = null
            Toast.makeText(requireContext(), "Elemento eliminado", Toast.LENGTH_SHORT).show()
        }

        btnClose.setOnClickListener {
            clearSelection(element)
            selectedElement = null
            currentDialog?.dismiss()
            currentDialog = null
        }

        val builder = AlertDialog.Builder(requireContext())
        builder.setView(dialogView)
        builder.setCancelable(true)
        builder.setOnCancelListener {
            clearSelection(element)
            selectedElement = null
            currentDialog = null
        }

        currentDialog = builder.create()

        currentDialog?.show()
        currentDialog?.window?.let { window ->
            val elementLocation = IntArray(2)
            element.getLocationOnScreen(elementLocation)
            val elementX = elementLocation[0]
            val elementY = elementLocation[1]
            val elementCenterY = elementY + element.height / 2

            val screenHeight = resources.displayMetrics.heightPixels
            val screenWidth = resources.displayMetrics.widthPixels

            val dialogHeight = 280
            val dialogWidth = 240

            val safeMargin = 20

            val params = window.attributes

            if (elementCenterY < screenHeight / 2) {
                params.gravity = Gravity.TOP or Gravity.START
                params.y = elementY + element.height + safeMargin
            } else {
                params.gravity = Gravity.TOP or Gravity.START
                params.y = (elementY - dialogHeight - safeMargin).coerceAtLeast(safeMargin)
            }

            val elementCenterX = elementX + element.width / 2
            val desiredX = elementCenterX - dialogWidth / 2

            params.x = desiredX.coerceIn(safeMargin, screenWidth - dialogWidth - safeMargin)

            window.attributes = params
        }
    }

    private fun saveElementsToTempData(): ArrayList<ElementData> {
        val elementsData = ArrayList<ElementData>()

        if (!this::elementContainer.isInitialized) {
            return elementsData
        }

        for (i in 0 until elementContainer.childCount) {
            val element = elementContainer.getChildAt(i) as? ImageView ?: continue
            val layoutParams = element.layoutParams as? FrameLayout.LayoutParams ?: continue

            val iconName = element.contentDescription?.toString() ?: continue

            val xRel = element.getTag(R.id.pos_x_rel) as? Float ?: 0.5f
            val yRel = element.getTag(R.id.pos_y_rel) as? Float ?: 0.5f

            elementsData.add(
                ElementData(
                    iconName = iconName,
                    xRel = xRel,
                    yRel = yRel,
                    scale = element.scaleX,
                    rotation = element.rotation,
                    width = layoutParams.width,
                    height = layoutParams.height
                )
            )
        }

        return elementsData
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)

        outState.putString("SAVED_SCENE_NAME", savedSceneName)
        outState.putBoolean("SOUND_ENABLED", isSoundEnabled)
        selectedBackgroundUri?.let { outState.putString("BACKGROUND_URI", it.toString()) }

        if (this::elementContainer.isInitialized && this::escenarioImageView.isInitialized) {
            if (elementContainer.childCount > 0) {
                outState.putParcelableArrayList("TEMP_ELEMENTS_DATA", saveElementsToTempData())
            }
        }
    }

    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)

        cachedScreenDimensions = null
        cachedImageRect = null

        val dimensions = getScreenDimensions()
        screenWidth = dimensions.width
        screenHeight = dimensions.height

        escenarioImageView.post {
            cachedImageRect = null
            getImageRect()
            repositionAllElements()
        }
    }

    private fun repositionAllElements() {
        elementContainer.post {
            val imageRect = getImageRect()

            for (i in 0 until elementContainer.childCount) {
                val element = elementContainer.getChildAt(i) as? ImageView ?: continue
                element.updatePositionFromRelative(imageRect)
            }

            elementContainer.invalidate()
            elementContainer.requestLayout()
        }
    }

    override fun onDestroyView() {
        super.onDestroyView()

        currentDialog?.dismiss()
        currentDialog = null
        selectedElement = null

        iconCache.clear()
        cachedScreenDimensions = null
        cachedImageRect = null

        elementContainer.setOnDragListener(null)
        escenarioImageView.setImageDrawable(null)
    }

    private fun isFragmentActive(): Boolean {
        return isAdded && !isDetached && activity != null && view != null
    }

    private fun safeContext(): Context? {
        return if (isFragmentActive()) requireContext() else null
    }

    private fun showEscenaOptionsDialog() {
        safeContext()?.let { context ->
            val options =
                arrayOf(getString(R.string.guardar_planta), getString(R.string.cargar_planta))
            val builder = AlertDialog.Builder(context)
            builder.setTitle(getString(R.string.opciones_planta_title))
            builder.setItems(options) { dialog, which ->
                when (which) {
                    0 -> showSaveSceneDialog()
                    1 -> showLoadSceneDialog()
                }
            }
            builder.show()
        }
    }

    private fun showCategorySelectionDialog() {
        val dialogView =
            LayoutInflater.from(requireContext()).inflate(R.layout.dialog_category_selector, null)
        val recyclerView = dialogView.findViewById<RecyclerView>(R.id.categoryRecyclerView)

        val categories = listOf(
            CategoryItem("Instrumentos", R.drawable.bateria1),
            CategoryItem("Electricidad", R.drawable.alargador1),
            CategoryItem("Monitores", R.drawable.array1),
            CategoryItem("Mezcla", R.drawable.mezcla1)
        )

        val builder = AlertDialog.Builder(requireContext())
        builder.setTitle(R.string.select_category)
        builder.setView(dialogView)
        builder.setNegativeButton(getString(R.string.cancelar), null)
        val dialog = builder.create()

        recyclerView.layoutManager = GridLayoutManager(requireContext(), 2)
        recyclerView.adapter = CategorySelectorAdapter(categories) { selectedCategory ->
            dialog.dismiss()
            if (selectedCategory == "Instrumentos") {
                showInstrumentSubcategoryDialog()
            } else {
                showIconSelectionDialog(selectedCategory)
            }
        }

        dialog.show()
    }

    private fun showInstrumentSubcategoryDialog() {
        val dialogView =
            LayoutInflater.from(requireContext()).inflate(R.layout.dialog_category_selector, null)
        val recyclerView = dialogView.findViewById<RecyclerView>(R.id.categoryRecyclerView)

        val subcategories = listOf(
            CategoryItem("Baterias y Percusión", R.drawable.congas2),
            CategoryItem("Cuerdas y Sintetizadores", R.drawable.guitarraleectrica1),
            CategoryItem("Vientos y Similar", R.drawable.saxo),
            CategoryItem("Voces y Otros", R.drawable.microfono5)
        )

        val builder = AlertDialog.Builder(requireContext())
        builder.setTitle(getString(R.string.seleccionar_subcategoria_instrumentos))
        builder.setView(dialogView)
        builder.setNegativeButton(getString(R.string.cancelar), null)
        val dialog = builder.create()

        recyclerView.layoutManager = GridLayoutManager(requireContext(), 2)
        recyclerView.adapter = CategorySelectorAdapter(subcategories) { selectedSubcategory ->
            dialog.dismiss()
            showIconSelectionDialog(selectedSubcategory)
        }

        dialog.show()
    }

    private fun showIconSelectionDialog(selectedCategory: String) {
        val dialogView =
            LayoutInflater.from(requireContext()).inflate(R.layout.dialog_icon_selector, null)
        val recyclerView = dialogView.findViewById<RecyclerView>(R.id.iconRecyclerView)
        val searchEditText = dialogView.findViewById<TextInputEditText>(R.id.searchEditText)

        val iconNames = getIconsForCategory(selectedCategory)
        val iconItems = iconNames.map { name ->
            IconItem(name, getIconResource(name))
        }

        val builder = AlertDialog.Builder(requireContext())
        builder.setTitle(R.string.select_instrument)
        builder.setView(dialogView)
        builder.setNegativeButton("Cancelar", null)
        val dialog = builder.create()

        val adapter = IconSelectorAdapter(iconItems) { selectedIcon ->
            dialog.dismiss()
            addElement(selectedIcon)
        }

        recyclerView.layoutManager = LinearLayoutManager(requireContext())
        recyclerView.adapter = adapter

        searchEditText?.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                adapter.filter(s?.toString() ?: "")
            }

            override fun afterTextChanged(s: Editable?) {}
        })

        dialog.show()
    }

    // Continúa con las funciones de iconos y categorías...
    // (getIconsForCategory, getSoundResource, getIconResource, etc. - sin cambios)

    // ============================================================
// 1. FUNCIÓN: restoreElementsFromData (CORREGIDA)
// ============================================================
    private fun restoreElementsFromData(elementsData: ArrayList<ElementData>) {
        elementContainer.removeAllViews()

        for (elementData in elementsData) {
            val newElement = ImageView(requireContext()).apply {
                setImageResource(getIconResource(elementData.iconName))
                layoutParams = FrameLayout.LayoutParams(elementData.width, elementData.height).apply {
                }
                setTag(R.id.pos_x_rel, elementData.xRel)
                setTag(R.id.pos_y_rel, elementData.yRel)
                scaleX = elementData.scale
                scaleY = elementData.scale
                rotation = elementData.rotation
                contentDescription = elementData.iconName

                // ✅ PASO 1: GUARDAR ESCALA ORIGINAL EN TAGS
                setTag(R.id.original_scale_x, elementData.scale)
                setTag(R.id.original_scale_y, elementData.scale)

                setOnTouchListener { v, event ->
                    when (event.action) {
                        MotionEvent.ACTION_DOWN -> {
                            v.performClick()
                            v.setTag(R.id.touch_start_time, System.currentTimeMillis())

                            // ✅ PASO 2: OBTENER ESCALA DEL TAG, NO DE VARIABLE LOCAL
                            val originalScaleX = v.getTag(R.id.original_scale_x) as? Float ?: 1.0f
                            val originalScaleY = v.getTag(R.id.original_scale_y) as? Float ?: 1.0f

                            // Animación de pulso al tocar
                            v.animate()
                                .scaleX(originalScaleX * 1.1f)
                                .scaleY(originalScaleY * 1.1f)
                                .setDuration(100)
                                .start()

                            true
                        }

                        MotionEvent.ACTION_MOVE -> {
                            val startTime = v.getTag(R.id.touch_start_time) as? Long ?: return@setOnTouchListener false
                            val holdDuration = System.currentTimeMillis() - startTime

                            if (holdDuration > 300) {
                                v.animate().cancel()

                                // ✅ PASO 3: RESTAURAR A ESCALA DEL TAG
                                val originalScaleX = v.getTag(R.id.original_scale_x) as? Float ?: 1.0f
                                val originalScaleY = v.getTag(R.id.original_scale_y) as? Float ?: 1.0f
                                v.scaleX = originalScaleX
                                v.scaleY = originalScaleY

                                val data = ClipData.newPlainText("", "")
                                val shadowBuilder = View.DragShadowBuilder(v)
                                v.startDragAndDrop(data, shadowBuilder, v, 0)

                                return@setOnTouchListener true
                            }
                            false
                        }

                        MotionEvent.ACTION_UP -> {
                            val startTime = v.getTag(R.id.touch_start_time) as? Long ?: return@setOnTouchListener false
                            val holdDuration = System.currentTimeMillis() - startTime

                            // ✅ PASO 4: MANTENER ESCALA ACTUAL (que puede ser editada por slider)
                            val currentScaleX = v.scaleX
                            val currentScaleY = v.scaleY

                            v.animate()
                                .scaleX(currentScaleX)
                                .scaleY(currentScaleY)
                                .alpha(1.0f)
                                .setDuration(100)
                                .withEndAction {
                                    v.scaleX = (Math.round(v.scaleX * 100.0) / 100.0).toFloat()
                                    v.scaleY = (Math.round(v.scaleY * 100.0) / 100.0).toFloat()
                                    // ✅ PASO 5: GUARDAR NUEVA ESCALA EN TAG
                                    v.setTag(R.id.original_scale_x, v.scaleX)
                                    v.setTag(R.id.original_scale_y, v.scaleY)
                                }
                                .start()

                            if (holdDuration < 300) {
                                selectElement(v as ImageView)
                            }
                            true
                        }

                        MotionEvent.ACTION_CANCEL -> {
                            val currentScaleX = v.scaleX
                            val currentScaleY = v.scaleY

                            v.animate()
                                .scaleX(currentScaleX)
                                .scaleY(currentScaleY)
                                .alpha(1.0f)
                                .setDuration(100)
                                .withEndAction {
                                    v.scaleX = (Math.round(v.scaleX * 100.0) / 100.0).toFloat()
                                    v.scaleY = (Math.round(v.scaleY * 100.0) / 100.0).toFloat()
                                    // ✅ PASO 5: GUARDAR NUEVA ESCALA EN TAG
                                    v.setTag(R.id.original_scale_x, v.scaleX)
                                    v.setTag(R.id.original_scale_y, v.scaleY)
                                }
                                .start()
                            true
                        }

                        else -> false
                    }
                }
            }
            elementContainer.addView(newElement)
        }

        repositionAllElements()
    }

    // ============================================================
// 2. FUNCIÓN: addElement (CORREGIDA)
// ============================================================
    private fun addElement(selectedIcon: String) {
        val centerXRel = 0.5f
        val centerYRel = 0.5f

        val elementWidth = 300
        val elementHeight = 300

        val (leftMargin, topMargin) = calculatePositionFromBase(
            centerXRel,
            centerYRel,
            elementWidth,
            elementHeight
        )

        val newElement = ImageView(requireContext()).apply {
            setImageResource(getIconResource(selectedIcon))
            layoutParams = FrameLayout.LayoutParams(elementWidth, elementHeight).apply {
                this.leftMargin = leftMargin
                this.topMargin = topMargin
            }
            setTag(R.id.pos_x_rel, centerXRel)
            setTag(R.id.pos_y_rel, centerYRel)
            contentDescription = selectedIcon

            // ✅ PASO 1: GUARDAR ESCALA ORIGINAL EN TAGS (escala inicial = 1.0f)
            setTag(R.id.original_scale_x, 1.0f)
            setTag(R.id.original_scale_y, 1.0f)

            setOnTouchListener { v, event ->
                when (event.action) {
                    MotionEvent.ACTION_DOWN -> {
                        v.performClick()
                        v.setTag(R.id.touch_start_time, System.currentTimeMillis())

                        // ✅ PASO 2: OBTENER ESCALA DEL TAG
                        val originalScaleX = v.getTag(R.id.original_scale_x) as? Float ?: 1.0f
                        val originalScaleY = v.getTag(R.id.original_scale_y) as? Float ?: 1.0f

                        // Animación de pulso al tocar
                        v.animate()
                            .scaleX(originalScaleX * 1.1f)
                            .scaleY(originalScaleY * 1.1f)
                            .setDuration(100)
                            .start()

                        true
                    }

                    MotionEvent.ACTION_MOVE -> {
                        val startTime = v.getTag(R.id.touch_start_time) as? Long ?: return@setOnTouchListener false
                        val holdDuration = System.currentTimeMillis() - startTime

                        if (holdDuration > 300) {
                            v.animate().cancel()

                            // ✅ PASO 3: RESTAURAR A ESCALA DEL TAG
                            val originalScaleX = v.getTag(R.id.original_scale_x) as? Float ?: 1.0f
                            val originalScaleY = v.getTag(R.id.original_scale_y) as? Float ?: 1.0f
                            v.scaleX = originalScaleX
                            v.scaleY = originalScaleY

                            val data = ClipData.newPlainText("", "")
                            val shadowBuilder = View.DragShadowBuilder(v)
                            v.startDragAndDrop(data, shadowBuilder, v, 0)

                            return@setOnTouchListener true
                        }
                        false
                    }

                    MotionEvent.ACTION_UP -> {
                        val startTime = v.getTag(R.id.touch_start_time) as? Long ?: return@setOnTouchListener false
                        val holdDuration = System.currentTimeMillis() - startTime

                        // ✅ PASO 4: MANTENER ESCALA ACTUAL
                        val currentScaleX = v.scaleX
                        val currentScaleY = v.scaleY

                        v.animate()
                            .scaleX(currentScaleX)
                            .scaleY(currentScaleY)
                            .alpha(1.0f)
                            .setDuration(100)
                            .withEndAction {
                                v.scaleX = (Math.round(v.scaleX * 100.0) / 100.0).toFloat()
                                v.scaleY = (Math.round(v.scaleY * 100.0) / 100.0).toFloat()
                                // ✅ PASO 5: GUARDAR NUEVA ESCALA EN TAG
                                v.setTag(R.id.original_scale_x, v.scaleX)
                                v.setTag(R.id.original_scale_y, v.scaleY)
                            }
                            .start()

                        if (holdDuration < 300) {
                            selectElement(v as ImageView)
                        }
                        true
                    }

                    MotionEvent.ACTION_CANCEL -> {
                        val currentScaleX = v.scaleX
                        val currentScaleY = v.scaleY

                        v.animate()
                            .scaleX(currentScaleX)
                            .scaleY(currentScaleY)
                            .alpha(1.0f)
                            .setDuration(100)
                            .start()
                        true
                    }

                    else -> false
                }
            }
        }
        elementContainer.addView(newElement)
        playIconSound(selectedIcon)
    }

    private fun handleDragEvent(v: View, event: DragEvent): Boolean {
        when (event.action) {
            DragEvent.ACTION_DRAG_STARTED -> {
                val draggedView = event.localState as? View
                draggedView?.let {
                    // Guardar la escala original antes de arrastrar
                    it.setTag(R.id.original_scale_x, it.scaleX)
                    it.setTag(R.id.original_scale_y, it.scaleY)
                    // Hacer semi-transparente mientras se arrastra
                    it.alpha = 0.3f
                }
                return true
            }

            DragEvent.ACTION_DRAG_ENTERED -> {
                return true
            }

            DragEvent.ACTION_DRAG_EXITED -> {
                return true
            }

            DragEvent.ACTION_DRAG_LOCATION -> {
                return true
            }

            DragEvent.ACTION_DROP -> {
                val view = event.localState as View
                val x = event.x.toInt()
                val y = event.y.toInt()

                // Recuperar la escala original
                val originalScaleX = view.getTag(R.id.original_scale_x) as? Float ?: 1.0f
                val originalScaleY = view.getTag(R.id.original_scale_y) as? Float ?: 1.0f

                val imageRect = getImageRect()

                if (x >= imageRect.left && x <= imageRect.right && y >= imageRect.top && y <= imageRect.bottom) {
                    val scaleX = imageRect.width() / BASE_IMAGE_WIDTH
                    val scaleY = imageRect.height() / BASE_IMAGE_HEIGHT
                    val scale = min(scaleX, scaleY)

                    val scaledBaseWidth = BASE_IMAGE_WIDTH * scale
                    val scaledBaseHeight = BASE_IMAGE_HEIGHT * scale
                    val offsetX = (imageRect.width() - scaledBaseWidth) / 2
                    val offsetY = (imageRect.height() - scaledBaseHeight) / 2

                    val relativeX = (x - imageRect.left - offsetX).toFloat()
                    val relativeY = (y - imageRect.top - offsetY).toFloat()

                    val xRel = (relativeX / scaledBaseWidth).coerceIn(0f, 1f)
                    val yRel = (relativeY / scaledBaseHeight).coerceIn(0f, 1f)

                    val (leftMargin, topMargin) = calculatePositionFromBase(
                        xRel, yRel, view.width, view.height
                    )

                    val layoutParams = view.layoutParams as ViewGroup.MarginLayoutParams
                    layoutParams.leftMargin = leftMargin
                    layoutParams.topMargin = topMargin

                    view.setTag(R.id.pos_x_rel, xRel)
                    view.setTag(R.id.pos_y_rel, yRel)

                    view.layoutParams = layoutParams

                    // Animación de "aterrizaje" con escala original correcta
                    view.alpha = 0.5f
                    view.scaleX = originalScaleX * 1.4f
                    view.scaleY = originalScaleY * 1.4f
                    view.visibility = View.VISIBLE

                    view.animate()
                        .alpha(1.0f)
                        .scaleX(originalScaleX)
                        .scaleY(originalScaleY)
                        .setDuration(200)
                        .setInterpolator(android.view.animation.OvershootInterpolator())
                        .withEndAction {
                            // Redondear después de la animación
                            view.scaleX = (Math.round(view.scaleX * 100.0) / 100.0).toFloat()
                            view.scaleY = (Math.round(view.scaleY * 100.0) / 100.0).toFloat()
                        }
                        .start()

                } else {
                    // Fuera del área válida - restaurar escala original
                    val layoutParams = view.layoutParams as ViewGroup.MarginLayoutParams
                    layoutParams.leftMargin = x - view.width / 2
                    layoutParams.topMargin = y - view.height / 2
                    view.layoutParams = layoutParams

                    view.alpha = 1.0f
                    view.scaleX = originalScaleX
                    view.scaleY = originalScaleY
                    view.visibility = View.VISIBLE
                }
                return true
            }

            DragEvent.ACTION_DRAG_ENDED -> {
                val view = event.localState as View

                // Recuperar la escala original
                val originalScaleX = view.getTag(R.id.original_scale_x) as? Float ?: 1.0f
                val originalScaleY = view.getTag(R.id.original_scale_y) as? Float ?: 1.0f

                if (!event.result) {
                    // El arrastre fue cancelado, restaurar estado
                    view.animate()
                        .alpha(1.0f)
                        .scaleX(originalScaleX)
                        .scaleY(originalScaleY)
                        .setDuration(200)
                        .start()
                }

                if (!view.isShown) {
                    view.visibility = View.VISIBLE
                }
                return true
            }

            else -> return false
        }
    }

    // Resto de funciones sin cambios (playIconSound, getIconResource, etc.)
    // saveSceneToDatabase necesita incluir rotation
    private fun createElementContentValues(element: ImageView, sceneName: String): ContentValues {
        val layoutParams = element.layoutParams as FrameLayout.LayoutParams
        val description = element.contentDescription?.toString() ?: ""

        return ContentValues().apply {
            put(PlantaEscenarioDatabaseHelper.COLUMN_NAME, sceneName)
            put(PlantaEscenarioDatabaseHelper.COLUMN_DESCRIPTION, description)
            put(PlantaEscenarioDatabaseHelper.COLUMN_ICON, description)

            val xRel = element.getTag(R.id.pos_x_rel) as? Float ?: 0.5f
            val yRel = element.getTag(R.id.pos_y_rel) as? Float ?: 0.5f

            put(PlantaEscenarioDatabaseHelper.COLUMN_X, layoutParams.leftMargin.toFloat())
            put(PlantaEscenarioDatabaseHelper.COLUMN_Y, layoutParams.topMargin.toFloat())
            put(PlantaEscenarioDatabaseHelper.COLUMN_X_REL, xRel)
            put(PlantaEscenarioDatabaseHelper.COLUMN_Y_REL, yRel)
            put(PlantaEscenarioDatabaseHelper.COLUMN_SCALE, element.scaleX)
            put(PlantaEscenarioDatabaseHelper.COLUMN_ROTATION, element.rotation)
            put(
                PlantaEscenarioDatabaseHelper.COLUMN_BACKGROUND_URI,
                selectedBackgroundUri?.toString()
            )
            put(PlantaEscenarioDatabaseHelper.COLUMN_SOUND_ENABLED, if (isSoundEnabled) 1 else 0)
        }
    }

    fun loadSceneFromDatabase(sceneName: String) {
        if (!this::elementContainer.isInitialized) {
            return
        }
        elementContainer.removeAllViews()
        val db = databaseHelper.readableDatabase
        val cursor = db.query(
            PlantaEscenarioDatabaseHelper.TABLE_NAME,
            null,
            "${PlantaEscenarioDatabaseHelper.COLUMN_NAME}=?",
            arrayOf(sceneName),
            null, null, null
        )

        while (cursor.moveToNext()) {
            val description = cursor.getString(
                cursor.getColumnIndexOrThrow(
                    PlantaEscenarioDatabaseHelper.COLUMN_DESCRIPTION
                )
            )
            val iconName = cursor.getString(
                cursor.getColumnIndexOrThrow(
                    PlantaEscenarioDatabaseHelper.COLUMN_ICON
                )
            )
            val xRel = cursor.getFloat(cursor.getColumnIndexOrThrow(PlantaEscenarioDatabaseHelper.COLUMN_X_REL))
            val yRel = cursor.getFloat(cursor.getColumnIndexOrThrow(PlantaEscenarioDatabaseHelper.COLUMN_Y_REL))
            val scale = cursor.getFloat(cursor.getColumnIndexOrThrow(PlantaEscenarioDatabaseHelper.COLUMN_SCALE))
            val rotation = cursor.getFloat(cursor.getColumnIndexOrThrow(PlantaEscenarioDatabaseHelper.COLUMN_ROTATION))

            val (calculatedLeftMargin, calculatedTopMargin) = calculatePositionFromBase(
                xRel,
                yRel,
                300,
                300
            )

            val newElement = ImageView(requireContext()).apply {
                setImageResource(getIconResource(iconName))
                layoutParams = FrameLayout.LayoutParams(300, 300).apply {
                    leftMargin = calculatedLeftMargin
                    topMargin = calculatedTopMargin
                }
                setTag(R.id.pos_x_rel, xRel)
                setTag(R.id.pos_y_rel, yRel)
                contentDescription = description
                scaleX = scale
                scaleY = scale
                this.rotation = rotation

                // ✅ PASO 1: GUARDAR ESCALA ORIGINAL EN TAGS (ESCALA CARGADA)
                setTag(R.id.original_scale_x, scale)
                setTag(R.id.original_scale_y, scale)

                setOnTouchListener { v, event ->
                    when (event.action) {
                        MotionEvent.ACTION_DOWN -> {
                            v.performClick()
                            v.setTag(R.id.touch_start_time, System.currentTimeMillis())

                            // ✅ PASO 2: OBTENER ESCALA DEL TAG
                            val originalScaleX = v.getTag(R.id.original_scale_x) as? Float ?: 1.0f
                            val originalScaleY = v.getTag(R.id.original_scale_y) as? Float ?: 1.0f

                            v.animate()
                                .scaleX(originalScaleX * 1.1f)
                                .scaleY(originalScaleY * 1.1f)
                                .setDuration(100)
                                .start()

                            true
                        }

                        MotionEvent.ACTION_MOVE -> {
                            val startTime = v.getTag(R.id.touch_start_time) as? Long ?: return@setOnTouchListener false
                            val holdDuration = System.currentTimeMillis() - startTime

                            if (holdDuration > 300) {
                                v.animate().cancel()

                                // ✅ PASO 3: RESTAURAR A ESCALA DEL TAG
                                val originalScaleX = v.getTag(R.id.original_scale_x) as? Float ?: 1.0f
                                val originalScaleY = v.getTag(R.id.original_scale_y) as? Float ?: 1.0f
                                v.scaleX = originalScaleX
                                v.scaleY = originalScaleY

                                val data = ClipData.newPlainText("", "")
                                val shadowBuilder = View.DragShadowBuilder(v)
                                v.startDragAndDrop(data, shadowBuilder, v, 0)

                                return@setOnTouchListener true
                            }
                            false
                        }

                        MotionEvent.ACTION_UP -> {
                            val startTime = v.getTag(R.id.touch_start_time) as? Long ?: return@setOnTouchListener false
                            val holdDuration = System.currentTimeMillis() - startTime

                            // ✅ PASO 4: MANTENER ESCALA ACTUAL
                            val currentScaleX = v.scaleX
                            val currentScaleY = v.scaleY

                            v.animate()
                                .scaleX(currentScaleX)
                                .scaleY(currentScaleY)
                                .alpha(1.0f)
                                .setDuration(100)
                                .withEndAction {
                                    v.scaleX = (Math.round(v.scaleX * 100.0) / 100.0).toFloat()
                                    v.scaleY = (Math.round(v.scaleY * 100.0) / 100.0).toFloat()
                                    // ✅ PASO 5: GUARDAR NUEVA ESCALA EN TAG
                                    v.setTag(R.id.original_scale_x, v.scaleX)
                                    v.setTag(R.id.original_scale_y, v.scaleY)
                                }
                                .start()

                            if (holdDuration < 300) {
                                selectElement(v as ImageView)
                            }
                            true
                        }

                        MotionEvent.ACTION_CANCEL -> {
                            val currentScaleX = v.scaleX
                            val currentScaleY = v.scaleY

                            v.animate()
                                .scaleX(currentScaleX)
                                .scaleY(currentScaleY)
                                .alpha(1.0f)
                                .setDuration(100)
                                .withEndAction {
                                    v.scaleX = (Math.round(v.scaleX * 100.0) / 100.0).toFloat()
                                    v.scaleY = (Math.round(v.scaleY * 100.0) / 100.0).toFloat()
                                    // ✅ PASO 5: GUARDAR NUEVA ESCALA EN TAG
                                    v.setTag(R.id.original_scale_x, v.scaleX)
                                    v.setTag(R.id.original_scale_y, v.scaleY)
                                }
                                .start()
                            true
                        }

                        else -> false
                    }
                }
            }
            elementContainer.addView(newElement)
        }
        cursor.close()
        Toast.makeText(requireContext(), "Escena cargada", Toast.LENGTH_SHORT).show()
    }

    private fun View.updatePositionFromRelative(imageRect: Rect) {
        val xRel = getTag(R.id.pos_x_rel) as? Float ?: 0.5f
        val yRel = getTag(R.id.pos_y_rel) as? Float ?: 0.5f

        val (leftMargin, topMargin) = calculatePositionFromBase(
            xRel, yRel,
            this.layoutParams.width,
            this.layoutParams.height
        )

        val layoutParams = this.layoutParams as FrameLayout.LayoutParams
        layoutParams.leftMargin = leftMargin
        layoutParams.topMargin = topMargin
        this.layoutParams = layoutParams
    }


    // Agregar estas funciones al PlantaEscenarioFragment.kt

    private fun getIconsForCategory(category: String): Array<String> {
        return when (category) {
            "Baterias y Percusión" -> arrayOf(
                "Batería", "Batería 2", "Batería 3", "Bombo leguero", "Cajon peruano", "Tumba",
                "Bongos", "Djembe", "Gong", "Maracas", "Timbales", "Conga",
                "Congas", "Pandero", "Shekere", "Cabaza", "Huiro", "Castanuelas"
            )

            "Cuerdas y Sintetizadores" -> arrayOf(
                "Bajo",
                "Bajo 2",
                "Bajo 3",
                "Contrabajo",
                "Banjo",
                "Guitarra electrica",
                "Guitarra electrica 2",
                "Guitarra electrica 3",
                "Guitarra acustica",
                "Guitarra electroacustica",
                "Piano",
                "Piano 2",
                "Organo",
                "Teclado",
                "Armonica",
                "Arpa",
                "Balalaica",
                "Violonchelo",
                "Violin",
                "Sintetizador",
                "Charango",
                "Clavecin",
                "Mandolina",
                "Koto",
                "Laud",
                "Cuatro"
            )

            "Vientos y Similar" -> arrayOf(
                "Acordeon", "Trompeta", "Trombon", "Saxo", "Clarinete",
                "Tuba", "Flauta", "Flauta traversa", "Melodica", "Oboe",
                "Quena", "Zampona", "Fagot", "Corno frances"
            )

            "Voces y Otros" -> arrayOf(
                "Voz 1", "Voz 2", "Voz 3", "Micrófono estudio",
                "Tornamesa", "Estudio", "Pendrive", "Pendrive 2", "Celular",
                "Pendrive", "Pendrive 2", "Celular", "Campanas tubulares", "Didgeridoo",
                "Xilofono", "Cortina"
            )

            "Electricidad" -> arrayOf("Alargador 1", "Alargador 2")
            "Monitores" -> arrayOf(
                "Monitor de piso", "Monitor de piso 2", "Monitor de piso 3",
                "Side fill", "Side fill 2", "Drum fill", "Drum fill 2",
                "In ear", "In ear 2", "Audifonos de estudio", "Audifonos de estudio 2",
                "Array", "Array 2", "Array 3"
            )

            "Mezcla" -> arrayOf(
                "Mezcla 1", "Mezcla 2", "Mezcla 3", "Mezcla 4", "Mezcla 5",
                "Mezcla 6", "Mezcla 7", "Mezcla 8", "Mezcla 9", "Mezcla 10",
                "Mezcla 11", "Mezcla 12", "Mezcla 13", "Mezcla 14", "Mezcla 15",
                "Mezcla 16"
            )

            else -> arrayOf()
        }
    }

    private fun getSoundResource(iconName: String): Int? {
        return when (iconName) {
            "Batería", "Batería 2", "Batería 3" -> R.raw.bateria_sound
            "Bajo", "Bajo 2", "Bajo 3" -> R.raw.slap_bass
            "Contrabajo" -> R.raw.contra_bass
            "Banjo" -> R.raw.banjo
            "Guitarra electrica", "Guitarra electrica 2", "Guitarra electrica 3" -> R.raw.guitar_electric
            "Guitarra acustica" -> R.raw.guitarra_acustica
            "Guitarra electroacustica" -> R.raw.guitar_acoustic
            "Piano", "Piano 2" -> R.raw.piano
            "Organo" -> R.raw.organ
            "Teclado" -> R.raw.keyboard
            "Armonica" -> R.raw.harmonica
            "Arpa" -> R.raw.arpa
            "Balalaica" -> R.raw.balalaica
            "Violonchelo" -> R.raw.violoncello
            "Violin" -> R.raw.violin
            "Sintetizador" -> R.raw.synthesizer
            "Charango" -> R.raw.charango
            "Clavecin" -> R.raw.clavinet
            "Mandolina" -> R.raw.mandolina
            "Koto" -> R.raw.koto
            "Laud" -> R.raw.laud
            "Cuatro" -> R.raw.cuatro
            "Acordeon" -> R.raw.acordeon
            "Trompeta" -> R.raw.trompeta
            "Trombon" -> R.raw.trombon
            "Saxo" -> R.raw.saxo
            "Clarinete" -> R.raw.clarinete
            "Tuba" -> R.raw.tuba
            "Flauta" -> R.raw.flauta
            "Flauta traversa" -> R.raw.flauta_traversa
            "Melodica" -> R.raw.melodica
            "Oboe" -> R.raw.oboe
            "Quena" -> R.raw.quena
            "Zampona" -> R.raw.zampona
            "Fagot" -> R.raw.fagot
            "Corno frances" -> R.raw.cornofrances
            "Cajon peruano" -> R.raw.cajonperuano
            "Tumba" -> R.raw.tumba
            "Bongos" -> R.raw.bongos
            "Djembe" -> R.raw.djembe
            "Gong" -> R.raw.gong
            "Maracas" -> R.raw.maracas
            "Huiro" -> R.raw.huiro
            "Timbales" -> R.raw.timbales
            "Shekere" -> R.raw.shekere
            "Cabaza" -> R.raw.cabaza
            "Castanuelas" -> R.raw.castanuelas
            "Congas", "Conga" -> R.raw.congas
            "Pandero" -> R.raw.pandero
            "Voz 1", "Voz 2", "Voz 3", "Micrófono estudio" -> R.raw.microfono1
            "Mac", "Notebook", "Tornamesa", "Audifonos de estudio", "Audifonos de estudio 2", "Alargador 1", "Alargador 2" -> R.raw.plug
            "Monitor de piso", "Monitor de piso 2", "Monitor de piso 3", "Side fill", "Side fill 2", "Drum fill", "Drum fill 2", "Array", "Array 2", "Array 3", "In ear", "In ear 2" -> R.raw.parlante
            "Bombo leguero" -> R.raw.bomboleguero
            else -> null
        }
    }

    private fun playIconSound(iconName: String) {
        if (!isSoundEnabled) return

        val soundResourceId = getSoundResource(iconName) ?: return
        MediaPlayer.create(requireContext(), soundResourceId)?.apply {
            setOnCompletionListener { it.release() }
            start()
        }
    }

    fun getIconResource(iconName: String): Int {
        iconCache[iconName]?.let { cachedResource ->
            return cachedResource
        }

        val resource = when (iconName) {
            "Batería" -> R.drawable.bateria1
            "Batería 2" -> R.drawable.bateria2
            "Batería 3" -> R.drawable.bateria3
            "Cajon peruano" -> R.drawable.cajonperuano
            "Bajo" -> R.drawable.bajo4
            "Bajo 2" -> R.drawable.bajo2
            "Bajo 3" -> R.drawable.bajo3
            "Contrabajo" -> R.drawable.contrabajo
            "Guitarra electrica" -> R.drawable.guitarraleectrica1
            "Guitarra electrica 2" -> R.drawable.guitarraelectrica2
            "Guitarra electrica 3" -> R.drawable.guitarraelectrica3
            "Guitarra acustica" -> R.drawable.guitarraacustica
            "Guitarra electroacustica" -> R.drawable.guitarraacustica2
            "Piano" -> R.drawable.piano1
            "Piano 2" -> R.drawable.piano2
            "Acordeon" -> R.drawable.acordeon
            "Melodica" -> R.drawable.melodica
            "Pendrive" -> R.drawable.pendrive
            "Pendrive 2" -> R.drawable.pendrive2
            "Celular" -> R.drawable.celular
            "Trompeta" -> R.drawable.trompeta
            "Conga" -> R.drawable.conga
            "Congas" -> R.drawable.congas2
            "Gong" -> R.drawable.gong
            "Djembe" -> R.drawable.djembe
            "Tumba" -> R.drawable.tumba
            "Pandero" -> R.drawable.pandero
            "Cabaza" -> R.drawable.cabaza
            "Castanuelas" -> R.drawable.castanuelas
            "Bongos" -> R.drawable.bongos
            "Shekere" -> R.drawable.shekere
            "Maracas" -> R.drawable.maracas
            "Huiro" -> R.drawable.huiro
            "Timbales" -> R.drawable.timbales
            "Trombon" -> R.drawable.trombon
            "Saxo" -> R.drawable.saxo
            "Tuba" -> R.drawable.tuba
            "Clarinete" -> R.drawable.clarinete
            "Teclado" -> R.drawable.teclado
            "Organo" -> R.drawable.organo
            "Estudio" -> R.drawable.estudio
            "Armonica" -> R.raw.harmonica
            "Arpa" -> R.drawable.arpa
            "Balalaica" -> R.drawable.balalaica
            "Banjo" -> R.drawable.banjo
            "Bombo leguero" -> R.drawable.bomboleguero
            "Campanas tubulares" -> R.drawable.campanastubulares
            "Charango" -> R.drawable.charango
            "Flauta" -> R.drawable.flauta
            "Clavecin" -> R.drawable.clavecin
            "Corneta" -> R.drawable.corneta
            "Corno frances" -> R.drawable.cornofrances
            "Cortina" -> R.drawable.cortina
            "Didgeridoo" -> R.drawable.didgeridoo
            "Fagot" -> R.drawable.fagot
            "Flauta traversa" -> R.drawable.flautatraversa
            "Koto" -> R.drawable.koto
            "Laud" -> R.drawable.laud
            "Mandolina" -> R.drawable.mandolina
            "Oboe" -> R.drawable.oboe
            "Quena" -> R.drawable.quena
            "Sintetizador" -> R.drawable.sintetizador
            "Sitar" -> R.drawable.sitar
            "Timbalorquesta" -> R.drawable.timbalorquesta
            "Ukelele" -> R.drawable.ukelele
            "Violonchelo" -> R.drawable.violonchelo
            "Violin" -> R.drawable.violin
            "Xilofono" -> R.drawable.xilofono
            "Zampona" -> R.drawable.zampona
            "Cuatro" -> R.drawable.cuatro
            "Voz 1" -> R.drawable.microfono3
            "Voz 2" -> R.drawable.microfono4
            "Voz 3" -> R.drawable.microfono5
            "Micrófono estudio" -> R.drawable.microfonoestudio
            "Mac" -> R.drawable.mac
            "Notebook" -> R.drawable.notebook
            "Tornamesa" -> R.drawable.torna
            "Monitor de piso" -> R.drawable.monitorpiso1
            "Monitor de piso 2" -> R.drawable.monitorpiso2
            "Monitor de piso 3" -> R.drawable.monitorpiso3
            "Side fill" -> R.drawable.drumfill
            "Side fill 2" -> R.drawable.drumfill2
            "Drum fill" -> R.drawable.sidefill
            "Drum fill 2" -> R.drawable.sidefill2
            "Array" -> R.drawable.array1
            "Array 2" -> R.drawable.array2
            "Array 3" -> R.drawable.array3
            "In ear" -> R.drawable.inear1
            "In ear 2" -> R.drawable.inear2
            "Audifonos de estudio" -> R.drawable.audifonosestudio
            "Audifonos de estudio 2" -> R.drawable.audifonosestudio2
            "Mezcla 1" -> R.drawable.mezcla1
            "Mezcla 2" -> R.drawable.mezcla2
            "Mezcla 3" -> R.drawable.mezcla3
            "Mezcla 4" -> R.drawable.mezcla4
            "Mezcla 5" -> R.drawable.mezcla5
            "Mezcla 6" -> R.drawable.mezcla6
            "Mezcla 7" -> R.drawable.mezcla7
            "Mezcla 8" -> R.drawable.mezcla8
            "Mezcla 9" -> R.drawable.mezcla9
            "Mezcla 10" -> R.drawable.mezcla10
            "Mezcla 11" -> R.drawable.mezcla11
            "Mezcla 12" -> R.drawable.mezcla12
            "Mezcla 13" -> R.drawable.mezcla13
            "Mezcla 14" -> R.drawable.mezcla14
            "Mezcla 15" -> R.drawable.mezcla15
            "Mezcla 16" -> R.drawable.mezcla16
            "Alargador 1" -> R.drawable.alargador1
            "Alargador 2" -> R.drawable.alargador2
            else -> R.drawable.exitico
        }

        iconCache[iconName] = resource
        return resource
    }

    // Funciones para guardar/cargar escenas (conservadas del original)
    private fun showSaveSceneDialog() {
        val dialogView =
            LayoutInflater.from(requireContext()).inflate(R.layout.dialog_scene_selector, null)
        val recyclerView = dialogView.findViewById<RecyclerView>(R.id.sceneRecyclerView)
        val searchEditText = dialogView.findViewById<TextInputEditText>(R.id.searchEditText)

        val sceneItems = mutableListOf<SceneItem>()
        val db = databaseHelper.readableDatabase
        val cursor = db.rawQuery(
            "SELECT DISTINCT ${PlantaEscenarioDatabaseHelper.COLUMN_NAME} FROM ${PlantaEscenarioDatabaseHelper.TABLE_NAME}",
            null
        )

        while (cursor.moveToNext()) {
            val sceneName = cursor.getString(
                cursor.getColumnIndexOrThrow(
                    PlantaEscenarioDatabaseHelper.COLUMN_NAME
                )
            )

            val countCursor = db.query(
                PlantaEscenarioDatabaseHelper.TABLE_NAME,
                null,
                "${PlantaEscenarioDatabaseHelper.COLUMN_NAME}=?",
                arrayOf(sceneName),
                null, null, null
            )
            val elementCount = countCursor.count
            countCursor.close()

            sceneItems.add(SceneItem(sceneName, elementCount))
        }
        cursor.close()

        val builder = AlertDialog.Builder(requireContext())
        builder.setTitle("Guardar Planta")
        builder.setView(dialogView)
        builder.setNegativeButton("Cancelar", null)
        builder.setPositiveButton("Nueva Planta") { _, _ ->
            showNewSceneNameDialog()
        }
        val dialog = builder.create()

        val adapter = SceneSelectorAdapter(sceneItems, { selectedScene ->
            dialog.dismiss()
            saveSceneToDatabase(selectedScene)
            savedSceneName = selectedScene
        }, { sceneName ->
            AlertDialog.Builder(requireContext())
                .setTitle("Confirmar sobrescritura")
                .setMessage("¿Deseas reemplazar la planta '$sceneName'?")
                .setPositiveButton("Sí") { _, _ ->
                    saveSceneToDatabase(sceneName)
                    savedSceneName = sceneName
                    dialog.dismiss()
                }
                .setNegativeButton("No", null)
                .show()
        })

        recyclerView.layoutManager = LinearLayoutManager(requireContext())
        recyclerView.adapter = adapter

        searchEditText?.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                adapter.filter(s?.toString() ?: "")
            }

            override fun afterTextChanged(s: Editable?) {}
        })

        dialog.show()
    }

    private fun saveSceneToDatabase(sceneName: String) {
        savedSceneName = sceneName

        databaseHelper.writableDatabase.use { db ->
            db.beginTransaction()
            try {
                db.delete(
                    PlantaEscenarioDatabaseHelper.TABLE_NAME,
                    "${PlantaEscenarioDatabaseHelper.COLUMN_NAME}=?",
                    arrayOf(sceneName)
                )

                val valuesList = mutableListOf<ContentValues>()
                for (i in 0 until elementContainer.childCount) {
                    val element = elementContainer.getChildAt(i) as? ImageView ?: continue
                    valuesList.add(createElementContentValues(element, sceneName))
                }

                valuesList.forEach { values ->
                    db.insert(PlantaEscenarioDatabaseHelper.TABLE_NAME, null, values)
                }

                db.setTransactionSuccessful()
                Toast.makeText(requireContext(), "Planta guardada", Toast.LENGTH_SHORT).show()
            } finally {
                db.endTransaction()
            }
        }
    }

    private fun showLoadSceneDialog() {
        val dialogView =
            LayoutInflater.from(requireContext()).inflate(R.layout.dialog_scene_selector, null)
        val recyclerView = dialogView.findViewById<RecyclerView>(R.id.sceneRecyclerView)
        val searchEditText = dialogView.findViewById<TextInputEditText>(R.id.searchEditText)

        val sceneItems = mutableListOf<SceneItem>()
        val db = databaseHelper.readableDatabase
        val cursor = db.rawQuery(
            "SELECT DISTINCT ${PlantaEscenarioDatabaseHelper.COLUMN_NAME} FROM ${PlantaEscenarioDatabaseHelper.TABLE_NAME}",
            null
        )

        if (cursor.count == 0) {
            Toast.makeText(requireContext(), "No hay Plantas guardadas", Toast.LENGTH_SHORT).show()
            cursor.close()
            return
        }

        while (cursor.moveToNext()) {
            val sceneName = cursor.getString(
                cursor.getColumnIndexOrThrow(
                    PlantaEscenarioDatabaseHelper.COLUMN_NAME
                )
            )

            val countCursor = db.query(
                PlantaEscenarioDatabaseHelper.TABLE_NAME,
                null,
                "${PlantaEscenarioDatabaseHelper.COLUMN_NAME}=?",
                arrayOf(sceneName),
                null, null, null
            )
            val elementCount = countCursor.count
            countCursor.close()

            sceneItems.add(SceneItem(sceneName, elementCount))
        }
        cursor.close()

        val builder = AlertDialog.Builder(requireContext())
        builder.setTitle("Cargar Planta")
        builder.setView(dialogView)
        builder.setNegativeButton("Cancelar", null)
        val dialog = builder.create()

        val adapter = SceneSelectorAdapter(sceneItems, { selectedScene ->
            dialog.dismiss()
            loadSceneFromDatabase(selectedScene)
        }, { sceneName ->
            AlertDialog.Builder(requireContext())
                .setTitle("Eliminar Planta")
                .setMessage("¿Deseas eliminar la planta '$sceneName'?")
                .setPositiveButton("Sí") { _, _ ->
                    deleteSceneFromDatabase(sceneName)
                    dialog.dismiss()
                    showLoadSceneDialog()
                }
                .setNegativeButton("No", null)
                .show()
        })

        recyclerView.layoutManager = LinearLayoutManager(requireContext())
        recyclerView.adapter = adapter

        searchEditText?.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                adapter.filter(s?.toString() ?: "")
            }

            override fun afterTextChanged(s: Editable?) {}
        })

        dialog.show()
    }

    private fun getSceneNames(): Array<String> {
        return try {
            val db = databaseHelper.readableDatabase
            val cursor = db.rawQuery(
                "SELECT DISTINCT ${PlantaEscenarioDatabaseHelper.COLUMN_NAME} FROM ${PlantaEscenarioDatabaseHelper.TABLE_NAME}",
                null
            )
            val sceneNames = mutableListOf<String>()
            while (cursor.moveToNext()) {
                sceneNames.add(
                    cursor.getString(
                        cursor.getColumnIndexOrThrow(
                            PlantaEscenarioDatabaseHelper.COLUMN_NAME
                        )
                    )
                )
            }
            cursor.close()
            sceneNames.toTypedArray()
        } catch (e: Exception) {
            Toast.makeText(safeContext(), "Error al cargar escenas", Toast.LENGTH_SHORT).show()
            emptyArray()
        }
    }

    private fun showNewSceneNameDialog() {
        val dialogView =
            LayoutInflater.from(requireContext()).inflate(R.layout.dialog_new_scene_name, null)
        val sceneNameEditText = dialogView.findViewById<TextInputEditText>(R.id.sceneNameEditText)

        val builder = AlertDialog.Builder(requireContext())
        builder.setTitle("Nueva Planta")
        builder.setView(dialogView)
        builder.setPositiveButton("Guardar") { _, _ ->
            val sceneName = sceneNameEditText?.text?.toString()?.trim() ?: ""
            if (sceneName.isNotEmpty()) {
                if (isSceneNameExists(sceneName)) {
                    Toast.makeText(requireContext(), "Este nombre ya existe", Toast.LENGTH_SHORT)
                        .show()
                    showNewSceneNameDialog()
                } else {
                    saveSceneToDatabase(sceneName)
                    savedSceneName = sceneName
                    Toast.makeText(
                        requireContext(),
                        "Planta '$sceneName' guardada",
                        Toast.LENGTH_SHORT
                    ).show()
                }
            } else {
                Toast.makeText(
                    requireContext(),
                    "El nombre no puede estar vacío",
                    Toast.LENGTH_SHORT
                ).show()
            }
        }
        builder.setNegativeButton("Cancelar", null)
        builder.show()
    }

    private fun isSceneNameExists(sceneName: String): Boolean {
        val db = databaseHelper.readableDatabase
        val cursor = db.query(
            PlantaEscenarioDatabaseHelper.TABLE_NAME,
            null,
            "${PlantaEscenarioDatabaseHelper.COLUMN_NAME}=?",
            arrayOf(sceneName),
            null, null, null
        )
        val exists = cursor.count > 0
        cursor.close()
        return exists
    }

    private fun deleteSceneFromDatabase(sceneName: String) {
        databaseHelper.writableDatabase.use { db ->
            db.delete(
                PlantaEscenarioDatabaseHelper.TABLE_NAME,
                "${PlantaEscenarioDatabaseHelper.COLUMN_NAME}=?",
                arrayOf(sceneName)
            )
            Toast.makeText(requireContext(), "Planta eliminada", Toast.LENGTH_SHORT).show()
        }
    }

    // Data classes y adaptadores (sin cambios)
    data class SceneItem(val name: String, val elementCount: Int)
    data class IconItem(val name: String, val iconRes: Int)
    data class CategoryItem(val name: String, val iconRes: Int)

    inner class IconSelectorAdapter(
        private var items: List<IconItem>,
        private val onItemClick: (String) -> Unit
    ) : RecyclerView.Adapter<IconSelectorAdapter.IconViewHolder>() {

        private var filteredItems: List<IconItem> = items

        inner class IconViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
            val iconImageView: ImageView = itemView.findViewById(R.id.iconImageView)
            val iconNameTextView: TextView = itemView.findViewById(R.id.iconNameTextView)
            val cardView: MaterialCardView = itemView as MaterialCardView
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): IconViewHolder {
            val view = LayoutInflater.from(parent.context)
                .inflate(R.layout.item_icon_selector, parent, false)
            return IconViewHolder(view)
        }

        override fun onBindViewHolder(holder: IconViewHolder, position: Int) {
            val item = filteredItems[position]
            holder.iconImageView.setImageResource(item.iconRes)
            holder.iconNameTextView.text = item.name
            holder.cardView.setOnClickListener {
                onItemClick(item.name)
            }
        }

        override fun getItemCount(): Int = filteredItems.size

        fun filter(query: String) {
            filteredItems = if (query.isEmpty()) {
                items
            } else {
                items.filter { it.name.contains(query, ignoreCase = true) }
            }
            notifyDataSetChanged()
        }
    }

    inner class CategorySelectorAdapter(
        private val items: List<CategoryItem>,
        private val onItemClick: (String) -> Unit
    ) : RecyclerView.Adapter<CategorySelectorAdapter.CategoryViewHolder>() {

        inner class CategoryViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
            val categoryIconImageView: ImageView = itemView.findViewById(R.id.categoryIconImageView)
            val categoryNameTextView: TextView = itemView.findViewById(R.id.categoryNameTextView)
            val cardView: MaterialCardView = itemView as MaterialCardView
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): CategoryViewHolder {
            val view = LayoutInflater.from(parent.context)
                .inflate(R.layout.item_category_selector, parent, false)
            return CategoryViewHolder(view)
        }

        override fun onBindViewHolder(holder: CategoryViewHolder, position: Int) {
            val item = items[position]
            holder.categoryIconImageView.setImageResource(item.iconRes)
            holder.categoryNameTextView.text = item.name
            holder.cardView.setOnClickListener {
                onItemClick(item.name)
            }
        }

        override fun getItemCount(): Int = items.size
    }

    inner class SceneSelectorAdapter(
        private var items: List<SceneItem>,
        private val onItemClick: (String) -> Unit,
        private val onDeleteClick: (String) -> Unit
    ) : RecyclerView.Adapter<SceneSelectorAdapter.SceneViewHolder>() {

        private var filteredItems: List<SceneItem> = items

        inner class SceneViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
            val sceneNameTextView: TextView = itemView.findViewById(R.id.sceneNameTextView)
            val sceneDetailsTextView: TextView = itemView.findViewById(R.id.sceneDetailsTextView)
            val deleteButton: View = itemView.findViewById(R.id.deleteSceneButton)
            val cardView: MaterialCardView = itemView as MaterialCardView
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): SceneViewHolder {
            val view = LayoutInflater.from(parent.context)
                .inflate(R.layout.item_scene_selector, parent, false)
            return SceneViewHolder(view)
        }

        override fun onBindViewHolder(holder: SceneViewHolder, position: Int) {
            val item = filteredItems[position]
            holder.sceneNameTextView.text = item.name
            holder.sceneDetailsTextView.text = "${item.elementCount} instrumentos"
            holder.cardView.setOnClickListener {
                onItemClick(item.name)
            }
            holder.deleteButton.setOnClickListener {
                onDeleteClick(item.name)
            }
        }

        override fun getItemCount(): Int = filteredItems.size

        fun filter(query: String) {
            filteredItems = if (query.isEmpty()) {
                items
            } else {
                items.filter { it.name.contains(query, ignoreCase = true) }
            }
            notifyDataSetChanged()
        }
    }
}
