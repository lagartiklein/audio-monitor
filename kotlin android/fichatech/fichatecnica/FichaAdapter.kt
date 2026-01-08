package com.cepalabsfree.fichatech.fichatecnica

import android.util.Log
import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.annotation.Keep
import androidx.appcompat.app.AlertDialog
import androidx.recyclerview.widget.RecyclerView
import com.cepalabsfree.fichatech.databinding.ItemFichaBinding

@Keep
class FichaAdapter(initialFichas: List<Ficha>) :
    RecyclerView.Adapter<FichaAdapter.FichaViewHolder>() {

    private val fichas = initialFichas.toMutableList()

    private var onDeleteClickListener: OnDeleteClickListener? = null
    private var onViewClickListener: OnViewClickListener? = null

    private fun refreshFicha(position: Int, descripcion: String? = null, color: Int? = null) {
        if (position !in fichas.indices) return

        val original = fichas[position]
        val updated = original.copy(
            descripcion = descripcion ?: original.descripcion,
            colorFondo = color ?: original.colorFondo,
            ultimaModificacion = System.currentTimeMillis() / 1000
        )

        // ✅ Si la posición es 0, solo actualizar en lugar
        if (position == 0) {
            fichas[position] = updated
            notifyItemChanged(position)
        } else {
            // ✅ Si no es primera, mover al inicio (porque timestamp se actualizó)
            fichas.removeAt(position)
            fichas.add(0, updated)
            notifyItemMoved(position, 0)
            notifyItemChanged(0)
        }
    }

    fun insertFichaAlInicio(ficha: Ficha) {
        fichas.add(0, ficha)
        notifyItemInserted(0)
    }

    fun setOnDeleteClickListener(listener: OnDeleteClickListener) {
        onDeleteClickListener = listener
    }

    fun setOnViewClickListener(listener: OnViewClickListener) {
        onViewClickListener = listener
    }

    fun updateFichas(nuevasFichas: List<Ficha>) {
        // ✅ ACTUALIZACIÓN INMEDIATA Y EFICIENTE
        if (fichas.isEmpty() && nuevasFichas.isNotEmpty()) {
            // Primera carga - insertar todos
            fichas.addAll(nuevasFichas)
            notifyItemRangeInserted(0, nuevasFichas.size)
        } else if (fichas.size == nuevasFichas.size) {
            // Mismo tamaño - actualizar elementos
            fichas.clear()
            fichas.addAll(nuevasFichas)
            notifyItemRangeChanged(0, fichas.size)
        } else {
            // Tamaño diferente - recarga completa optimizada
            fichas.clear()
            fichas.addAll(nuevasFichas)
            notifyDataSetChanged()
        }
    }

    // ✅ NUEVO: Actualizar ficha específica inmediatamente
    fun actualizarFichaInmediata(fichaActualizada: Ficha) {
        val index = fichas.indexOfFirst { it.id == fichaActualizada.id }
        if (index >= 0) {
            fichas[index] = fichaActualizada
            notifyItemChanged(index)
        }
    }

    fun getFichaAt(position: Int): Ficha {
        return fichas[position]
    }

    // Permite mover fichas en la lista
    fun moveFicha(fromPosition: Int, toPosition: Int) {
        // VALIDACIÓN CRÍTICA DE ÍNDICES
        if (fromPosition !in 0 until itemCount || toPosition !in 0 until itemCount) {
            Log.w("FichaAdapter", "Índices inválidos: from=$fromPosition, to=$toPosition, count=$itemCount")
            return
        }
        if (fromPosition == toPosition) return

        val ficha = fichas.removeAt(fromPosition)
        fichas.add(toPosition, ficha)
        notifyItemMoved(fromPosition, toPosition)
    }

    // Devuelve la lista actual para guardar el orden
    fun getFichas(): List<Ficha> = fichas

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): FichaViewHolder {
        val binding = ItemFichaBinding.inflate(LayoutInflater.from(parent.context), parent, false)
        return FichaViewHolder(binding)
    }

    override fun onBindViewHolder(holder: FichaViewHolder, position: Int) {
        val ficha = fichas[position]
        holder.bind(ficha)
        // Mostrar número de canales en el visor
        holder.binding.root.findViewById<android.widget.TextView>(com.cepalabsfree.fichatech.R.id.fichaNumCanales)?.text =
            "${ficha.canales.size} Ch"
        // Aplica el color de fondo: blanco por defecto
        val cardView = holder.binding.root.findViewById<androidx.cardview.widget.CardView>(com.cepalabsfree.fichatech.R.id.cardFicha)
        if (ficha.colorFondo != null && ficha.colorFondo != -1) {
            cardView?.setCardBackgroundColor(ficha.colorFondo)
        } else {
            // Color por defecto: blanco
            cardView?.setCardBackgroundColor(0xFFFFFFFF.toInt())
        }
    }

    override fun onViewRecycled(holder: FichaViewHolder) {
        super.onViewRecycled(holder)
        // Limpiar cualquier listener del itemView
        holder.itemView.setOnClickListener(null)
        holder.binding.fichaIcono.setOnClickListener(null)
    }

    override fun getItemCount(): Int = fichas.size

    inner class FichaViewHolder(val binding: ItemFichaBinding) :
        RecyclerView.ViewHolder(binding.root) {

        fun bind(ficha: Ficha) {
            binding.fichaNombre.text = ficha.nombre
            binding.fichaDescripcion.text = ficha.descripcion
            binding.fichaIcono.setOnClickListener {
                val context = binding.root.context
                val options = arrayOf("Editar descripción", "Cambiar color", "Eliminar")
                AlertDialog.Builder(context)
                    .setTitle("Opciones")
                    .setItems(options) { _, which ->
                        when (which) {
                            0 -> { // Editar descripción
                                val editText = android.widget.EditText(context).apply {
                                    setText(ficha.descripcion)
                                    setSelection(text.length)
                                }
                                AlertDialog.Builder(context)
                                    .setTitle("Editar descripción")
                                    .setView(editText)
                                    .setPositiveButton("Guardar") { _, _ ->
                                        val nuevaDescripcion = editText.text.toString()
                                        if (context is android.app.Activity) {
                                            val dbHelper = FichaDatabaseHelper(context)
                                            // ✅ updateFicha ya actualiza el timestamp automáticamente
                                            dbHelper.updateFicha(ficha.id, ficha.nombre, nuevaDescripcion)

                                            refreshFicha(bindingAdapterPosition, nuevaDescripcion)
                                        }
                                    }
                                    .setNegativeButton("Cancelar", null)
                                    .show()
                            }
                            1 -> { // Cambiar color
                                val colores = arrayOf("Por defecto", "Azul", "Verde", "Rojo", "Amarillo", "Gris")
                                val colorValues = arrayOf(
                                    -1, // Por defecto (usamos -1 para indicar valor por defecto)
                                    0xFF2196F3.toInt(), // Azul
                                    0xFF4CAF50.toInt(), // Verde
                                    0xFFF44336.toInt(), // Rojo
                                    0xFFFFEB3B.toInt(), // Amarillo
                                    0xFFBDBDBD.toInt()  // Gris más oscuro
                                )
                                AlertDialog.Builder(context)
                                    .setTitle("Selecciona un color")
                                    .setItems(colores) { _, colorIdx ->
                                        if (context is android.app.Activity) {
                                            val dbHelper = FichaDatabaseHelper(context)
                                            // ✅ updateFichaColor ya actualiza el timestamp automáticamente
                                            if (colorIdx == 0) {
                                                dbHelper.updateFichaColor(ficha.id, -1) // -1 indica color por defecto
                                            } else {
                                                dbHelper.updateFichaColor(ficha.id, colorValues[colorIdx])
                                            }

                                            refreshFicha(bindingAdapterPosition, color = if (colorIdx == 0) -1 else colorValues[colorIdx])
                                        }
                                    }
                                    .setNegativeButton("Cancelar", null)
                                    .show()
                            }
                            2 -> { // Eliminar
                                onDeleteClickListener?.onDeleteClick(bindingAdapterPosition)
                            }
                        }
                    }.show()
            }
            // Agregar click listener al item completo
            itemView.setOnClickListener {
                onViewClickListener?.onViewClick(bindingAdapterPosition)
            }
        }
    }



    interface OnDeleteClickListener {
        fun onDeleteClick(position: Int)
    }

    interface OnViewClickListener {
        fun onViewClick(position: Int)
    }
}