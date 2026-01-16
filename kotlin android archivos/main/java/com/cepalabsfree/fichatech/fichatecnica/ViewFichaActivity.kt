package com.cepalabsfree.fichatech.fichatecnica

import android.content.ContentValues
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.util.Log
import android.view.View
import android.widget.EditText
import android.widget.Toast
import androidx.activity.addCallback
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.widget.Toolbar
import androidx.coordinatorlayout.widget.CoordinatorLayout
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.core.view.WindowInsetsCompat
import androidx.recyclerview.widget.ItemTouchHelper
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.cepalabsfree.fichatech.R
import com.google.android.material.appbar.AppBarLayout
import kotlinx.coroutines.*

class ViewFichaActivity : AppCompatActivity(), CanalAdapter.OnDeleteClickListener {
    private lateinit var fichaDatabaseHelper: FichaDatabaseHelper
    private lateinit var fichaSaver: FichaSaver
    private var ficha: Ficha? = null
    private var canales: MutableList<Canal> = mutableListOf()
    private lateinit var editTextNombre: EditText
    private lateinit var editTextDescripcion: EditText
    private lateinit var recyclerViewCanales: RecyclerView
    private lateinit var canalAdapter: CanalAdapter
    private lateinit var agregarCanalButton: View
    private var orderSaveJob: Job? = null

    private val scope = MainScope()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()


        setContentView(R.layout.activity_view_ficha)

        setupWindowInsets()
        initViews()
        setupDatabase()
        setupRecyclerView()
        setupEventListeners()
        setupBackHandler()

