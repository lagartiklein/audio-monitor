package com.cepalabsfree.fichatech.tuner

import android.Manifest
import android.animation.AnimatorSet
import android.animation.ObjectAnimator
import android.content.pm.ActivityInfo
import android.content.pm.PackageManager
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.view.animation.OvershootInterpolator
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import com.cepalabsfree.fichatech.R
import com.cepalabsfree.fichatech.databinding.FragmentTunerBinding

class TunerFragment : Fragment() {
    private var _binding: FragmentTunerBinding? = null
    private val binding get() = _binding!!

    private lateinit var tuner: Tuner
    private var isTunerRunning: Boolean = false

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted: Boolean ->
        if (isGranted) {
            setupStartStopButton()
            toggleTuner() // Inicia o detiene el afinador dependiendo de su estado actual
        } else {
            // Manejar el caso donde no se concede el permiso
            // Puedes mostrar un mensaje al usuario
            binding.startStopButton.text = getString(R.string.permission_denied)
        }
    }

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentTunerBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        // Comprobar si el permiso ya está concedido
        if (ContextCompat.checkSelfPermission(
                requireContext(),
                Manifest.permission.RECORD_AUDIO
            ) == PackageManager.PERMISSION_GRANTED
        ) {
            setupStartStopButton()
        } else {
            // Solicitar el permiso si no está concedido
            requestPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
        }
    }

    private fun setupStartStopButton() {
        binding.startStopButton.setOnClickListener {
            animateStartStopButton()
            toggleTuner()
        }
    }

    private fun animateStartStopButton() {
        val scaleX = ObjectAnimator.ofFloat(binding.startStopButton, "scaleX", 1f, 1.15f, 1f)
        val scaleY = ObjectAnimator.ofFloat(binding.startStopButton, "scaleY", 1f, 1.15f, 1f)
        AnimatorSet().apply {
            playTogether(scaleX, scaleY)
            duration = 300
            interpolator = OvershootInterpolator()
            start()
        }
    }

    private fun toggleTuner() {
        if (isTunerRunning) {
            detenerAfinador()
        } else {
            iniciarAfinador()
        }
    }

    private fun iniciarAfinador() {
        tuner = Tuner()
        tuner.onNoteDetected = { note, db -> updateUI(note, db) }
        tuner.start(requireContext())
        isTunerRunning = true
        binding.startStopButton.text = getString(R.string.stop_tuner)
        requireActivity().requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_LOCKED // Bloquear la rotación mientras el afinador está activo
    }

    private fun detenerAfinador() {
        if (::tuner.isInitialized) {
            tuner.stop()
        }
        isTunerRunning = false
        binding.startStopButton.text = getString(R.string.start_tuner)
        requireActivity().requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED // Permitir rotación después de detener

        // Reset UI to default state
        binding.noteText.text = getString(R.string.tuner_default_note)
        binding.frequencyText.text = getString(R.string.tuner_default_frequency)
        binding.centsView.updateCents(0)
        binding.audioLevelBar.progress = 0
    }

    private fun updateUI(note: Note, db: Float) {
        activity?.runOnUiThread {
            _binding?.let {
                it.noteText.text = note.name
                it.frequencyText.text = getString(R.string.frequency_text, note.frequency)
                it.centsView.updateCents(note.cents)
                it.audioLevelBar.progress = calculateAudioLevel(db)
            }
        }
    }

    private fun calculateAudioLevel(db: Float): Int {
        val maxDb = 0f
        val minDb = -80f
        return ((db - minDb) / (maxDb - minDb) * 100).toInt().coerceIn(0, 100)
    }

    override fun onPause() {
        super.onPause()
        detenerAfinador()
    }

    override fun onDestroyView() {
        super.onDestroyView()
        detenerAfinador()
        _binding = null
    }
}
