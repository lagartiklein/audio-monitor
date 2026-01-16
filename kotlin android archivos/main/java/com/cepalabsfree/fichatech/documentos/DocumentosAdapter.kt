package com.cepalabsfree.fichatech.documentos

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.CheckBox
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import com.cepalabsfree.fichatech.R

class DocumentosAdapter(
    var documentos: List<Documento>,
    private val onDocumentoSelected: (Documento, Boolean) -> Unit
) : RecyclerView.Adapter<DocumentosAdapter.DocumentoViewHolder>() {
    inner class DocumentoViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        val tvNombre: TextView = itemView.findViewById(R.id.tvNombreDocumento)
        val tvDescripcion: TextView = itemView.findViewById(R.id.tvDescripcionDocumento)
        val tvFecha: TextView = itemView.findViewById(R.id.tvFechaDocumento)
        val checkBox: CheckBox = itemView.findViewById(R.id.checkBoxDocumento)
        fun bind(documento: Documento) {
            tvNombre.text = documento.nombre
            tvDescripcion.text = documento.descripcion
            tvFecha.text = documento.fechaCreacion
            checkBox.isChecked = documento.isSelected
            // Configurar el click listener para toda la vista
            itemView.setOnClickListener {
                checkBox.isChecked = !checkBox.isChecked
                onDocumentoSelected(documento, checkBox.isChecked)
            }
            // Configurar el checkbox
            checkBox.setOnClickListener {
                onDocumentoSelected(documento, checkBox.isChecked)
            }
        }
    }
    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): DocumentoViewHolder {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_documento, parent, false)
        return DocumentoViewHolder(view)
    }
    override fun onBindViewHolder(holder: DocumentoViewHolder, position: Int) {
        holder.bind(documentos[position])
    }
    override fun getItemCount(): Int = documentos.size
    fun updateDocumentos(documentos: List<Documento>) {
        // Filtrar solo fichas técnicas y plantas de escenario
        this.documentos = documentos.filter {
            it.tipo == TipoDocumento.FICHA_TECNICA || it.tipo == TipoDocumento.PLANTA_ESCENARIO
        }
        notifyDataSetChanged()
    }
}