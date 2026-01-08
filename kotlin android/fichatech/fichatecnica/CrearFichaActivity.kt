package com.cepalabsfree.fichatech.fichatecnica

import android.animation.ObjectAnimator
import android.animation.PropertyValuesHolder
import android.app.AlertDialog
import android.content.Context
import android.content.Intent
import android.graphics.Rect
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.MotionEvent
import android.view.View
import android.view.inputmethod.InputMethodManager
import android.widget.EditText
import android.widget.Toast
import androidx.activity.addCallback
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.widget.Toolbar
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.recyclerview.widget.ItemTouchHelper
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.cepalabsfree.fichatech.R
import com.cepalabsfree.fichatech.databinding.ActivityCrearFichaBinding
import kotlinx.coroutines.*

class CrearFichaActivity : AppCompatActivity() {
    // Binding generado por ViewBinding para acceder a las vistas del layout de forma segura
    private lateinit var binding: ActivityCrearFichaBinding

    // Helper para operaciones con la base de datos (CRUD de fichas y canales)
    private lateinit var dbHelper: FichaDatabaseHelper

    // Componente responsable de programar/ejecutar guardados asíncronos en segundo plano
    // Se asume que `FichaSaver` expone métodos para programar guardados, flush, etc.
    private lateinit var fichaSaver: FichaSaver

    // Lista en memoria de los canales que se muestran en el RecyclerView
    private val canales = mutableListOf<Canal>()

    // Adapter del RecyclerView que renderiza canales y expone callbacks para edición/eliminación
    private lateinit var canalAdapter: CanalAdapter

    // Referencias a botones del layout (se inicializan en setupViews)
    private lateinit var btnAgregarCanal: View
    private lateinit var btnGuardar: View

    // Scope para coroutines ligadas al ciclo de vida de la Activity (MainThread por defecto)
    private val scope = MainScope()

    // ID de la ficha en la base de datos; -1 indica que aún no se ha persistido
    private var fichaId: Long = -1L

    // Job usado para agrupar/posponer guardados de orden de canales y evitar llamadas excesivas
    private var orderSaveJob: Job? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Log.d("CrearFichaActivity", "🅕 onCreate() - savedInstanceState: ${savedInstanceState != null}")

        // Habilita Edge-to-Edge ANTES de setContentView (requerido en Android 15)
        enableEdgeToEdge()

        // Inicializar ViewBinding
        binding = ActivityCrearFichaBinding.inflate(layoutInflater)
        setContentView(binding.root)

        if (savedInstanceState != null) {
            Log.d("CrearFichaActivity", "📦 Restaurando desde savedInstanceState")

            // Restaurar datos básicos
            savedInstanceState.getString("NOMBRE_FICHA")?.let {
                binding.etNombreFicha1.setText(it)
            }
            savedInstanceState.getString("DESCRIPCION_FICHA")?.let {
                binding.etDescripcionFicha1.setText(it)
            }
            fichaId = savedInstanceState.getLong("FICHA_ID", -1L)

            // Restaurar canales
            @Suppress("DEPRECATION")
            val canalesRestored: ArrayList<Canal>? = savedInstanceState.getParcelableArrayList("CANALES_DATA")
            if (canalesRestored != null) {
                Log.d("CrearFichaActivity", "📦 Canales restaurados: ${canalesRestored.size}")
                canales.clear()
                canales.addAll(canalesRestored)
            }
        }

        // 3. LUEGO configurar todo lo demás
        setupWindowInsets()
        setupToolbar()
        setupDatabase()
        setupViews()
        setupRecyclerView()
        setupEventListeners()
        setupBackHandler()