        loadDatabaseAsync()
    }

    private fun initViews() {
        val toolbar: Toolbar = findViewById(R.id.toolbar)
        setSupportActionBar(toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.setDisplayShowHomeEnabled(true)
        toolbar.setNavigationOnClickListener {
            onBackPressedDispatcher.onBackPressed()
        }

        editTextNombre = findViewById(R.id.etNombreFicha1)
        editTextDescripcion = findViewById(R.id.etDescripcionFicha1)
        agregarCanalButton = findViewById(R.id.btnAgregarCanal)
    }

    private fun setupDatabase() {
        fichaDatabaseHelper = FichaDatabaseHelper(this)
        fichaSaver = FichaSaver
    }

    private fun loadDatabaseAsync() {
        val fichaId = intent.getIntExtra("fichaId", -1)
        if (fichaId == -1) {
            Toast.makeText(this, "Error: Ficha no encontrada", Toast.LENGTH_SHORT).show()
            finish()
            return
        }

        scope.launch(Dispatchers.IO) {
            try {
                val fichaWithCanales = fichaDatabaseHelper.getFichaWithCanales(fichaId)

                withContext(Dispatchers.Main) {
                    if (fichaWithCanales != null) {
                        ficha = fichaWithCanales.ficha
                        canales.clear()
                        canales.addAll(fichaWithCanales.canales)

                        editTextNombre.setText(ficha?.nombre.orEmpty())
                        editTextDescripcion.setText(ficha?.descripcion.orEmpty())

                        editTextNombre.isEnabled = false
                        editTextDescripcion.isEnabled = false

                        canalAdapter.notifyDataSetChanged()
                        Log.d("ViewFichaActivity", "✅ Canales cargados: ${canales.size}")
                    } else {
                        Toast.makeText(this@ViewFichaActivity, "Error: Ficha no encontrada", Toast.LENGTH_SHORT).show()
                        finish()
                    }
                }
            } catch (e: Exception) {
                Log.e("ViewFichaActivity", "Error cargando datos", e)
                withContext(Dispatchers.Main) {
                    Toast.makeText(this@ViewFichaActivity, "Error al cargar la ficha", Toast.LENGTH_SHORT).show()
                    finish()
                }
            }
        }
    }
    private fun hideSystemBars() {
        // Ocultar las barras del sistema (status bar y navigation bar)
        val windowInsetsController = androidx.core.view.WindowCompat.getInsetsController(window, window.decorView)
        windowInsetsController?.let {
            // Ocultar barras de estado y navegación
            it.hide(androidx.core.view.WindowInsetsCompat.Type.systemBars())
            // Comportamiento: las barras reaparecen cuando el usuario interactúa
            it.systemBarsBehavior = androidx.core.view.WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        }
    }
    private fun setupRecyclerView() {
        recyclerViewCanales = findViewById(R.id.canalesContainer)

        recyclerViewCanales.setHasFixedSize(false)
        recyclerViewCanales.setItemViewCacheSize(30)
        recyclerViewCanales.setRecycledViewPool(SharedViewPool.getPool())
        recyclerViewCanales.itemAnimator = null

        val layoutManager = LinearLayoutManager(this, LinearLayoutManager.HORIZONTAL, false)
        layoutManager.isItemPrefetchEnabled = false
        recyclerViewCanales.layoutManager = layoutManager

        canalAdapter = CanalAdapter(canales, this, recyclerViewCanales) { canalId, level, isFinalChange ->
            fichaSaver.programarGuardadoFader(fichaDatabaseHelper, canalId, level, isFinalChange)
        }

        canalAdapter.setOnCanalDataChangeListener { canalId, field, value ->
            fichaSaver.programarGuardadoCampo(fichaDatabaseHelper, canalId, field, value)
        }

        canalAdapter.setOnColorChangeListener { position, color ->
            if (position in canales.indices) {
                val canal = canales[position]
                canal.color = color

                if (canal.id != -1) {
                    fichaSaver.programarGuardadoCampo(fichaDatabaseHelper, canal.id, "color", color)
                }
            }
        }

        recyclerViewCanales.adapter = canalAdapter
        setupItemTouchHelper()
    }

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
                if (fromPos in canales.indices && toPos in canales.indices) {
                    canalAdapter.moveCanal(fromPos, toPos)
                    return true
                }
                return false
            }

            override fun onSwiped(viewHolder: RecyclerView.ViewHolder, direction: Int) {}

            override fun isLongPressDragEnabled(): Boolean = false

            override fun onSelectedChanged(viewHolder: RecyclerView.ViewHolder?, actionState: Int) {
                super.onSelectedChanged(viewHolder, actionState)
                when (actionState) {
                    ItemTouchHelper.ACTION_STATE_DRAG -> {
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

                recyclerView.postDelayed({
                    canalAdapter.refreshNumerationDebounced()
                    saveCanalOrder()
                }, 100)
            }

            override fun getMoveThreshold(viewHolder: RecyclerView.ViewHolder): Float {
                return 0.2f
            }

            override fun getAnimationDuration(
                recyclerView: RecyclerView,
                animationType: Int,
                animateDx: Float,
                animateDy: Float
            ): Long {
                return 150
            }
        }

        val itemTouchHelper = ItemTouchHelper(callback)
        itemTouchHelper.attachToRecyclerView(recyclerViewCanales)
        canalAdapter.setItemTouchHelper(itemTouchHelper)
    }

    private fun setupEventListeners() {
        setupDynamicHints()

        agregarCanalButton.setOnClickListener {
            Log.d("ViewFichaActivity", "🔵 Botón Agregar Canal presionado")
            agregarCanal()
        }
    }

    private fun setupDynamicHints() {
        val nombreHint = getString(R.string.nombreficha)
        val descripcionHint = "Descripción"

        editTextNombre.setOnFocusChangeListener { _, hasFocus ->
            editTextNombre.hint = if (hasFocus) "" else nombreHint
        }

        editTextDescripcion.setOnFocusChangeListener { _, hasFocus ->
            editTextDescripcion.hint = if (hasFocus) "" else descripcionHint
        }
    }

    private fun setupBackHandler() {
        onBackPressedDispatcher.addCallback(this) {
            // Mostrar Toast inmediatamente
            Toast.makeText(
                this@ViewFichaActivity,
                "Ficha actualizada",
                Toast.LENGTH_SHORT
            ).show()

            // Iniciar guardado en background pero no esperar
            scope.launch {
                Log.d("ViewFichaActivity", "🔙 Back presionado - Guardando en background")

                insertarCanalesPendientesSync()
                fichaSaver.flushTodo(fichaDatabaseHelper)

                ficha?.id?.let { fichaId ->
                    fichaSaver.guardarFichaCompleta(
                        fichaDatabaseHelper,
                        fichaId,
                        editTextNombre.text.toString(),
                        editTextDescripcion.text.toString(),
                        canales
                    )
                }
            }

            // Retornar resultado y terminar inmediatamente
            val resultIntent = Intent().apply {
                putExtra("fichaId", ficha?.id ?: -1)
            }
            setResult(RESULT_OK, resultIntent)
            finish()
        }
    }

    private suspend fun insertarCanalesPendientesSync() {
        val canalesPendientes = canales.filter { it.id == -1 }
        if (canalesPendientes.isEmpty()) return

        Log.d("ViewFichaActivity", "🔧 Insertando ${canalesPendientes.size} canales pendientes")

        ficha?.id?.let { fichaId ->
            withContext(Dispatchers.IO) {
                val db = fichaDatabaseHelper.writableDatabase
                db.beginTransaction()

                try {
                    var insertados = 0
                    canales.forEachIndexed { index, canal ->
                        if (canal.id == -1) {
                            val values = ContentValues().apply {
                                put("ficha_id", fichaId)
                                put("nombre", canal.nombre)
                                put("microfonia", canal.microfonia)
                                put("fx", canal.fx)
                                put("color", canal.color)
                                put("orden", index)
                                put("fader_level", canal.faderLevel)
                            }

                            val nuevoId = db.insert("canales", null, values)
                            if (nuevoId != -1L) {
                                canal.id = nuevoId.toInt()
                                insertados++
                                Log.d("ViewFichaActivity", "✅ Canal pendiente insertado: ID=$nuevoId")
                            }
                        }
                    }

                    // Actualizar timestamp de la ficha
                    if (insertados > 0) {
                        val fichaValues = ContentValues().apply {
                            put("ultima_modificacion", System.currentTimeMillis() / 1000)
                        }
                        db.update("fichas", fichaValues, "id = ?", arrayOf(fichaId.toString()))
                    }

                    db.setTransactionSuccessful()
                    Log.d("ViewFichaActivity", "✅ $insertados canales pendientes insertados")
                } catch (e: Exception) {
                    Log.e("ViewFichaActivity", "❌ Error insertando canales pendientes", e)
                } finally {
                    db.endTransaction()
                }
            }
        }
    }

    private fun setupWindowInsets() {
        val coordinatorLayout = findViewById<CoordinatorLayout>(R.id.coordinator_layout)
        ViewCompat.setOnApplyWindowInsetsListener(coordinatorLayout) { _, windowInsets ->
            val systemInsets = windowInsets.getInsets(WindowInsetsCompat.Type.systemBars())

            val appBarLayout = findViewById<AppBarLayout>(R.id.appBarLayout)
            appBarLayout.setPadding(systemInsets.left, systemInsets.top, systemInsets.right, 0)

            val toolbar = findViewById<Toolbar>(R.id.toolbar)
            toolbar.setPadding(systemInsets.left, 0, systemInsets.right, 0)

            val nestedScrollView = findViewById<androidx.core.widget.NestedScrollView>(R.id.frame_layout)
            nestedScrollView.setPadding(systemInsets.left, 0, systemInsets.right, systemInsets.bottom)

            WindowInsetsCompat.CONSUMED
        }
    }

    private fun saveCanalOrder() {
        orderSaveJob?.cancel()
        orderSaveJob = scope.launch(Dispatchers.IO) {
            delay(300)
            ficha?.id?.let { fichaId ->
                fichaSaver.guardarOrdenCanales(fichaDatabaseHelper, fichaId, canales)
            }
        }
    }

    private fun agregarCanal() {
        if (canales.size >= 16) {
            mostrarLimiteCanalesDialog()
            return
        }

        val nuevoNumeroCanal = canales.size + 1
        val nuevoCanal = Canal(-1, nuevoNumeroCanal, "", "", "", 0, 0)
        val posicion = canales.size

        canales.add(nuevoCanal)
        canalAdapter.notifyItemInserted(posicion)

        // Scroll después de que el item se haya renderizado
        recyclerViewCanales.postDelayed({
            // Verificar que el layout está listo
            if (recyclerViewCanales.isLaidOut && recyclerViewCanales.isAttachedToWindow) {
                val layoutManager = recyclerViewCanales.layoutManager as LinearLayoutManager
                layoutManager.scrollToPositionWithOffset(posicion, 50) // Con un pequeño offset
                Log.d("ViewFichaActivity", "📜 Scroll realizado a posición: $posicion")
            } else {
                // Fallback si el layout no está listo
                recyclerViewCanales.smoothScrollToPosition(posicion)
            }
        }, 100) // Pequeño delay para asegurar que el item se haya agregado

        ficha?.id?.let { fichaId ->
            // Insertar inmediatamente sin debounce para evitar problemas de timing
            insertarCanalInmediato(fichaId, nuevoCanal, posicion)
        }
    }

    private fun insertarCanalInmediato(fichaId: Int, canal: Canal, posicion: Int) {
        scope.launch(Dispatchers.IO) {
            try {
                // ✅ Usar el método existente que ya maneja transacciones internamente
                val nuevoId = fichaDatabaseHelper.insertCanal(
                    fichaId = fichaId,
                    nombre = canal.nombre,
                    microfonia = canal.microfonia,
                    fx = canal.fx,
                    color = canal.color,
                    orden = posicion,
                    faderLevel = canal.faderLevel
                )

                if (nuevoId != -1L) {
                    canal.id = nuevoId.toInt()

                    // Actualizar timestamp (ya se hace en insertCanal, pero por si acaso)
                    fichaDatabaseHelper.updateFichaTimestamp(fichaId)

                    withContext(Dispatchers.Main) {
                        canalAdapter.notifyItemChanged(posicion)
                        Log.d("ViewFichaActivity", "✅ Canal insertado: ID=$nuevoId")
                    }
                }
            } catch (e: Exception) {
                Log.e("ViewFichaActivity", "❌ Error insertando canal", e)
            }
        }
    }



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

    override fun onDeleteClick(position: Int) {
        if (position !in canales.indices) return

        val canal = canales[position]
        AlertDialog.Builder(this)
            .setTitle("Confirmar eliminación")
            .setMessage("¿Seguro de que deseas eliminar este canal?")
            .setPositiveButton("Sí") { _, _ ->
                scope.launch {
                    if (canal.id != -1) {
                        fichaSaver.eliminarCanal(fichaDatabaseHelper, canal.id)
                    }
                }
                canalAdapter.removeItem(position)
            }
            .setNegativeButton("No", null)
            .show()
    }

    override fun onPause() {
        super.onPause()
        Log.d("ViewFichaActivity", "⏸️ onPause() - Guardando cambios pendientes")

        // Usar una coroutine con tiempo limitado para evitar bloquear la UI
        scope.launch {
            try {
                withTimeout(2000) { // Timeout de 2 segundos
                    // Guardar canales pendientes primero
                    insertarCanalesPendientesSync()

                    // Luego hacer flush de otras operaciones
                    fichaSaver.flushTodo(fichaDatabaseHelper)

                    Log.d("ViewFichaActivity", "✅ Guardado en onPause completado")
                }
            } catch (e: TimeoutCancellationException) {
                Log.e("ViewFichaActivity", "⚠️ Timeout al guardar en onPause")
            } catch (e: Exception) {
                Log.e("ViewFichaActivity", "❌ Error en onPause", e)
            }
        }
    }

    override fun onDestroy() {
        fichaSaver.cancelarTodo()
        scope.cancel()
        fichaDatabaseHelper.close()
        super.onDestroy()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        Log.d("ViewFichaActivity", "💾 Guardando estado - Ficha ID: ${ficha?.id}, Canales: ${canales.size}")

        ficha?.let {
            outState.putInt("FICHA_ID", it.id)
            outState.putString("FICHA_NOMBRE", it.nombre)
            outState.putString("FICHA_DESCRIPCION", it.descripcion)
        }

        outState.putParcelableArrayList("CANALES_DATA", ArrayList(canales))
    }

    override fun onRestoreInstanceState(savedInstanceState: Bundle) {
        super.onRestoreInstanceState(savedInstanceState)
        Log.d("ViewFichaActivity", "🔄 Restaurando estado...")

        savedInstanceState.let { bundle ->
            val fichaId = bundle.getInt("FICHA_ID", -1)
            if (fichaId != -1 && ficha != null) {
                ficha = ficha?.copy(
                    nombre = bundle.getString("FICHA_NOMBRE", ficha?.nombre ?: ""),
                    descripcion = bundle.getString("FICHA_DESCRIPCION", ficha?.descripcion ?: "")
                )

                editTextNombre.setText(ficha?.nombre.orEmpty())
                editTextDescripcion.setText(ficha?.descripcion.orEmpty())
            }

            @Suppress("DEPRECATION")
            val canalesRestored: ArrayList<Canal>? = bundle.getParcelableArrayList("CANALES_DATA")
            if (canalesRestored != null) {
                canales.clear()
                canales.addAll(canalesRestored)
                canalAdapter.notifyDataSetChanged()
                Log.d("ViewFichaActivity", "✅ Estado restaurado - Canales: ${canales.size}")
            }
        }
    }

    override fun onConfigurationChanged(newConfig: android.content.res.Configuration) {
        super.onConfigurationChanged(newConfig)
        Log.d("ViewFichaActivity", "🔄 Cambio de configuración detectado (rotación)")

        recyclerViewCanales.post {
            recyclerViewCanales.layoutManager?.let {
                (it as? LinearLayoutManager)?.supportsPredictiveItemAnimations()
            }
            canalAdapter.notifyDataSetChanged()
            Log.d("ViewFichaActivity", "✅ UI actualizada post-rotación - Canales visibles: ${canales.size}")
        }
    }
}