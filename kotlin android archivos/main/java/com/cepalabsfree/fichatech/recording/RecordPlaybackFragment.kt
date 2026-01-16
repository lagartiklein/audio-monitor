package com.cepalabsfree.fichatech.recording

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.MediaPlayer
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.SystemClock
import android.util.Log
import android.view.LayoutInflater
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.InputMethodManager
import android.widget.*
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import com.cepalabsfree.fichatech.R
import com.cepalabsfree.fichatech.WaveformView

import com.google.android.gms.ads.AdError
import com.google.android.gms.ads.AdRequest
import com.google.android.gms.ads.FullScreenContentCallback
import com.google.android.gms.ads.LoadAdError
import com.google.android.gms.ads.interstitial.InterstitialAd
import com.google.android.gms.ads.interstitial.InterstitialAdLoadCallback
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import java.io.File
import java.io.IOException

class RecordPlaybackFragment : Fragment() {

    // Grabación
    private lateinit var recordingManager: RecordingManager
    private lateinit var waveformView: WaveformView
    private lateinit var recordingNameEditText: EditText
    private lateinit var timerTextView: TextView
    private lateinit var recordButton: Button
    private lateinit var stopRecordButton: Button
    private val handler = Handler()

    // Reproducción
    private lateinit var recordingsListView: ListView
    private lateinit var recordingInfoTextView: TextView
    private lateinit var playButton: Button
    private lateinit var stopPlaybackButton: Button
    private lateinit var deleteButton: Button
    private lateinit var exportButton: Button
    private lateinit var seekBar: SeekBar
    private var selectedRecording: Recording? = null
    private var mediaPlayer: MediaPlayer? = null

    private var timerRunnable: Runnable? = null
    private var startTime = 0L
    private var recordingJob: Job? = null
    private var updateSeekBarRunnable: Runnable? = null

    companion object {
        private const val EXPORT_REQUEST_CODE = 1
        private const val PERMISSION_REQUEST_CODE = 200
    }

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View? {
        val view = inflater.inflate(R.layout.fragment_record_playback, container, false)

        // Inicializar vistas de grabación
        waveformView = view.findViewById(R.id.waveformView)
        recordingNameEditText = view.findViewById(R.id.recordingNameEditText)
        timerTextView = view.findViewById(R.id.timerTextView)
        recordButton = view.findViewById(R.id.recordButton)
        stopRecordButton = view.findViewById(R.id.stopRecordButton)

        // Inicializar vistas de reproducción
        recordingsListView = view.findViewById(R.id.recordingsListView)
        recordingInfoTextView = view.findViewById(R.id.recordingInfoTextView)
        playButton = view.findViewById(R.id.playButton)
        stopPlaybackButton = view.findViewById(R.id.stopPlaybackButton)
        deleteButton = view.findViewById(R.id.deleteButton)
        exportButton = view.findViewById(R.id.exportButton)
        seekBar = view.findViewById(R.id.seekBar)

        stopRecordButton.isEnabled = false
        stopPlaybackButton.isEnabled = false
        seekBar.isEnabled = false

        if (!permissionsGranted()) {
            requestPermissions()
        }

        recordingManager = RecordingManager(
            requireContext(),
            waveformView,
            handler,
            ::startTimer,
            ::stopTimer
        )

        loadRecordings()

        recordButton.setOnClickListener {
            if (recordingNameEditText.text.toString().isBlank()) {
                showToast("Por favor, ingrese un nombre para la grabación")
            } else {
                recordingManager.startRecording(recordingNameEditText.text.toString())
                manageButtons(recording = true, playing = false)
                seekBar.isEnabled = false
                hideKeyboard()
            }
        }

        stopRecordButton.setOnClickListener {
            recordingManager.stopRecording()
            manageButtons(recording = false, playing = false)
            loadRecordings()
            recordingNameEditText.text.clear() // Limpiar el campo de texto del nombre de la grabación
            seekBar.isEnabled = false
        }

        playButton.setOnClickListener {
            selectedRecording?.let {
                playRecording(it.filePath)
                manageButtons(recording = false, playing = true)
                startVisualizerForPlayback()
            } ?: showToast("Por favor, seleccione una grabación")
        }

        stopPlaybackButton.setOnClickListener {
            stopPlaying()
            manageButtons(recording = false, playing = false)
        }

        deleteButton.setOnClickListener {
            selectedRecording?.let {
                deleteRecording(it)
                loadRecordings()
                selectedRecording = null
                recordingInfoTextView.text = "Seleccione una grabación"
            } ?: showToast("Por favor, seleccione una grabación")
        }

        exportButton.setOnClickListener {
            selectedRecording?.let { chooseExportLocation(it) } ?: showToast("Por favor, seleccione una grabación")
        }

        seekBar.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                if (fromUser && mediaPlayer != null) {
                    mediaPlayer?.seekTo(progress)
                    timerTextView.text = formatTime(progress)
                }
            }

