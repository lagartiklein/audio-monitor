package com.cepalabsfree.fichatech.sonometro

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.RecyclerView
import com.cepalabsfree.fichatech.R

class ReportAdapter(
    private val reportList: List<SonometroReport>,
    private val onItemLongClick: (SonometroReport) -> Unit
) : RecyclerView.Adapter<ReportAdapter.ReportViewHolder>() {

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ReportViewHolder {
        val view = LayoutInflater.from(parent.context).inflate(R.layout.item_report, parent, false)
        return ReportViewHolder(view)
    }

    override fun onBindViewHolder(holder: ReportViewHolder, position: Int) {
        val report = reportList[position]
        holder.bind(report, onItemLongClick)
    }

    override fun getItemCount(): Int = reportList.size

    class ReportViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        private val tvReport: TextView = itemView.findViewById(R.id.tvReport)

        fun bind(report: SonometroReport, onItemLongClick: (SonometroReport) -> Unit) {
            tvReport.text = "${report.date} - Promedio: ${String.format("%.1f", report.averageDb)} dB"

            // Cambiar color basado en el nivel de dB
            val color = when {
                report.averageDb < 60 -> ContextCompat.getColor(itemView.context, R.color.canal_verde)
                report.averageDb < 80 -> ContextCompat.getColor(itemView.context, R.color.canal_amarillo)
                else -> ContextCompat.getColor(itemView.context, R.color.canal_rojo)
            }
            tvReport.setTextColor(color)

            itemView.setOnLongClickListener {
                onItemLongClick(report)
                true
            }

            // También hacer click normal para ver detalles
            itemView.setOnClickListener {
                // Podrías mostrar un diálogo con más detalles aquí
            }
        }
    }
}