        Log.d("CrearFichaActivity", "✅ onCreate completado - Canales: ${canales.size}")
    }

    // Configura la barra superior (toolbar) y maneja la navegación hacia atrás
    private fun setupToolbar() {
        val toolbar: Toolbar = findViewById(R.id.toolbar)
        setSupportActionBar(toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.setDisplayShowHomeEnabled(true)
        toolbar.setNavigationOnClickListener {
            // Delegar el comportamiento de back al onBackPressedDispatcher para centralizar la lógica
            onBackPressedDispatcher.onBackPressed()
        }
    }

    // Inicializa el helper de BD y el servicio/objeto que se encarga de persistencia asíncrona
    private fun setupDatabase() {
        dbHelper = FichaDatabaseHelper(this)
        fichaSaver = FichaSaver
    }

    // Configura referencias a vistas y animaciones iniciales
    private fun setupViews() {
        btnAgregarCanal = findViewById(R.id.btnAgregarCanal)
        btnGuardar = findViewById(R.id.btnGuardar)

        // Animación de pulso para el botón Agregar Canal (mejora UX)
        // Se lanza con un pequeño delay para que la UI esté lista
        btnAgregarCanal.post {
            Handler(Looper.getMainLooper()).postDelayed({
                ObjectAnimator.ofPropertyValuesHolder(
                    btnAgregarCanal,
                    PropertyValuesHolder.ofFloat("scaleX", 1.0f, 1.1f),
                    PropertyValuesHolder.ofFloat("scaleY", 1.0f, 1.1f)
                ).apply {
                    duration = 800
                    repeatMode = ObjectAnimator.REVERSE
                    repeatCount = ObjectAnimator.INFINITE
                    start()
                }
            }, 500)
        }
    }

    // Inicializa el RecyclerView que muestra los canales y configura el adapter
    private fun setupRecyclerView() {
        val recyclerViewCanales = findViewById<RecyclerView>(R.id.rvCanales)

        recyclerViewCanales.setHasFixedSize(false)
        recyclerViewCanales.setItemViewCacheSize(30)
        recyclerViewCanales.setRecycledViewPool(SharedViewPool.getPool())
        recyclerViewCanales.itemAnimator = null

        val layoutManager = LinearLayoutManager(this, LinearLayoutManager.HORIZONTAL, false)
        layoutManager.isItemPrefetchEnabled = false
        recyclerViewCanales.layoutManager = layoutManager

        // IMPORTANTE: El adapter debe recibir la lista ACTUAL de canales
        // (que puede estar vacía o tener datos restaurados)
        canalAdapter = CanalAdapter(canales, object : CanalAdapter.OnDeleteClickListener {
            override fun onDeleteClick(position: Int) {
                mostrarConfirmacionEliminacion(position)
            }
        }, recyclerViewCanales) { canalId, level, isFinalChange ->
            fichaSaver.programarGuardadoFader(dbHelper, canalId, level, isFinalChange)
        }

        canalAdapter.setOnCanalDataChangeListener { canalId, field, value ->
            if (canalId != -1) {
                fichaSaver.programarGuardadoCampo(dbHelper, canalId, field, value)
            }
        }

        canalAdapter.setOnColorChangeListener { position, color ->
            if (position in canales.indices) {
                val canal = canales[position]
                canal.color = color

                if (canal.id != -1) {
                    fichaSaver.programarGuardadoCampo(dbHelper, canal.id, "color", color)
                }
            }
        }

        recyclerViewCanales.adapter = canalAdapter

        // Si hay canales restaurados, notificar al adapter
        if (canales.isNotEmpty()) {
            Log.d("CrearFichaActivity", "📊 Notificando adapter con ${canales.size} canales restaurados")
            canalAdapter.notifyDataSetChanged()
        }

        setupItemTouchHelper()
    }
    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        Log.d("CrearFichaActivity", "💾 Guardando estado - Canales: ${canales.size}")

        // Guardar nombre y descripción
        outState.putString("NOMBRE_FICHA", binding.etNombreFicha1.text.toString())
        outState.putString("DESCRIPCION_FICHA", binding.etDescripcionFicha1.text.toString())

        // Guardar ID de ficha
        if (fichaId != -1L) {
            outState.putLong("FICHA_ID", fichaId)
        }

        // Guardar canales
        outState.putParcelableArrayList("CANALES_DATA", ArrayList(canales))

        // Debug: mostrar qué se está guardando
        Log.d("CrearFichaActivity", "📝 Estado guardado:")
        Log.d("CrearFichaActivity", "   Nombre: ${binding.etNombreFicha1.text}")
        Log.d("CrearFichaActivity", "   Descripción: ${binding.etDescripcionFicha1.text}")
        Log.d("CrearFichaActivity", "   Ficha ID: $fichaId")
        Log.d("CrearFichaActivity", "   Canales: ${canales.size}")
        canales.forEachIndexed { index, canal ->
            Log.d("CrearFichaActivity", "     Canal[$index]: id=${canal.id}, nombre='${canal.nombre}'")
        }
    }

    override fun onRestoreInstanceState(savedInstanceState: Bundle) {
        super.onRestoreInstanceState(savedInstanceState)
        Log.d("CrearFichaActivity", "🔄 Restaurando estado...")

        savedInstanceState.let { bundle ->
            // ... (código anterior para restaurar nombre, descripción, fichaId)

            // Restaurar canales
            @Suppress("DEPRECATION")
            val canalesRestored: ArrayList<Canal>? = bundle.getParcelableArrayList("CANALES_DATA")
            if (canalesRestored != null) {
                Log.d("CrearFichaActivity", "📦 Canales restaurados del Bundle: ${canalesRestored.size}")

                // Debug detallado de canales restaurados
                canalesRestored.forEachIndexed { index, canal ->
                    Log.d("CrearFichaActivity", "   📋 Canal[$index]: id=${canal.id}, nombre='${canal.nombre}', numero=${canal.numeroCanal}")
                }

                // ✅ Actualizar adapter PRIMERO con los canales restaurados
                canalAdapter.updateCanales(canalesRestored)

                // ✅ LUEGO actualizar la lista local
                canales.clear()
                canales.addAll(canalesRestored)

                // Debug del estado del adapter después de la actualización
                canalAdapter.debugEstadoAdapter()

                Log.d("CrearFichaActivity", "✅ Estado restaurado - Canales locales: ${canales.size}, Ficha ID: $fichaId")
            } else {
                Log.e("CrearFichaActivity", "❌ ERROR: No se encontraron canales en el Bundle")
            }
        }
    }

    private fun reasignarIdsTemporales() {
        // Notificar al adapter que debe manejar los IDs temporales
        canalAdapter.updateCanales(canales)

        // Si la ficha ya tiene ID, insertar canales pendientes en BD
        if (fichaId != -1L) {
            scope.launch {
                canales.forEachIndexed { index, canal ->
                    if (canal.id == -1) {
                        fichaSaver.programarInsercionCanal(
                            dbHelper,
                            fichaId.toInt(),
                            canal,
                            index
                        ) { nuevoId ->
                            canal.id = nuevoId
                            canalAdapter.notifyItemChanged(index)
                        }
                    }
                }
            }
        }
    }
    // Configura el ItemTouchHelper para arrastrar/reordenar canales
    private fun setupItemTouchHelper() {
        val callback = object : ItemTouchHelper.SimpleCallback(
            ItemTouchHelper.LEFT or ItemTouchHelper.RIGHT, 0
        ) {
            override fun onMove(
                recyclerView: RecyclerView,
                viewHolder: RecyclerView.ViewHolder,
                target: RecyclerView.ViewHolder
            ): Boolean {
                val fromPos = viewHolder.bindingAdapterPosition
                val toPos = target.bindingAdapterPosition

                // Validar índices antes de mover en la lista
                if (fromPos in canales.indices && toPos in canales.indices) {
                    canalAdapter.moveCanal(fromPos, toPos)
                    return true
                }
                return false
            }

            override fun onSwiped(viewHolder: RecyclerView.ViewHolder, direction: Int) {}

            // Se deshabilita arrastre por long press para usar un handle personalizado en el ViewHolder
            override fun isLongPressDragEnabled(): Boolean = false

            override fun onSelectedChanged(viewHolder: RecyclerView.ViewHolder?, actionState: Int) {
                super.onSelectedChanged(viewHolder, actionState)
                when (actionState) {
                    ItemTouchHelper.ACTION_STATE_DRAG -> {
                        // Efecto visual cuando empieza el drag: elevar y escalar la vista
                        viewHolder?.itemView?.apply {
                            animate().cancel()
                            translationZ = 16f
                            scaleX = 1.03f
                            scaleY = 1.03f
                            alpha = 0.95f
                            setLayerType(View.LAYER_TYPE_HARDWARE, null)
                        }
                    }
                }
            }

            override fun clearView(recyclerView: RecyclerView, viewHolder: RecyclerView.ViewHolder) {
                super.clearView(recyclerView, viewHolder)
                // Restaurar propiedades visuales al finalizar el drag
                viewHolder.itemView.apply {
                    animate()
                        .translationZ(0f)
                        .scaleX(1.0f)
                        .scaleY(1.0f)
                        .alpha(1.0f)
                        .setDuration(150)
                        .withEndAction {
                            setLayerType(View.LAYER_TYPE_NONE, null)
                        }
                        .start()
                }

                // Después de un pequeño delay, actualizar numeración y guardar orden si aplica
                recyclerView.postDelayed({
                    canalAdapter.refreshNumerationDebounced()
                    saveCanalOrder()
                }, 100)
            }

            override fun getMoveThreshold(viewHolder: RecyclerView.ViewHolder): Float {
                // Umbral de movimiento para iniciar el reorder
                return 0.2f
            }

            override fun getAnimationDuration(
                recyclerView: RecyclerView,
                animationType: Int,
                animateDx: Float,
                animateDy: Float
            ): Long {
                // Duración corta para hacer la experiencia de arrastre más responsiva
                return 150
            }
        }

        val itemTouchHelper = ItemTouchHelper(callback)
        itemTouchHelper.attachToRecyclerView(binding.rvCanales)
        canalAdapter.setItemTouchHelper(itemTouchHelper)
    }

    // Registra listeners de botones y otras interacciones de UI
    private fun setupEventListeners() {
        btnAgregarCanal.setOnClickListener {
            agregarCanal()
        }

        btnGuardar.setOnClickListener {
            guardarFichaSiCamposValidos()
        }

        setupDynamicHints()
    }

    // Maneja hints dinámicos: ocultarlos al enfocar y restaurarlos si están vacíos
    private fun setupDynamicHints() {
        binding.etNombreFicha1.setOnFocusChangeListener { _, hasFocus ->
            if (hasFocus) {
                binding.etNombreFicha1.hint = ""
            } else {
                if (binding.etNombreFicha1.text.isNullOrEmpty()) {
                    binding.etNombreFicha1.hint = getString(R.string.nombreficha)
                }
            }
        }

        binding.etDescripcionFicha1.setOnFocusChangeListener { _, hasFocus ->
            if (hasFocus) {
                binding.etDescripcionFicha1.hint = ""
            } else {
                if (binding.etDescripcionFicha1.text.isNullOrEmpty()) {
                    binding.etDescripcionFicha1.hint = "Descripción"
                }
            }
        }
    }

    // Maneja la acción de retroceso; si hay cambios sin guardar muestra confirmaciones
    private fun setupBackHandler() {
        onBackPressedDispatcher.addCallback(this) {
            if (hasUnsavedChanges()) {
                val nombre = binding.etNombreFicha1.text.toString().trim()

                if (nombre.isNotEmpty()) {
                    // Si ya hay nombre, pedir guardar/descartar/cancelar
                    mostrarDialogoConfirmacionSalida()
                } else {
                    // Si no hay nombre, informar que la ficha necesita un nombre para guardarse
                    AlertDialog.Builder(this@CrearFichaActivity)
                        .setTitle("Descartar cambios")
                        .setMessage("¿Salir sin guardar?")
                        .setPositiveButton("Sí") { _, _ -> finish() }
                        .setNegativeButton("No", null)
                        .show()
                }
            } else {
                finish()
            }
        }
    }

    // Ajusta padding de vistas para respetar insets (status bar, navigation bar)
    private fun setupWindowInsets() {
        ViewCompat.setOnApplyWindowInsetsListener(binding.root) { _, windowInsets ->
            val systemInsets = windowInsets.getInsets(WindowInsetsCompat.Type.systemBars())

            val appBarLayout = findViewById<com.google.android.material.appbar.AppBarLayout>(R.id.appBarLayout)
            appBarLayout.setPadding(systemInsets.left, systemInsets.top, systemInsets.right, 0)

            val toolbar = findViewById<androidx.appcompat.widget.Toolbar>(R.id.toolbar)
            toolbar.setPadding(systemInsets.left, 0, systemInsets.right, 0)

            val nestedScrollView = findViewById<androidx.core.widget.NestedScrollView>(R.id.scrollView)
            nestedScrollView.setPadding(systemInsets.left, 0, systemInsets.right, systemInsets.bottom)

            WindowInsetsCompat.CONSUMED
        }
    }

    // Comprueba si hay cambios en los campos que deben provocar advertencia al salir
    private fun hasUnsavedChanges(): Boolean {
        val nombre = binding.etNombreFicha1.text.toString()
        val descripcion = binding.etDescripcionFicha1.text.toString()
        return nombre.isNotEmpty() || descripcion.isNotEmpty() || canales.isNotEmpty()
    }

    // Muestra un diálogo que pregunta al usuario si desea guardar, descartar o cancelar
    private fun mostrarDialogoConfirmacionSalida() {
        AlertDialog.Builder(this)
            .setTitle("¿Guardar cambios?")
            .setMessage("Tienes cambios sin guardar")
            .setPositiveButton("Guardar") { _, _ ->
                guardarFichaSiCamposValidos()
            }
            .setNegativeButton("Descartar") { _, _ ->
                finish()
            }
            .setNeutralButton("Cancelar") { dialog, _ ->
                dialog.dismiss()
            }
            .show()
    }

    // Valida campos básicos antes de intentar persistir la ficha
    private fun validarDatosFicha(): Boolean {
        val nombre = binding.etNombreFicha1.text.toString().trim()

        if (nombre.isEmpty()) {
            Toast.makeText(this, "El nombre de la ficha es obligatorio", Toast.LENGTH_SHORT).show()
            binding.etNombreFicha1.requestFocus()
            return false
        }

        // Evitar nombres de canal duplicados (solo canales con nombre no vacío)
        val nombresCanales = canales.map { it.nombre.trim() }.filter { it.isNotEmpty() }
        if (nombresCanales.distinct().size != nombresCanales.size) {
            Toast.makeText(this, "Hay nombres de canal duplicados", Toast.LENGTH_SHORT).show()
            return false
        }

        return true
    }

    // Intento de guardado completo: muestra progress, lanza coroutine y maneja resultado
    private fun guardarFichaSiCamposValidos() {
        if (!validarDatosFicha()) return

        val nombreFicha = binding.etNombreFicha1.text.toString()
        val descripcionFicha = binding.etDescripcionFicha1.text.toString()

        val progressDialog = AlertDialog.Builder(this)
            .setTitle("Guardando ficha...")
            .setMessage("Por favor, espere")
            .setCancelable(false)
            .create()

        progressDialog.show()

        scope.launch {
            val exito = try {
                // Timeout razonable para evitar colgar la UI indefinidamente
                withTimeout(5000) {
                    guardarFicha(nombreFicha, descripcionFicha)
                }
            } catch (e: TimeoutCancellationException) {
                Log.e("CrearFicha", "❌ Timeout al guardar ficha", e)
                false
            } catch (e: Exception) {
                Log.e("CrearFicha", "❌ Error al guardar ficha", e)
                false
            }

            withContext(Dispatchers.Main) {
                progressDialog.dismiss()

                if (exito) {
                    Toast.makeText(
                        this@CrearFichaActivity,
                        "Ficha creada correctamente",
                        Toast.LENGTH_SHORT
                    ).show()

                    // Forzar sincronización de operaciones pendientes antes de terminar
                    fichaSaver.flushTodo(dbHelper)

                    // Guardar orden final de canales en BD
                    fichaSaver.guardarOrdenCanales(dbHelper, fichaId.toInt(), canales)

                    // Retornar el ID de la ficha al Activity llamante y cerrar
                    Handler(Looper.getMainLooper()).postDelayed({
                        val resultIntent = Intent().apply {
                            putExtra("fichaId", fichaId.toInt())
                        }
                        setResult(RESULT_OK, resultIntent)
                        finish()
                    }, 300)

                } else {
                    // Manejo simple de error con opción para reintentar
                    Toast.makeText(
                        this@CrearFichaActivity,
                        "Error al crear la ficha",
                        Toast.LENGTH_SHORT
                    ).show()

                    AlertDialog.Builder(this@CrearFichaActivity)
                        .setTitle("Error al guardar")
                        .setMessage("¿Deseas intentar nuevamente?")
                        .setPositiveButton("Sí") { _, _ ->
                            guardarFichaSiCamposValidos()
                        }
                        .setNegativeButton("No") { _, _ -> }
                        .setNeutralButton("Salir sin guardar") { _, _ ->
                            finish()
                        }
                        .show()
                }
            }
        }
    }

    // Función suspend que delega la creación completa de ficha a fichaSaver y guarda el ID
    private suspend fun guardarFicha(nombre: String, descripcion: String): Boolean {
        return fichaSaver.crearFichaCompleta(dbHelper, nombre, descripcion, canales).let { fichaId ->
            if (fichaId != -1) {
                this.fichaId = fichaId.toLong()
                true
            } else {
                false
            }
        }
    }

    // Añade un canal nuevo a la lista y lo persiste si la ficha ya existe
    private fun agregarCanal() {
        // Límite de 16 canales en la versión gratuita
        if (canales.size >= 16) {  // ← CAMBIAR A: canales.size > 16
            mostrarLimiteCanalesDialog()
            return
        }

        val nuevoCanal = Canal(-1, canales.size + 1, "", "", "", 0, 0)
        val posicion = canales.size

        canales.add(nuevoCanal)
        canalAdapter.notifyItemInserted(posicion)
        binding.rvCanales.scrollToPosition(posicion)

        // Si la ficha ya tiene ID en BD, insertar canal en background y actualizar su ID real
        if (fichaId != -1L) {
            fichaSaver.programarInsercionCanal(dbHelper, fichaId.toInt(), nuevoCanal, posicion) { nuevoId ->
                nuevoCanal.id = nuevoId
                canalAdapter.notifyItemChanged(posicion)
            }
        }
    }

    // Muestra diálogo informando límite de canales y propone actualizar a Pro
    private fun mostrarLimiteCanalesDialog() {
        AlertDialog.Builder(this)
            .setTitle("Límite alcanzado")
            .setMessage("La versión gratuita permite un máximo de 16 canales.\n\n" +
                    "Para agregar más canales, actualiza a la versión Pro de Fichatech.")
            .setPositiveButton("Entendido", null)
            .setNegativeButton("Actualizar a Pro") { _, _ ->
                abrirAppProEnGooglePlay()
            }
            .show()
    }

    // Intenta abrir la app Pro en Google Play; si falla, abre la url web o muestra un Toast
    private fun abrirAppProEnGooglePlay() {
        try {
            val intent = Intent(Intent.ACTION_VIEW).apply {
                data = Uri.parse("market://details?id=com.cepalabs.fichatech")
                flags = Intent.FLAG_ACTIVITY_NEW_TASK
            }
            startActivity(intent)
        } catch (e: android.content.ActivityNotFoundException) {
            try {
                val intent = Intent(Intent.ACTION_VIEW).apply {
                    data = Uri.parse("https://play.google.com/store/apps/details?id=com.cepalabs.fichatech&hl=es_CL")
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                startActivity(intent)
            } catch (e2: Exception) {
                Toast.makeText(this,
                    "No se pudo abrir Google Play. Visita: play.google.com/store/apps/details?id=com.cepalabs.fichatech",
                    Toast.LENGTH_LONG).show()
            }
        }
    }

    // Pide confirmación antes de eliminar un canal (muestra el número de canal)
    private fun mostrarConfirmacionEliminacion(position: Int) {
        val canal = canales[position]
        AlertDialog.Builder(this)
            .setTitle("Confirmación")
            .setMessage("¿Estás seguro de que deseas eliminar el Canal #${canal.numeroCanal}?")
            .setPositiveButton("Sí") { _, _ ->
                eliminarCanal(position)
            }
            .setNegativeButton("No", null)
            .show()
    }

    // Elimina un canal de la lista y (si corresponde) también de la base de datos
    private fun eliminarCanal(position: Int) {
        if (position !in canales.indices) {
            Log.w("CrearFichaActivity", "Posición inválida para eliminar: $position")
            return
        }

        val canal = canales[position]

        // Si el canal ya existía en BD, solicitar eliminación asíncrona
        if (canal.id != -1) {
            scope.launch {
                fichaSaver.eliminarCanal(dbHelper, canal.id)
            }
        }

        // Actualizar lista en memoria y notificar al adapter
        canales.removeAt(position)
        actualizarNumeracionCanales()
        canalAdapter.notifyItemRemoved(position)

        if (position < canales.size) {
            canalAdapter.notifyItemRangeChanged(position, canales.size - position)
        }
    }

    // Recalcula el número mostrado de cada canal (1-based) después de reordenar/eliminar
    private fun actualizarNumeracionCanales() {
        canales.forEachIndexed { index, canal ->
            canal.numeroCanal = index + 1
        }
    }

    // Guarda el orden de canales en BD con debounce para evitar llamadas repetidas
    private fun saveCanalOrder() {
        orderSaveJob?.cancel()
        orderSaveJob = scope.launch(Dispatchers.IO) {
            delay(300)
            if (fichaId != -1L) {
                fichaSaver.guardarOrdenCanales(dbHelper, fichaId.toInt(), canales)
            }
        }
    }

    // Cuando la Activity pasa a segundo plano, forzar flush de operaciones pendientes
    override fun onPause() {
        super.onPause()
        scope.launch {
            fichaSaver.flushTodo(dbHelper)
        }
    }

    // Cleanup: cancelar trabajos pendientes, cerrar BD y liberar scope de coroutines
    override fun onDestroy() {
        fichaSaver.cancelarTodo()
        scope.cancel()
        dbHelper.close()
        super.onDestroy()
    }



    // Cierra el teclado al tocar fuera del EditText
    override fun dispatchTouchEvent(event: MotionEvent?): Boolean {
        val result = super.dispatchTouchEvent(event)
        event?.let {
            if (it.action == MotionEvent.ACTION_DOWN) {
                val view = currentFocus
                if (view is EditText) {
                    val outRect = Rect()
                    view.getGlobalVisibleRect(outRect)
                    if (!outRect.contains(it.rawX.toInt(), it.rawY.toInt())) {
                        view.clearFocus()
                        // Cerrar el teclado
                        val imm = getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
                        imm.hideSoftInputFromWindow(view.windowToken, 0)
                    }
                }
            }
        }
        return result
    }
}