            override fun onStartTrackingTouch(seekBar: SeekBar?) {
                if (mediaPlayer == null) {
                    seekBar?.isEnabled = false // Deshabilitar si no hay reproducción
                }
            }
            override fun onStopTrackingTouch(seekBar: SeekBar?) {}
        })

        // Configurar el OnTouchListener para el View principal
        view.setOnTouchListener { _, event ->
            if (event.action == MotionEvent.ACTION_DOWN) {
                hideKeyboard()
            }
            false
        }

        return view
    }

    private fun manageButtons(recording: Boolean, playing: Boolean) {
        recordButton.isEnabled = !recording && !playing
        stopRecordButton.isEnabled = recording
        playButton.isEnabled = !recording && !playing
        stopPlaybackButton.isEnabled = playing
        deleteButton.isEnabled = !recording && !playing
        exportButton.isEnabled = !recording && !playing
        seekBar.isEnabled = playing
    }

    private fun loadRecordings() {
        val recordingStorage = RecordingStorage(requireContext())
        val recordings = recordingStorage.loadRecordings()
        val recordingNames = recordings.map { File(it.filePath).name }
        val adapter = ArrayAdapter(requireContext(), android.R.layout.simple_list_item_1, recordingNames)
        recordingsListView.adapter = adapter

        recordingsListView.setOnItemClickListener { _, _, position, _ ->
            selectedRecording = recordings[position]
            val file = File(selectedRecording!!.filePath)
            if (file.exists()) {
                val duration = getDuration(file)
                recordingInfoTextView.text = "Nombre: ${file.name}\nDuración: $duration"
            } else {
                recordingInfoTextView.text = "Archivo no encontrado"
            }
        }
    }


    private fun startTimer() {
        startTime = SystemClock.uptimeMillis()
        timerRunnable = object : Runnable {
            override fun run() {
                val elapsedMillis = SystemClock.uptimeMillis() - startTime
                val seconds = (elapsedMillis / 1000).toInt()
                val minutes = seconds / 60
                timerTextView.text = String.format("%02d:%02d", minutes, seconds % 60)
                handler.postDelayed(this, 500)
            }
        }
        handler.post(timerRunnable!!)
    }

    private fun stopTimer() {
        timerRunnable?.let {
            handler.removeCallbacks(it)
        }
        timerTextView.text = "00:00"
    }

    private fun playRecording(filePath: String) {
        stopPlaying()
        mediaPlayer = MediaPlayer().apply {
            try {
                setDataSource(filePath)
                prepare()
                start()
                showToast("Reproduciendo...")
                seekBar.max = duration
                seekBar.isEnabled = true // Habilitar la SeekBar al comenzar la reproducción
                startUpdatingSeekBar()
            } catch (e: IOException) {
                showToast("Error al reproducir: ${e.message}")
            }
        }

        mediaPlayer?.setOnCompletionListener {
            stopPlaying()
            manageButtons(recording = false, playing = false)
        }
    }


    private fun startUpdatingSeekBar() {
        seekBar.isEnabled = true // Habilitar la SeekBar al comenzar la reproducción
        updateSeekBarRunnable = object : Runnable {
            override fun run() {
                mediaPlayer?.let {
                    seekBar.progress = it.currentPosition
                    timerTextView.text = formatTime(it.currentPosition)
                    if (it.isPlaying) {
                        handler.postDelayed(this, 1000)
                    }
                }
            }
        }
        handler.post(updateSeekBarRunnable!!)
    }

    private fun stopUpdatingSeekBar() {
        updateSeekBarRunnable?.let {
            handler.removeCallbacks(it)
        }
    }

    private fun formatTime(milliseconds: Int): String {
        val seconds = (milliseconds / 1000) % 60
        val minutes = (milliseconds / 1000) / 60
        return String.format("%02d:%02d", minutes, seconds)
    }

    private fun stopPlaying() {
        mediaPlayer?.release()
        mediaPlayer = null
        waveformView.clearAmplitudes()
        recordingJob?.cancel()
        stopUpdatingSeekBar()
        manageButtons(recording = false, playing = false)
        timerTextView.text = "00:00"
        seekBar.progress = 0
        seekBar.isEnabled = false // Deshabilitar la SeekBar al detener la reproducción
    }

    private fun startVisualizerForPlayback() {
        recordingJob = CoroutineScope(Dispatchers.Default).launch {
            try {
                while (mediaPlayer?.isPlaying == true) {
                    val amplitude = mediaPlayer?.audioSessionId?.toFloat() ?: 0f
                    waveformView.addAmplitude(amplitude)
                    kotlinx.coroutines.delay(100)
                }
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }
    }

    private fun deleteRecording(recording: Recording) {
        val recordingStorage = RecordingStorage(requireContext())
        recordingStorage.deleteRecording(recording)
    }

    private fun chooseExportLocation(recording: Recording) {
        val intent = Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "audio/mpeg"
            putExtra(Intent.EXTRA_TITLE, "${recording.name}.mp3")
        }
        startActivityForResult(intent, EXPORT_REQUEST_CODE)
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == EXPORT_REQUEST_CODE && resultCode == Activity.RESULT_OK) {
            data?.data?.also { uri ->
                selectedRecording?.let { exportRecording(it, uri) }
            }
        }
    }

    private fun exportRecording(recording: Recording, uri: Uri) {
        val inputFile = File(recording.filePath)
        try {
            val outputStream = requireContext().contentResolver.openOutputStream(uri)
            inputFile.inputStream().use { input ->
                outputStream?.use { output ->
                    input.copyTo(output)
                }
            }
            showToast("Grabación exportada: ${uri.path}")
        } catch (e: IOException) {
            showToast("Error al exportar: ${e.message}")
            Log.e("ExportError", "Error exporting recording", e)
        }
    }

    private fun getDuration(file: File): String {
        val mediaPlayer = MediaPlayer()
        mediaPlayer.setDataSource(file.path)
        mediaPlayer.prepare()
        val durationMillis = mediaPlayer.duration
        mediaPlayer.release()

        val seconds = (durationMillis / 1000) % 60
        val minutes = (durationMillis / 1000) / 60
        return String.format("%02d:%02d", minutes, seconds)
    }

    private fun permissionsGranted(): Boolean {
        return ContextCompat.checkSelfPermission(requireContext(), Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED &&
                ContextCompat.checkSelfPermission(requireContext(), Manifest.permission.WRITE_EXTERNAL_STORAGE) == PackageManager.PERMISSION_GRANTED &&
                ContextCompat.checkSelfPermission(requireContext(), Manifest.permission.READ_EXTERNAL_STORAGE) == PackageManager.PERMISSION_GRANTED
    }

    private fun requestPermissions() {
        if (ActivityCompat.shouldShowRequestPermissionRationale(requireActivity(), Manifest.permission.RECORD_AUDIO)) {
            showToast("El permiso de grabación es necesario para grabar audio")
        }
        ActivityCompat.requestPermissions(
            requireActivity(),
            arrayOf(Manifest.permission.RECORD_AUDIO, Manifest.permission.WRITE_EXTERNAL_STORAGE, Manifest.permission.READ_EXTERNAL_STORAGE),
            PERMISSION_REQUEST_CODE
        )
    }

    @Deprecated("Deprecated in Java")
    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == PERMISSION_REQUEST_CODE) {
            if (!permissionsGranted()) {
                showToast("Permisos no concedidos")
            }
        }
    }

    override fun onStop() {
        super.onStop()
        recordingManager.release()
        stopPlaying()
        handler.removeCallbacksAndMessages(null) // Añadir esta línea

    }

    private fun hideKeyboard() {
        val imm = requireContext().getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        imm.hideSoftInputFromWindow(view?.windowToken, 0)
    }

    private fun showToast(message: String) {
        Toast.makeText(context, message, Toast.LENGTH_SHORT).show()
    }
}
