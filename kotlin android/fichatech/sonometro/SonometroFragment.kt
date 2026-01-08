package com.cepalabsfree.fichatech.sonometro

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioDeviceInfo
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.cepalabsfree.fichatech.R
import com.cepalabsfree.fichatech.databinding.FragmentSonometroBinding
import com.google.android.gms.ads.AdError
import com.google.android.gms.ads.AdRequest
import com.google.android.gms.ads.FullScreenContentCallback
import com.google.android.gms.ads.LoadAdError
import kotlinx.coroutines.*
import java.text.SimpleDateFormat
import java.util.*
import kotlin.math.log10
import kotlin.math.sqrt

class SonometroFragment : Fragment() {

    private lateinit var binding: FragmentSonometroBinding

    private val sampleRate = 44100
    private val bufferSize = AudioRecord.getMinBufferSize(
        sampleRate,
        AudioFormat.CHANNEL_IN_MONO,
        AudioFormat.ENCODING_PCM_16BIT
    )

    private var audioRecordMic1: AudioRecord? = null
    private var audioRecordMic2: AudioRecord? = null

    private lateinit var bufferMic1: ShortArray
    private lateinit var bufferMic2: ShortArray

    private var isRecording = false
    private val handler = Handler(Looper.getMainLooper())
    private val updateInterval: Long = 25
    private val decibelHistoryMic1 = mutableListOf<Double>()
    private val decibelHistoryMic2 = mutableListOf<Double>()
    private val reportList = mutableListOf<SonometroReport>()
    private lateinit var reportAdapter: ReportAdapter
    private lateinit var databaseManager: SonometroDatabaseManager

    private val TAG = "SonometroFragment"

    private var recordingJob: Job? = null

    private var micCount = 1

