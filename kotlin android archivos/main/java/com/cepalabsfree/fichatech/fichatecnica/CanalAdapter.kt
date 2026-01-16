package com.cepalabsfree.fichatech.fichatecnica

import android.content.Context
import android.util.Log
import android.util.TypedValue
import android.view.LayoutInflater
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.InputMethodManager
import android.widget.*
import androidx.annotation.Keep
import androidx.appcompat.app.AlertDialog
import androidx.cardview.widget.CardView
import androidx.recyclerview.widget.ItemTouchHelper
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.cepalabsfree.fichatech.R
import com.google.android.material.textfield.MaterialAutoCompleteTextView

import java.util.*

@Keep
// Adapter encargado de renderizar y administrar la lista horizontal/vertical de canales.
// - Gestiona IDs estables (soporta elementos temporales antes de persistir en BD)
// - Soporta reordenamiento mediante ItemTouchHelper
// - Expande/contrae cada item para mostrar/ocultar detalles
// - Expone callbacks para cambios: fader, color y datos del canal
class CanalAdapter(
    private val canales: MutableList<Canal>,
    private val onDeleteClickListener: OnDeleteClickListener,
    private val recyclerView: RecyclerView,
    private var onFaderChangeListener: ((canalId: Int, level: Int, isFinalChange: Boolean) -> Unit)? = null
) : RecyclerView.Adapter<CanalAdapter.CanalViewHolder>() {

    companion object {
        private const val TAG = "CanalAdapter"

        // Cache global de colores de tema para evitar recalcular para cada ViewHolder
        private var cachedThemeColors: Pair<Int, Int>? = null

        fun clearThemeCache() {
            cachedThemeColors = null
        }
    }

    // Posición expandida actualmente (-1 si ninguna)
    private var expandedPosition = -1

    // Listener para cambios de color desde el ViewHolder
    private var onColorChangeListener: ((position: Int, color: Int) -> Unit)? = null

    // Listener que notifica cambios en campos del canal (nombre, fx, microfonia)
    private var onCanalDataChangeListener: ((canalId: Int, field: String, value: String) -> Unit)? = null

    // Callback externo opcional cuando termina un movimiento/drag
    var onMoveFinished: (() -> Unit)? = null

    // Referencia al ItemTouchHelper para iniciar arrastres desde un handle
    private var itemTouchHelper: ItemTouchHelper? = null

    // Contadores y mapas para IDs temporales (cuando el canal no tiene id de BD aún)
    private var tempIdCounter = -1
    private val tempIdMap = mutableMapOf<Int, Long>()

    // Mecanismo para refrescar numeración de items con debounce
    private val numerationHandler = android.os.Handler(android.os.Looper.getMainLooper())
    private val numerationRunnable = Runnable {
        refreshNumeration()
    }

    // Adapters para los spinners/autocompletes de microfonía y FX
    private lateinit var microfoniaAdapter: ArrayAdapter<String>
    private lateinit var fxAdapter: ArrayAdapter<String>
    private var spinnersInitialized = false

    init {
        // Indicamos que los items tienen IDs estables -> mejora rendimiento y animaciones al reordenar
        setHasStableIds(true)
    }

    // Interfaz para manejar la eliminación solicitada desde un item
    interface OnDeleteClickListener {
        fun onDeleteClick(position: Int)
    }

    // Setters para listeners externos
    fun setOnFaderChangeListener(listener: (canalId: Int, level: Int, isFinalChange: Boolean) -> Unit) {
        onFaderChangeListener = listener
    }

    fun setOnCanalDataChangeListener(listener: (canalId: Int, field: String, value: String) -> Unit) {
        onCanalDataChangeListener = listener
    }

    fun setOnColorChangeListener(listener: (position: Int, color: Int) -> Unit) {
        onColorChangeListener = listener
    }

    // Inicializa los adapters para las opciones de microfonía y FX (se llama desde ViewHolder)
    private fun initializeSpinners(context: Context) {
        if (spinnersInitialized) return

        val microfoniaOptions = context.resources.getStringArray(R.array.microfonia_options)
        val fxOptions = context.resources.getStringArray(R.array.fx_options)

        microfoniaAdapter = ArrayAdapter(context, android.R.layout.simple_dropdown_item_1line, microfoniaOptions)
        fxAdapter = ArrayAdapter(context, android.R.layout.simple_dropdown_item_1line, fxOptions)

        spinnersInitialized = true
    }

    override fun getItemId(position: Int): Long {
        if (!isValidPosition(position)) {
            Log.w(TAG, "⚠️ getItemId: Posición inválida $position")
            return RecyclerView.NO_ID
        }

        val canal = canales[position]

        // Si el canal ya tiene un ID persistente de BD, usarlo
        if (canal.id != -1) {
            val idPersistente = canal.id.toLong()
            Log.v(TAG, "📌 getItemId posición $position: ID persistente $idPersistente")
            return idPersistente
        }

        // Si no, usar o crear un ID temporal
        val tempId = tempIdMap.getOrPut(position) {
            val nuevoTempId = generarNuevoIdTemporal()
            Log.d(TAG, "📌 getItemId posición $position: Nuevo ID temporal $nuevoTempId")
            nuevoTempId
        }

        Log.v(TAG, "📌 getItemId posición $position: ID temporal $tempId")
        return tempId
    }

    fun setItemTouchHelper(helper: ItemTouchHelper) {
        this.itemTouchHelper = helper
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): CanalViewHolder {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_canal, parent, false)
        return CanalViewHolder(view)
    }

    override fun onBindViewHolder(holder: CanalViewHolder, position: Int) {
        if (!isValidPosition(position)) {
            Log.w("CanalAdapter", "Intentando bindear posición inválida: $position")
            return
        }

        val canal = canales[position]
        holder.bind(canal, position)

        // Evitar que ciertos views reaccionen a long click para prevenir conflictos con drag
        arrayOf(holder.btnExpand, holder.buttonDelete, holder.seekBarFader, holder.textViewNumero).forEach { view ->
            view.isLongClickable = false
        }

        // El handle de drag sí es longClickable
        holder.btnDragHandle.isLongClickable = true
        holder.headerLayout.setOnLongClickListener(null)
    }

    override fun onViewRecycled(holder: CanalViewHolder) {
        super.onViewRecycled(holder)
        // Limpiar listeners pesados o referencias para evitar leaks
        holder.cleanup()
    }

    // Valida que la posición sea correcta respecto al tamaño y al conteo del adapter
    private fun isValidPosition(position: Int): Boolean {
        return position in 0 until itemCount && position in canales.indices
    }

    private fun isValidAdapterPosition(holder: CanalViewHolder): Boolean {
        val position = holder.bindingAdapterPosition
        return position != RecyclerView.NO_POSITION && isValidPosition(position)
    }

    override fun getItemCount(): Int = canales.size

    // Public: refresca numeración con debounce para no forzar muchos redraws al arrastrar
    fun refreshNumerationDebounced() {
        numerationHandler.removeCallbacks(numerationRunnable)
        numerationHandler.postDelayed(numerationRunnable, 50)
    }

    // Recalcula qué items visibles deben actualizar su numeración (mejora eficiencia)
    fun refreshNumeration() {
        val layoutManager = (recyclerView.layoutManager as? LinearLayoutManager)
        val firstVisible = layoutManager?.findFirstVisibleItemPosition() ?: 0
        val lastVisible = layoutManager?.findLastVisibleItemPosition() ?: itemCount - 1

        if (firstVisible >= 0 && lastVisible >= firstVisible) {
            for (i in firstVisible..lastVisible) {
                if (i in canales.indices) {
                    notifyItemChanged(i)
                }
            }
        }
    }

    // Mueve en la lista interna y notifica cambio visual al reordenar
    fun moveCanal(fromPos: Int, toPos: Int) {
        if (fromPos in canales.indices && toPos in canales.indices && fromPos != toPos) {
            Collections.swap(canales, fromPos, toPos)
            notifyItemMoved(fromPos, toPos)
            Log.d("CanalAdapter", "Canal movido: $fromPos → $toPos")
        }
    }

    fun getCanales(): List<Canal> = canales

    // Reemplaza completamente la lista interna por una nueva (usado al recuperar desde BD)
    fun updateCanales(nuevosCanales: List<Canal>) {
        Log.d(TAG, "🔄 Actualizando lista de canales: ${nuevosCanales.size} elementos")

        // Mostrar información de debug
        nuevosCanales.forEachIndexed { index, canal ->
            Log.d(TAG, "   Nuevo canal[$index]: id=${canal.id}, nombre='${canal.nombre}'")
        }

        // Guardar backup de IDs temporales
        val tempIdMapBackup = tempIdMap.toMap()

        // Limpiar y actualizar
        canales.clear()
        canales.addAll(nuevosCanales)

        // Reconstruir tempIdMap
        tempIdMap.clear()
        nuevosCanales.forEachIndexed { index, canal ->
            if (canal.id == -1) {
                // Intentar preservar ID temporal anterior para esta posición
                tempIdMap[index] = tempIdMapBackup[index] ?: generarNuevoIdTemporal()
            }
        }

        notifyDataSetChanged()
        Log.d(TAG, "✅ Lista actualizada - ${canales.size} canales, ${tempIdMap.size} IDs temporales")
    }

    private fun generarNuevoIdTemporal(): Long {
        val nuevoId = tempIdCounter--.toLong()
        Log.d(TAG, "   🆔 Generado nuevo ID temporal: $nuevoId")
        return nuevoId
    }

    private fun getNuevoIdTemporal(): Long {
        return (tempIdCounter--).toLong()
    }

    fun debugEstadoAdapter() {
        Log.d(TAG, "=== DEBUG ESTADO ADAPTER ===")
        Log.d(TAG, "Canales en adapter: ${canales.size}")
        Log.d(TAG, "tempIdMap tamaño: ${tempIdMap.size}")

        canales.forEachIndexed { index, canal ->
            val tempId = tempIdMap[index]
            Log.d(TAG, "  Posición $index: Canal(id=${canal.id}, nombre='${canal.nombre}') - ID temporal: $tempId")
        }

        Log.d(TAG, "=== FIN DEBUG ===")
    }

    // Remueve un item y ajusta el mapa de ids temporales para mantener consistencia
    fun removeItem(position: Int) {
        if (!isValidPosition(position)) {
            Log.e("CanalAdapter", "Posición inválida para remover: $position, tamaño: ${canales.size}")
            return
        }

        canales.removeAt(position)
        tempIdMap.remove(position)

        // Reorganizar tempIdMap para reflejar el desplazamiento de posiciones
        val newTempIdMap = mutableMapOf<Int, Long>()
        tempIdMap.forEach { (oldPos, id) ->
            if (oldPos > position) {
                newTempIdMap[oldPos - 1] = id
            } else if (oldPos < position) {
                newTempIdMap[oldPos] = id
            }
        }
        tempIdMap.clear()
        tempIdMap.putAll(newTempIdMap)

        notifyItemRemoved(position)

        if (position < canales.size) {
            notifyItemRangeChanged(position, canales.size - position)
        }
    }

    // Obtener la vista de encabezado (usado por ItemTouchHelper u otras utilidades)
    fun getHeaderView(holder: RecyclerView.ViewHolder): View? {
        return if (holder is CanalViewHolder) holder.headerLayout else null
    }

    // Contrae todos los items (oculta contenido expandido) — útil cuando comienza un drag
    fun compressAllCanals() {
        for (i in 0 until itemCount) {
            val holder = recyclerView.findViewHolderForAdapterPosition(i) as? CanalViewHolder
            holder?.contentLayout?.visibility = View.GONE
            holder?.btnExpand?.setImageResource(android.R.drawable.ic_input_add)
            holder?.itemView?.requestLayout()
        }
        expandedPosition = -1
    }

    // ViewHolder que contiene y administra los elementos UI por cada canal
    inner class CanalViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        // Referencias a Views del layout item_canal.xml
        val textViewNumero: TextView = itemView.findViewById(R.id.tvNumeroCanal)
        private val textViewNombre: TextView = itemView.findViewById(R.id.tvNombreCanal)
        val spinnerMicrofonia: MaterialAutoCompleteTextView = itemView.findViewById(R.id.spinnerMicrofonia)
        val spinnerFx: MaterialAutoCompleteTextView = itemView.findViewById(R.id.spinnerFX)
        val buttonDelete: ImageButton = itemView.findViewById(R.id.btn_eliminar_canal)
        val contentLayout: CardView = itemView.findViewById(R.id.contentCanal)
        val headerLayout: LinearLayout = itemView.findViewById(R.id.headerCanal)
        val seekBarFader: VerticalSeekBar = itemView.findViewById(R.id.seekBarFader)
        val btnExpand: ImageButton = itemView.findViewById(R.id.btnExpand)
        private val mainCanalLayout: CardView = itemView.findViewById(R.id.mainCanalLayout)
        val btnDragHandle: ImageButton = itemView.findViewById(R.id.btnDragHandle)

        init {
            // Evitar autofill en los campos que no deben recibirlo
            spinnerMicrofonia.importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO
            spinnerFx.importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO
        }

        // Flags internos para evitar volver a inicializar listeners y spinners
        private var spinnersSetup = false
        private var listenersInitialized = false
        private var currentCanalId: Int = -1
        private var currentPosition: Int = -1
        private var isEditing = false
        private var seekBarListener: SeekBar.OnSeekBarChangeListener? = null

        init {
            // Inicializar los datos compartidos entre holders sólo una vez
            if (!spinnersInitialized) {
                initializeSpinners(itemView.context)
            }
            setupSpinners()
            setupListeners()
            listenersInitialized = true
        }

        // Limpieza para evitar referencias a listeners cuando el ViewHolder es reciclado
        fun cleanup() {
            seekBarListener?.let { listener ->
                seekBarFader.setOnSeekBarChangeListener(null)
            }
            seekBarListener = null
        }

        // Configura adapters en cada holder (si aún no están configurados)
        private fun setupSpinners() {
            if (spinnersSetup) return

            spinnerMicrofonia.setAdapter(microfoniaAdapter)
            spinnerFx.setAdapter(fxAdapter)

            spinnersSetup = true
        }

        // Obtener colores del tema actual (cacheado en companion)
        private fun getThemeColors(): Pair<Int, Int> {
            if (cachedThemeColors != null) {
                return cachedThemeColors!!
            }

            val typedValue = TypedValue()
            val theme = itemView.context.theme

            theme.resolveAttribute(android.R.attr.colorBackground, typedValue, true)
            val backgroundColor = typedValue.data

            theme.resolveAttribute(android.R.attr.textColorPrimary, typedValue, true)
            val textColor = typedValue.data

            val colors = Pair(backgroundColor, textColor)
            cachedThemeColors = colors

            Log.d("CanalAdapter", "✅ Colores de tema cacheados")
            return colors
        }

        // Aplica color de fondo al Card principal del canal (usa color del canal si existe)
        private fun applyColors(canal: Canal) {
            val (backgroundColor, textColor) = getThemeColors()
            val finalBackgroundColor = if (canal.color == 0) backgroundColor else canal.color

            mainCanalLayout.setBackgroundColor(finalBackgroundColor)
        }

        // Vincula datos del modelo al ViewHolder y ajusta vistas
        fun bind(canal: Canal, position: Int) {
            currentCanalId = canal.id
            currentPosition = position

            val layoutParams = itemView.layoutParams as RecyclerView.LayoutParams
            layoutParams.height = RecyclerView.LayoutParams.MATCH_PARENT
            itemView.layoutParams = layoutParams

            updateViewData(canal, position)

            // Sincronizar progreso de fader entre UI y modelo
            if (seekBarFader.progress != canal.faderLevel) {
                Log.d(TAG, "⚠️ Discrepancia en fader: UI=${seekBarFader.progress}, Memoria=${canal.faderLevel}")
                seekBarFader.progress = canal.faderLevel
            }

            applyColors(canal)
            Log.d(TAG, "✅ Canal vinculado: posición=$position, ID=${canal.id}, fader=${canal.faderLevel}")
        }

        // Actualiza los textos, visibilidad y estado de los controles del item
        private fun updateViewData(canal: Canal, position: Int) {
            textViewNumero.text = "#${position + 1}"
            textViewNombre.text = canal.nombre ?: ""
            spinnerMicrofonia.setText(canal.microfonia, false)
            spinnerFx.setText(canal.fx, false)

            if (seekBarFader.progress != canal.faderLevel) {
                seekBarFader.progress = canal.faderLevel
            }

            setupSpinnerListeners()

            // Mostrar detalle expandido sólo si la posición coincide con expandedPosition
            if (position == expandedPosition) {
                contentLayout.visibility = View.VISIBLE
                btnExpand.setImageResource(android.R.drawable.ic_delete)
            } else {
                contentLayout.visibility = View.GONE
                btnExpand.setImageResource(android.R.drawable.ic_input_add)
            }

            applyColors(canal)
        }

        // Configura listeners específicos de los spinners y autocompletes
        private fun setupSpinnerListeners() {
            // Al pulsar el campo de microfonía se abre un diálogo moderno con marcas/modelos
            spinnerMicrofonia.setOnClickListener {
                val currentPosition = bindingAdapterPosition
                if (isValidPosition(currentPosition)) {
                    showModernMicrofoniaDialog(currentPosition, canales[currentPosition].microfonia)
                }
            }
            // Desactivar entrada por teclado y usar touch para mostrar diálogo personalizado
            spinnerMicrofonia.keyListener = null
            spinnerMicrofonia.isFocusable = false
            spinnerMicrofonia.isClickable = true
            spinnerMicrofonia.setOnTouchListener { v, event ->
                if (event.action == MotionEvent.ACTION_UP) {
                    val currentPosition = bindingAdapterPosition
                    if (isValidPosition(currentPosition)) {
                        showModernMicrofoniaDialog(currentPosition, canales[currentPosition].microfonia)
                    }
                }
                true
            }

            // Listener para selección rápida desde la lista de FX
            spinnerFx.setOnItemClickListener { parent, view, pos, id ->
                val currentPosition = bindingAdapterPosition
                if (isValidPosition(currentPosition)) {
                    val canal = canales[currentPosition]
                    val newValue = parent.getItemAtPosition(pos) as String
                    canal.fx = newValue

                    // Si el canal ya está persistido, notificar el cambio para guardarlo
                    if (canal.id != -1) {
                        onCanalDataChangeListener?.invoke(canal.id, "fx", newValue)
                    }
                }
            }
        }

        // Muestra diálogo para seleccionar marca de micrófono y luego modelo
        private fun showModernMicrofoniaDialog(position: Int, currentValue: String) {
            val context = itemView.context
            // Verificar que la Activity asociada esté en estado válido para mostrar diálogos
            if (context is android.app.Activity && (context.isFinishing || context.isDestroyed)) {
                Log.w(TAG, "⚠️ No se puede mostrar diálogo: actividad no válida")
                return
            }

            val marcas = arrayOf(
                "🎤 Shure", "🎤 Sennheiser", "🎤 AKG", "🎤 Audio-Technica", "🎤 Neumann", "🎤 Rode",
                "🎤 DPA", "🎤 Beyerdynamic", "🎤 Electro-Voice", "🎤 Lewitt", "🎤 Telefunken",
                "🔧 Otros y Personalizados"
            )

            // Diálogo con estilo moderno (opaco) y lista de marcas
            AlertDialog.Builder(context, R.style.ModernDialogOpaque)
                .setTitle("Seleccionar Marca")
                .setIcon(R.drawable.ic_microphone)
                .setItems(marcas) { dialog, which ->
                    val marcaSeleccionada = marcas[which]

                    // Mostrar modelos según marca seleccionada
                    showModelosDialog(position, marcaSeleccionada)
                }
                .setNegativeButton("Cancelar", null)
                .show()
        }

        // Diálogo que muestra los modelos asociados a una marca y permite seleccionar o customizar
        private fun showModelosDialog(position: Int, marca: String) {
            val context = itemView.context
            // Listas ampliadas y profesionales por marca
            val modelosBase = when (marca) {
                "🎤 Shure" -> arrayOf(
                    "SM57", "SM58", "SM7B", "Beta 52A", "Beta 57A", "Beta 58A", "Beta 87A", "Beta 91A", "KSM9", "KSM32", "KSM44A", "KSM141", "KSM137", "SM81", "SM86", "SM87A", "VP88", "PG58", "PG81", "ULXD2", "BLX2", "MX418"
                )
                "🎤 Sennheiser" -> arrayOf(
                    "e835", "e845", "e865", "e935", "e945", "MD421", "MD441", "MK4", "MK8", "MKH 416", "MKH 418", "MKH 40", "MKH 50", "MKH 60", "MKE 600", "MKE 440", "MKE 200", "E602-II", "E604", "E609", "E614", "E904", "E906"
                )
                "🎤 AKG" -> arrayOf(
                    "C414 XLS", "C414 XLII", "C214", "C451B", "C1000S", "D112 MKII", "D5", "P120", "P170", "P220", "P420", "C3000", "C535", "C636", "C7", "D40", "D5S"
                )
                "🎤 Audio-Technica" -> arrayOf(
                    "AT2020", "AT2035", "AT2040", "AT2050", "AT3035", "AT4040", "AT4050", "AT4060", "ATM250", "ATM350", "ATM450", "ATM650", "ATM710", "AE5400", "AE6100", "PRO37", "PRO70", "PRO8HEx"
                )
                "🎤 Neumann" -> arrayOf(
                    "U87", "U87ai", "U67", "TLM102", "TLM103", "TLM107", "TLM49", "KM184", "KM185", "KMS104", "KMS105", "M149", "M150", "M147", "KMR81i", "KMR82i"
                )
                "🎤 Rode" -> arrayOf(
                    "NT1", "NT1-A", "NT2-A", "NT3", "NT4", "NT5", "NT55", "NTG1", "NTG2", "NTG3", "NTG4", "NTG5", "M1", "M2", "M3", "M5", "PodMic", "Procaster", "Broadcaster"
                )
                "🎤 DPA" -> arrayOf(
                    "d:facto", "d:vote 4099", "4060", "4061", "4066", "4088", "4011", "4015", "2011", "2028", "4098", "4090", "4091", "d:screet 4060", "d:screet 4061"
                )
                "🎤 Beyerdynamic" -> arrayOf(
                    "M88 TG", "M160", "M201 TG", "M69 TG", "M130", "TG V50d", "TG V70d", "TG I51", "TG D35d", "Opus 69", "Opus 81"
                )
                "🎤 Electro-Voice" -> arrayOf(
                    "RE20", "RE27N/D", "RE320", "PL20", "ND76", "ND86", "ND96", "PL44", "PL80a", "PL24S", "PL37"
                )
                "🎤 Lewitt" -> arrayOf(
                    "LCT 240 PRO", "LCT 440 PURE", "LCT 441 FLEX", "LCT 540 S", "LCT 640 TS", "MTP 250 DM", "MTP 350 CM", "MTP 440 DM", "MTP 550 DM", "MTP 940 CM"
                )
                "🎤 Telefunken" -> arrayOf(
                    "M80", "M81", "M82", "M60 FET", "CU-29 Copperhead", "AK-47 MkII", "AR-51", "ELA M 251E", "U47", "U48"
                )
                "🔧 Otros y Personalizados" -> arrayOf(
                    "Por definir", "No aplica", "Genérico dinámico", "Genérico condensador", "Genérico lavalier", "Genérico headset"
                )
                else -> arrayOf("Por definir", "No aplica")
            }
            // Siempre agregar la opción 'Personalizado' al final
            val modelos = modelosBase + arrayOf("Personalizado")

            AlertDialog.Builder(context, R.style.ModernDialogOpaque)
                .setTitle(marca)
                .setItems(modelos) { _, which ->
                    val modeloSeleccionado = modelos[which]
                    if (modeloSeleccionado == "Personalizado") {
                        showCustomMicrofoniaInput(position)
                    } else {
                        val currentPosition = bindingAdapterPosition
                        if (isValidPosition(currentPosition)) {
                            val canal = canales[currentPosition]
                            canal.microfonia = modeloSeleccionado
                            spinnerMicrofonia.setText(modeloSeleccionado)
                            // Notificar cambio para guardado si el canal ya existe en BD
                            if (canal.id != -1) {
                                onCanalDataChangeListener?.invoke(canal.id, "microfonia", modeloSeleccionado)
                            }
                        }
                    }
                }
                .setNegativeButton("Cancelar", null)
                .show()
        }

        // Muestra un dialogo con un EditText para ingresar un micrófono personalizado
        private fun showCustomMicrofoniaInput(position: Int) {
            val context = itemView.context
            val editText = EditText(context)
            editText.hint = "Escribe el modelo de micrófono"
            editText.setText(canales[position].microfonia)
            if (canales[position].microfonia.isNotEmpty()) {
                editText.selectAll()
            }

            AlertDialog.Builder(context)
                .setTitle("Micrófono personalizado")
                .setView(editText)
                .setPositiveButton("Guardar") { _, _ ->
                    val customValue = editText.text.toString().trim()
                    if (customValue.isNotEmpty()) {
                        val currentPosition = bindingAdapterPosition
                        if (isValidPosition(currentPosition)) {
                            val canal = canales[currentPosition]
                            canal.microfonia = customValue
                            spinnerMicrofonia.setText(customValue)
                            if (canal.id != -1) {
                                onCanalDataChangeListener?.invoke(canal.id, "microfonia", customValue)
                            }
                        }
                    }
                }
                .setNegativeButton("Cancelar", null)
                .show()

            // Mostrar teclado automáticamente
            editText.post {
                editText.requestFocus()
                val imm = context.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
                imm.showSoftInput(editText, InputMethodManager.SHOW_IMPLICIT)
            }
        }

        // Diálogo rápido para editar el nombre del canal (muestra un EditText simple)
        private fun showQuickEditDialog(position: Int, currentName: String) {
            val context = itemView.context
            // Verificar que la Activity esté en estado válido
            if (context is android.app.Activity && (context.isFinishing || context.isDestroyed)) {
                Log.w(TAG, "⚠️ No se puede mostrar diálogo: actividad no válida")
                return
            }

            val editText = EditText(context)
            editText.setText(currentName)
            editText.hint = "Nombre del canal"
            editText.selectAll()

            try {
                val dialog = AlertDialog.Builder(context)
                    .setTitle("Editar nombre del canal")
                    .setView(editText)
                    .setPositiveButton("Guardar") { dialog, which ->
                        val newName = editText.text.toString().trim()
                        if (newName.isNotEmpty()) {
                            val canal = canales[position]
                            canal.nombre = newName
                            textViewNombre.text = newName

                            // Notificar cambio de nombre para persistencia
                            if (canal.id != -1) {
                                onCanalDataChangeListener?.invoke(canal.id, "nombre", newName)
                            }
                        }
                    }
                    .setNegativeButton("Cancelar", null)
                    .create()

                // Mostrar teclado y solicitar foco al EditText tras mostrar el diálogo
                if (context is android.app.Activity && !context.isFinishing && !context.isDestroyed) {
                    dialog.show()
                    editText.post {
                        editText.requestFocus()
                        val imm = context.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
                        imm.showSoftInput(editText, InputMethodManager.SHOW_IMPLICIT)
                    }
                }
            } catch (e: Exception) {
                // Capturar errores inesperados al crear/mostrar el diálogo
                Log.e(TAG, "❌ Error al mostrar diálogo de edición: ${e.message}", e)
            }
        }

        // Configura listeners generales del ViewHolder (nombre, fader, delete, expand, drag)
        private fun setupListeners() {
            // Al pulsar el número se rota el color del canal entre una paleta definida
            textViewNumero.setOnClickListener {
                val currentPosition = bindingAdapterPosition
                if (isValidPosition(currentPosition)) {
                    val colorValues = itemView.resources.getIntArray(R.array.color_values)
                    val currentColor = canales[currentPosition].color
                    val currentIndex = colorValues.indexOf(currentColor)
                    val nextIndex = (currentIndex + 1) % colorValues.size
                    canales[currentPosition].color = colorValues[nextIndex]
                    applyColors(canales[currentPosition])
                    onColorChangeListener?.invoke(currentPosition, colorValues[nextIndex])
                }
            }

            // Click en el nombre abre un diálogo rápido para editarlo
            textViewNombre.setOnClickListener {
                val currentPosition = bindingAdapterPosition
                val context = itemView.context
                if (isValidPosition(currentPosition) &&
                    !(context is android.app.Activity && (context.isFinishing || context.isDestroyed))) {
                    showQuickEditDialog(currentPosition, canales[currentPosition].nombre)
                }
            }

            // Listener del fader: mientras se arrastra notifica cambios graduales y al soltar notifica final
            seekBarListener = object : SeekBar.OnSeekBarChangeListener {
                override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                    if (fromUser && isValidPosition(bindingAdapterPosition)) {
                        val currentPosition = bindingAdapterPosition
                        val canal = canales[currentPosition]
                        val oldLevel = canal.faderLevel
                        canal.faderLevel = progress

                        if (oldLevel != progress) {
                            onFaderChangeListener?.invoke(canal.id, progress, false)
                        }
                    }
                }

                override fun onStartTrackingTouch(seekBar: SeekBar?) {
                    // Al empezar a mover el fader se contraen todos los canales para enfocarse en el actual
                    this@CanalAdapter.compressAllCanals()
                }

                override fun onStopTrackingTouch(seekBar: SeekBar?) {
                    val currentPosition = bindingAdapterPosition
                    if (isValidPosition(currentPosition)) {
                        val canal = canales[currentPosition]
                        // Notificar cambio final del fader (isFinalChange = true)
                        onFaderChangeListener?.invoke(canal.id, canal.faderLevel, true)
                    }
                }
            }
            seekBarFader.setOnSeekBarChangeListener(seekBarListener)

            // Botón eliminar: delega al listener externo
            buttonDelete.setOnClickListener {
                val currentPosition = bindingAdapterPosition
                if (currentPosition in 0 until canales.size) {
                    onDeleteClickListener.onDeleteClick(currentPosition)
                }
            }

            // Botón de expand/colapsar: gestiona visibilidad de `contentLayout` y animación de icono
            btnExpand.setOnClickListener {
                val currentPosition = bindingAdapterPosition
                val currentVisibility = contentLayout.visibility
                this@CanalAdapter.compressAllCanals()

                if (currentVisibility == View.GONE) {
                    // Mostrar detalles y desplazar suavemente al item
                    contentLayout.visibility = View.VISIBLE
                    itemView.post {
                        notifyItemChanged(currentPosition)
                        recyclerView.post { recyclerView.smoothScrollToPosition(currentPosition) }
                    }
                    btnExpand.setImageResource(android.R.drawable.ic_delete)
                    expandedPosition = currentPosition
                } else {
                    // Ocultar detalles
                    contentLayout.visibility = View.GONE
                    btnExpand.setImageResource(android.R.drawable.ic_input_add)
                    expandedPosition = -1
                }
                itemView.requestLayout()
            }

            // Handle para iniciar drag mediante ItemTouchHelper
            btnDragHandle.setOnLongClickListener {
                val currentPosition = bindingAdapterPosition
                if (currentPosition != RecyclerView.NO_POSITION &&
                    currentPosition >= 0 &&
                    currentPosition < canales.size &&
                    itemView.parent != null &&
                    isValidAdapterPosition(this@CanalViewHolder) &&
                    itemTouchHelper != null) {
                    try {
                        itemTouchHelper?.startDrag(this@CanalViewHolder)
                        true
                    } catch (e: Exception) {
                        Log.e(TAG, "❌ Error al iniciar drag: ${e.message}", e)
                        false
                    }
                } else {
                    Log.w(TAG, "⚠️ No se puede arrastrar: posición=$currentPosition, tamaño=${canales.size}, parent=${itemView.parent}")
                    false
                }
            }

            btnDragHandle.isLongClickable = true
        }
    }
}
