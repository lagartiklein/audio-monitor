package com.cepalabsfree.fichatech

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.fragment.app.Fragment
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.Spinner
import android.widget.ArrayAdapter
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatDelegate
import com.google.android.material.switchmaterial.SwitchMaterial
import com.google.firebase.auth.FirebaseAuth
import java.io.File
import java.util.Locale

class AjustesFragment : Fragment() {

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View? {
        val view = inflater.inflate(R.layout.fragment_ajustes, container, false)

        val btnClearData: Button = view.findViewById(R.id.btn_clear_data)
        btnClearData.setOnClickListener {
            showConfirmDialog()
        }

        // Switch para modo oscuro
        val switchTheme: SwitchMaterial = view.findViewById(R.id.switch_theme)
        val prefs = requireActivity().getSharedPreferences("theme_prefs", Context.MODE_PRIVATE)
        val mode = prefs.getInt("theme_mode", AppCompatDelegate.MODE_NIGHT_NO)
        switchTheme.isChecked = mode == AppCompatDelegate.MODE_NIGHT_YES

        switchTheme.setOnCheckedChangeListener { _, isChecked ->
            val newMode = if (isChecked) AppCompatDelegate.MODE_NIGHT_YES else AppCompatDelegate.MODE_NIGHT_NO
            prefs.edit().putInt("theme_mode", newMode).apply()

            // ✅ CORRECCIÓN: Limpiar caché de colores antes de cambiar tema
            com.cepalabsfree.fichatech.fichatecnica.CanalAdapter.clearThemeCache()

            AppCompatDelegate.setDefaultNightMode(newMode)
            requireActivity().recreate()
        }

        // Botón de cerrar sesión
        setupLogoutButton(view)

        return view
    }





    private fun setupLogoutButton(view: View) {
        val auth = FirebaseAuth.getInstance()
        val userPrefs = requireActivity().getSharedPreferences("user_prefs", Context.MODE_PRIVATE)
        val isGuest = userPrefs.getBoolean("is_guest", false)

        // Encontrar el botón de cerrar sesión
        val btnLogout = view.findViewById<Button>(R.id.btn_logout)

        // Solo mostrar el botón si hay un usuario autenticado o es invitado
        if (auth.currentUser != null || isGuest) {
            btnLogout?.visibility = View.VISIBLE
            btnLogout?.setOnClickListener {
                showLogoutDialog()
            }
        } else {
            btnLogout?.visibility = View.GONE
        }
    }

    private fun showLogoutDialog() {
        AlertDialog.Builder(requireContext())
            .setTitle(getString(R.string.logout_title))
            .setMessage(getString(R.string.logout_message))
            .setPositiveButton(getString(R.string.yes)) { _, _ -> performLogout() }
            .setNegativeButton(getString(R.string.no), null)
            .show()
    }

    private fun performLogout() {
        // Cerrar sesión de Firebase
        FirebaseAuth.getInstance().signOut()

        // Limpiar preferencias de invitado
        val userPrefs = requireActivity().getSharedPreferences("user_prefs", Context.MODE_PRIVATE)
        userPrefs.edit().clear().apply()

        // Redirigir a LoginActivity
        val intent = Intent(requireContext(), com.cepalabsfree.fichatech.auth.LoginActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        }
        startActivity(intent)
        requireActivity().finish()
    }

    private fun showConfirmDialog() {
        AlertDialog.Builder(requireContext())
            .setTitle(getString(R.string.confirmar_borrado_title))
            .setMessage(getString(R.string.confirmar_borrado_message))
            .setPositiveButton(getString(R.string.yes)) { _, _ -> clearAllData() }
            .setNegativeButton(getString(R.string.no), null)
            .show()
    }

    private fun clearAllData() {
        // ✅ Borrar TODAS las SharedPreferences
        requireActivity().getSharedPreferences("theme_prefs", Context.MODE_PRIVATE).edit().clear().apply()
        requireActivity().getSharedPreferences("language_prefs", Context.MODE_PRIVATE).edit().clear().apply()
        requireActivity().getSharedPreferences("user_prefs", Context.MODE_PRIVATE).edit().clear().apply()

        // Borrar bases de datos
        requireContext().deleteDatabase("fichas.db")
        requireContext().deleteDatabase("planta_escenario.db")
        requireContext().deleteDatabase("sonometro.db")

        // Borrar archivos
        val recordingsDir = File(requireContext().filesDir, "recordings")
        recordingsDir.deleteRecursively()

        // Mostrar confirmación y redirigir
        AlertDialog.Builder(requireContext())
            .setTitle(getString(R.string.datos_borrados_title))
            .setMessage(getString(R.string.datos_borrados_message))
            .setPositiveButton(getString(R.string.cerrar)) { _, _ ->
                requireActivity().finish()
            }
            .setCancelable(false)
            .show()
    }

    private fun openUrl(url: String) {
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
        startActivity(intent)
    }
}
