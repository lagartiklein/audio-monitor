package com.cepalabsfree.fichatech.fichatecnica

import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.animation.ObjectAnimator
import android.animation.AnimatorSet
import android.animation.PropertyValuesHolder
import android.view.animation.DecelerateInterpolator
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.fragment.app.Fragment
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import androidx.recyclerview.widget.ItemTouchHelper
import com.cepalabsfree.fichatech.databinding.FragmentFichaTecnicaBinding
import androidx.activity.result.contract.ActivityResultContracts
import android.os.Handler
import android.os.Looper

class FichaTecnicaFragment : Fragment(), FichaAdapter.OnDeleteClickListener,
    FichaAdapter.OnViewClickListener {

    private var _binding: FragmentFichaTecnicaBinding? = null
    private val binding get() = _binding!!

    private lateinit var recyclerView: RecyclerView
    private lateinit var adapter: FichaAdapter
    private lateinit var dbHelper: FichaDatabaseHelper


    // Moderno: Launchers para resultados de actividades
    private val crearFichaLauncher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        if (result.resultCode == AppCompatActivity.RESULT_OK) {
            // ✅ ACTUALIZACIÓN INMEDIATA - sin delays
            updateFichas()
        }
    }

    private val viewFichaLauncher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        if (result.resultCode == AppCompatActivity.RESULT_OK) {
            // ✅ ACTUALIZACIÓN INMEDIATA - sin delays
            updateFichas()
        }
    }

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentFichaTecnicaBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        dbHelper = FichaDatabaseHelper(requireContext())
        adapter = FichaAdapter(dbHelper.getAllFichas())
        adapter.setOnDeleteClickListener(this)
        adapter.setOnViewClickListener(this)



        recyclerView = binding.recyclerFichasGuardadas
        recyclerView.layoutManager = LinearLayoutManager(requireContext())
        recyclerView.adapter = adapter

        // Drag & drop para mover fichas y guardar el orden
        val itemTouchHelper = ItemTouchHelper(object : ItemTouchHelper.SimpleCallback(
            ItemTouchHelper.UP or ItemTouchHelper.DOWN, 0
        ) {
            override fun onMove(
                recyclerView: RecyclerView,
                viewHolder: RecyclerView.ViewHolder,
                target: RecyclerView.ViewHolder
            ): Boolean {
                val fromPos = viewHolder.bindingAdapterPosition
                val toPos = target.bindingAdapterPosition
                adapter.moveFicha(fromPos, toPos)
                return true
            }

            override fun onSwiped(viewHolder: RecyclerView.ViewHolder, direction: Int) {
                // No swipe
            }

            override fun isLongPressDragEnabled(): Boolean = true

            override fun clearView(recyclerView: RecyclerView, viewHolder: RecyclerView.ViewHolder) {
                super.clearView(recyclerView, viewHolder)
                dbHelper.updateFichasOrder(adapter.getFichas())
            }
        })
        itemTouchHelper.attachToRecyclerView(recyclerView)

        // Animación de movimiento para los items del RecyclerView
        recyclerView.itemAnimator = null // Desactiva animaciones por defecto

        // Agrega animación al aparecer cada item
        adapter.registerAdapterDataObserver(object : RecyclerView.AdapterDataObserver() {
            override fun onChanged() {
                super.onChanged()
                animateVisibleItems()
            }
        })
        animateVisibleItems() // Para la primera carga

        // Animación para mostrar el botón "Crear nueva lista" centrado
        binding.btnCrearNuevaLista.apply {
            alpha = 0f
            translationY = 30f
            post {
                val fadeIn = ObjectAnimator.ofFloat(this, "alpha", 0f, 1f)
                val moveIn = ObjectAnimator.ofFloat(this, "translationY", 30f, 0f)
                AnimatorSet().apply {
                    playTogether(fadeIn, moveIn)
                    duration = 900
                    interpolator = DecelerateInterpolator()
                    start()
                }
                // Reemplaza la animación de pulso actual con esta versión mejorada
                Handler(Looper.getMainLooper()).postDelayed({
                    ObjectAnimator.ofPropertyValuesHolder(
                        this,
                        PropertyValuesHolder.ofFloat("scaleX", 1.0f, 1.03f),
                        PropertyValuesHolder.ofFloat("scaleY", 1.0f, 1.03f)
                    ).apply {
                        duration = 1000
                        repeatMode = ObjectAnimator.REVERSE
                        repeatCount = ObjectAnimator.INFINITE
                        start()
                    }
                }, 900)
            }
            setOnClickListener {
                val fichasActuales = adapter.getFichas().size
                if (fichasActuales >= 8) {
                    AlertDialog.Builder(requireContext())
                        .setTitle("Límite alcanzado")
                        .setMessage("La versión gratuita permite un máximo de 8 fichas.\n\nPara crear más fichas, descarga la versión Pro de Fichatech.")
                        .setPositiveButton("Entendido", null)
                        .setNegativeButton("Descargar Pro") { _, _ ->
                            val intent = Intent(Intent.ACTION_VIEW).apply {
                                data = android.net.Uri.parse("market://details?id=com.cepalabs.fichatech")
                                setPackage("com.android.vending")
                            }
                            try {
                                startActivity(intent)
                            } catch (e: Exception) {
                                // Si no hay Play Store, abrir en navegador
                                val webIntent = Intent(Intent.ACTION_VIEW, android.net.Uri.parse("market://details?id=com.cepalabs.fichatech"))
                                startActivity(webIntent)
                            }
                        }
                        .show()
                } else {
                    val intent = Intent(requireContext(), CrearFichaActivity::class.java)
                    crearFichaLauncher.launch(intent)
                }
            }
        }
    }

    private fun animateVisibleItems() {
        recyclerView.post {
            for (i in 0 until recyclerView.childCount) {
                val view = recyclerView.getChildAt(i)
                view?.let {
                    it.translationX = 200f
                    it.alpha = 0f
                    it.animate()
                        .translationX(0f)
                        .alpha(1f)
                        .setDuration(400)
                        .setStartDelay((i * 60).toLong())
                        .start()
                }
            }
        }
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }

    override fun onDeleteClick(position: Int) {
        val ficha = adapter.getFichaAt(position)
        AlertDialog.Builder(requireContext())
            .setTitle("Eliminar Ficha")
            .setMessage("¿Está seguro de que desea eliminar?")
            .setPositiveButton("Sí") { _, _ ->
                dbHelper.deleteFicha(ficha.id)
                updateFichas()
            }
            .setNegativeButton("No", null)
            .show()
    }

    override fun onViewClick(position: Int) {
        val ficha = adapter.getFichaAt(position)
        val intent = Intent(requireContext(), ViewFichaActivity::class.java).apply {
            putExtra("fichaId", ficha.id)
        }
        // Usar launcher moderno
        viewFichaLauncher.launch(intent)
    }

    private fun updateFichas() {
        // ✅ ACTUALIZACIÓN INMEDIATA Y EFICIENTE
        val fichas = dbHelper.getAllFichas()
        adapter.updateFichas(fichas)
        // ✅ NO usar invalidate() - es costoso. El adapter notifica los cambios
    }
}