    private val requestAudioPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted: Boolean ->
        if (isGranted) {
            initializeAudioRecords()
            startRecording()
        } else {
            Toast.makeText(requireContext(), "Permiso de micrófono denegado", Toast.LENGTH_SHORT).show()
        }
    }

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View? {
        binding = FragmentSonometroBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        databaseManager = SonometroDatabaseManager(requireContext())

        val audioManager = requireContext().getSystemService(Context.AUDIO_SERVICE) as AudioManager
        val devices = audioManager.getDevices(AudioManager.GET_DEVICES_INPUTS)
        micCount = devices.count { it.type == AudioDeviceInfo.TYPE_BUILTIN_MIC }

        bufferMic1 = ShortArray(bufferSize)
        if (micCount > 1) {
            bufferMic2 = ShortArray(bufferSize)
        }

        binding.btnStart.setOnClickListener {
            if (isRecording) {
                stopRecording(saveReport = true)
            } else {
                checkAudioPermissionAndStart()
            }
        }

        reportAdapter = ReportAdapter(reportList) { report ->
            showDeleteDialog(report.id)
        }
        binding.rvReports.layoutManager = LinearLayoutManager(requireContext())
        binding.rvReports.adapter = reportAdapter

        cargarReportes()

        savedInstanceState?.let {
            if (it.getBoolean("isRecording", false)) {
                checkAudioPermissionAndStart()
            }
        }
    }

    override fun onResume() {
        super.onResume()
        if (isRecording) {
            startRecording()
        }
    }

    override fun onPause() {
        super.onPause()
        if (isRecording) {
            stopRecording(saveReport = false)
        }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putBoolean("isRecording", isRecording)
    }

    private fun checkAudioPermissionAndStart() {
        if (ContextCompat.checkSelfPermission(
                requireContext(),
                Manifest.permission.RECORD_AUDIO
            ) == PackageManager.PERMISSION_GRANTED
        ) {
            initializeAudioRecords()
            startRecording()
        } else {
            requestAudioPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
        }
    }

    private fun initializeAudioRecords() {
        if (ActivityCompat.checkSelfPermission(
                requireContext(),
                Manifest.permission.RECORD_AUDIO
            ) != PackageManager.PERMISSION_GRANTED
        ) {
            return
        }
        releaseAudioRecords()

        audioRecordMic1 = AudioRecord(
            MediaRecorder.AudioSource.MIC,
            sampleRate,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            bufferSize
        )

        if (micCount > 1) {
            audioRecordMic2 = AudioRecord(
                MediaRecorder.AudioSource.MIC,
                sampleRate,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                bufferSize
            )
        }
    }

    private fun releaseAudioRecords() {
        audioRecordMic1?.release()
        audioRecordMic2?.release()
        audioRecordMic1 = null
        audioRecordMic2 = null
    }

    private fun startRecording() {
        if (ActivityCompat.checkSelfPermission(
                requireContext(),
                Manifest.permission.RECORD_AUDIO
            ) != PackageManager.PERMISSION_GRANTED
        ) {
            requestAudioPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
            return
        }

        try {
            audioRecordMic1?.startRecording()
            if (micCount > 1) {
                audioRecordMic2?.startRecording()
            }
            isRecording = true
            binding.btnStart.text = "Detener"

            recordingJob?.cancel()
            recordingJob = viewLifecycleOwner.lifecycleScope.launch {
                while (isActive) {
                    try {
                        audioRecordMic1?.read(bufferMic1, 0, bufferSize)
                        if (micCount > 1) {
                            audioRecordMic2?.read(bufferMic2, 0, bufferSize)
                        }
                    } catch (e: Exception) {
                        withContext(Dispatchers.Main) {
                            Toast.makeText(requireContext(), "Error en la grabación", Toast.LENGTH_SHORT).show()
                        }
                        stopRecording(saveReport = false)
                        return@launch
                    }

                    val dBMic1 = calculateDB(bufferMic1)
                    val dBMic2 = if (micCount > 1) calculateDB(bufferMic2) else 0.0

                    decibelHistoryMic1.add(dBMic1)
                    if (micCount > 1) {
                        decibelHistoryMic2.add(dBMic2)
                    }

                    withContext(Dispatchers.Main) {
                        updateUI(dBMic1, dBMic2)
                    }

                    delay(100)
                }
            }
        } catch (e: Exception) {
            Toast.makeText(requireContext(), "Error en la grabación", Toast.LENGTH_SHORT).show()
        }
    }

    private fun stopRecording(saveReport: Boolean) {
        if (!isRecording) return

        recordingJob?.cancel()
        recordingJob = null

        audioRecordMic1?.stop()
        if (micCount > 1) {
            audioRecordMic2?.stop()
        }

        releaseAudioRecords()

        isRecording = false
        binding.btnStart.text = "Iniciar"
        binding.tvDecibelMic1.text = "Mic1: 0 dB"
        binding.tvDecibelMic2.text = "Mic2: 0 dB"
        binding.waveViewMic1.reset()
        binding.waveViewMic2.reset()

        if (saveReport) {
            agregarReporte()
        }

        resetStatistics()
    }

    private fun calculateDB(buffer: ShortArray): Double {
        val rms = sqrt(buffer.map { it.toDouble() * it }.average())
        return if (rms > 0) 20 * log10(rms) else -60.0
    }

    private fun updateUI(dBMic1: Double, dBMic2: Double) {
        binding.tvDecibelMic1.text = getString(R.string.db_value, dBMic1)
        if (micCount > 1) {
            binding.tvDecibelMic2.text = getString(R.string.db_value, dBMic2)
            binding.waveViewMic2.updateDecibelValues(dBMic2)
        } else {
            binding.tvDecibelMic2.text = "Mic2: N/A"
            binding.waveViewMic2.reset()
        }

        binding.waveViewMic1.updateDecibelValues(dBMic1)

        val averageDb = if (micCount > 1) {
            (decibelHistoryMic1.average() + decibelHistoryMic2.average()) / 2
        } else {
            decibelHistoryMic1.average()
        }

        val peakDb = if (micCount > 1) {
            maxOf(decibelHistoryMic1.maxOrNull() ?: 0.0, decibelHistoryMic2.maxOrNull() ?: 0.0)
        } else {
            decibelHistoryMic1.maxOrNull() ?: 0.0
        }

        val minDb = if (micCount > 1) {
            minOf(decibelHistoryMic1.minOrNull() ?: 0.0, decibelHistoryMic2.minOrNull() ?: 0.0)
        } else {
            decibelHistoryMic1.minOrNull() ?: 0.0
        }

        val rangeDb = "%.1f - %.1f".format(minDb, peakDb)

        binding.tvAverage.text = "Promedio: %.1f dB".format(averageDb)
        binding.tvPeak.text = "Pico: %.1f dB".format(peakDb)
        binding.tvRange.text = "Rango: $rangeDb"
    }

    private fun resetStatistics() {
        decibelHistoryMic1.clear()
        decibelHistoryMic2.clear()
        binding.tvAverage.text = "Promedio: 0 dB"
        binding.tvPeak.text = "Pico: 0 dB"
        binding.tvRange.text = "Rango: 0 dB - 0 dB"
    }

    private fun agregarReporte() {
        val averageDecibel = if (micCount > 1) {
            (decibelHistoryMic1.average() + decibelHistoryMic2.average()) / 2
        } else {
            decibelHistoryMic1.average()
        }

        Log.d(TAG, "Intentando guardar reporte - averageDecibel: $averageDecibel, isFinite: ${averageDecibel.isFinite()}")

        if (averageDecibel.isFinite() && averageDecibel > -60.0) {
            val currentTime = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
            val currentDate = SimpleDateFormat("dd/MM/yyyy", Locale.getDefault()).format(Date())
            val report = SonometroReport(0, "$currentTime - $currentDate", averageDecibel)

            val insertedId = databaseManager.insertReport(report)
            Log.d(TAG, "Reporte guardado con ID: $insertedId")

            cargarReportes()
            Log.d(TAG, "Reportes en lista después de guardar: ${reportList.size}")

            Toast.makeText(requireContext(), "Reporte guardado: ${String.format("%.1f", averageDecibel)} dB", Toast.LENGTH_SHORT).show()
        } else {
            Log.e(TAG, "No se pudo guardar reporte - Valor inválido: $averageDecibel")
            Toast.makeText(requireContext(), "No se pudo guardar: medición inválida", Toast.LENGTH_SHORT).show()
        }
    }

    private fun eliminarReporte(id: Long) {
        databaseManager.deleteReport(id)
        cargarReportes()
        Toast.makeText(requireContext(), "Reporte eliminado", Toast.LENGTH_SHORT).show()
    }

    private fun cargarReportes() {
        val reportsFromDB = databaseManager.getAllReports()
        Log.d(TAG, "Reportes en BD: ${reportsFromDB.size}")

        reportList.clear()
        reportList.addAll(reportsFromDB)
        reportAdapter.notifyDataSetChanged()

        Log.d(TAG, "Reportes en adapter: ${reportList.size}")

        // Mostrar mensaje si no hay reportes
        if (reportList.isEmpty()) {
            Toast.makeText(requireContext(), "No hay reportes guardados", Toast.LENGTH_SHORT).show()
        }
    }

    private fun showDeleteDialog(id: Long) {
        AlertDialog.Builder(requireContext())
            .setTitle(getString(R.string.eliminar_reporte_title))
            .setMessage(getString(R.string.eliminar_reporte_message))
            .setPositiveButton(getString(R.string.yes)) { _, _ ->
                eliminarReporte(id)
            }
            .setNegativeButton(getString(R.string.no), null)
            .show()
    }

    override fun onDestroyView() {
        super.onDestroyView()
        stopRecording(saveReport = false)
    }
}