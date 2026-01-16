package com.cepalabsfree.fichatech

import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.fragment.app.Fragment

class AyudaFragment : Fragment() {

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View? {
        // Inflar el layout para este fragmento
        val view = inflater.inflate(R.layout.fragment_ayuda, container, false)

        // Configurar clics en los TextView
        setupExpandableTextView(view, R.id.inicio_app, R.id.inicio_app_content)
        setupExpandableTextView(view, R.id.ficha_tecnica, R.id.ficha_tecnica_content)
        setupExpandableTextView(view, R.id.planta_escenario, R.id.planta_escenario_content)
        setupExpandableTextView(view, R.id.afinador_cromatico, R.id.afinador_cromatico_content)
        setupExpandableTextView(view, R.id.sonometro, R.id.sonometro_content)
        setupExpandableTextView(view, R.id.grabador_audio, R.id.grabador_audio_content)
        setupExpandableTextView(view, R.id.ajustes, R.id.ajustes_content)
        setupExpandableTextView(view, R.id.documentos_guardados, R.id.documentos_guardados_content)
        setupExpandableTextView(view, R.id.version, R.id.version_content)

        // Configurar clics para abrir documentos HTML
        setupDocumentOpener(view, R.id.terminos_condiciones, "terms_and_conditions.html")
        setupDocumentOpener(view, R.id.politica_privacidad, "privacy_policy.html")

        return view
    }

    private fun setupExpandableTextView(view: View, textViewId: Int, contentViewId: Int) {
        val textView = view.findViewById<TextView>(textViewId)
        val contentView = view.findViewById<TextView>(contentViewId)

        textView.setOnClickListener {
            if (contentView.visibility == View.GONE) {
                contentView.animate()
                    .alpha(1.0f)
                    .setDuration(300)
                    .withStartAction { contentView.visibility = View.VISIBLE }
                    .start()
            } else {
                contentView.animate()
                    .alpha(0.0f)
                    .setDuration(300)
                    .withEndAction { contentView.visibility = View.GONE }
                    .start()
            }
        }
    }

    private fun setupDocumentOpener(view: View, textViewId: Int, fileName: String) {
        val textView = view.findViewById<TextView>(textViewId)
        textView.setOnClickListener {
            val intent = Intent(requireContext(), WebViewActivity::class.java)
            intent.putExtra("file", fileName)
            startActivity(intent)
        }
    }
}
