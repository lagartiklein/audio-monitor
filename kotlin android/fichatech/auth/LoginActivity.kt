package com.cepalabsfree.fichatech.auth

import android.content.Context
import android.content.Intent
import android.content.res.Configuration
import android.os.Bundle
import android.util.Log
import android.view.animation.AccelerateDecelerateInterpolator
import android.widget.Toast
import android.widget.TextView
import android.animation.ValueAnimator
import android.graphics.LinearGradient
import android.graphics.Shader
import android.graphics.Color
import android.os.Handler
import android.os.Looper
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.ActivityResultLauncher
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.app.AppCompatDelegate
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.animation.doOnEnd
import androidx.credentials.CredentialManager
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import androidx.credentials.GetCredentialResponse
import androidx.credentials.exceptions.GetCredentialException
import androidx.lifecycle.lifecycleScope
import com.cepalabsfree.fichatech.MainActivity
import com.cepalabsfree.fichatech.R
import com.cepalabsfree.fichatech.databinding.ActivityLoginBinding
import com.google.android.gms.auth.api.signin.GoogleSignIn
import com.google.android.gms.auth.api.signin.GoogleSignInClient
import com.google.android.gms.auth.api.signin.GoogleSignInOptions
import com.google.android.gms.common.api.ApiException
import com.google.android.libraries.identity.googleid.GetGoogleIdOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.FirebaseAuthEmailException
import com.google.firebase.auth.FirebaseAuthException
import com.google.firebase.auth.FirebaseAuthInvalidCredentialsException
import com.google.firebase.auth.FirebaseAuthInvalidUserException
import com.google.firebase.auth.FirebaseAuthUserCollisionException
import com.google.firebase.auth.FirebaseAuthWeakPasswordException
import com.google.firebase.auth.GoogleAuthProvider
import kotlinx.coroutines.launch

class LoginActivity : AppCompatActivity() {
    private lateinit var binding: ActivityLoginBinding
    private lateinit var auth: FirebaseAuth
    private lateinit var googleSignInClient: GoogleSignInClient
    private lateinit var signInLauncher: ActivityResultLauncher<Intent>
    private lateinit var credentialManager: CredentialManager
    private val sweepHandler = Handler(Looper.getMainLooper())
    private var sweepRunnable: Runnable? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        AppCompatDelegate.setDefaultNightMode(AppCompatDelegate.MODE_NIGHT_NO)
        setTheme(R.style.Theme_Fichatech_Light)
        super.onCreate(savedInstanceState)

        // Configurar Edge to Edge
        enableEdgeToEdge()
        // Ocultar las barras del sistema (status bar y navigation bar)


        binding = ActivityLoginBinding.inflate(layoutInflater)
        setContentView(binding.root)

        // Configurar insets
        setupWindowInsets()

        // Animación para el título
        binding.tvTitle.apply {
            alpha = 0f
            scaleX = 0.8f
            scaleY = 0.8f
            animate()
                .alpha(1f)
                .scaleX(1f)
                .scaleY(1f)
                .setDuration(900)
                .setInterpolator(AccelerateDecelerateInterpolator())
                .withEndAction {
                    startSweepEffect(this)
                    scheduleSweepEffect()
                }
                .start()
        }


        // Inicializar Firebase Auth y Credential Manager
        auth = FirebaseAuth.getInstance()
        credentialManager = CredentialManager.create(this)

        // Configurar Google Sign In
        val webClientId = getString(R.string.default_web_client_id)
        Log.d("LoginActivity", "Web Client ID: $webClientId")

        val gso = GoogleSignInOptions.Builder(GoogleSignInOptions.DEFAULT_SIGN_IN)
            .requestIdToken(webClientId)
            .requestEmail()
            .build()

        googleSignInClient = GoogleSignIn.getClient(this, gso)
        Log.d("LoginActivity", "Google Sign-In Client configurado correctamente")

        // Configurar ActivityResultLauncher para Google Sign In
        signInLauncher = registerForActivityResult(
            ActivityResultContracts.StartActivityForResult()
        ) { result ->
            Log.d("LoginActivity", "Resultado de Google Sign-In recibido. ResultCode: ${result.resultCode}")
            if (result.resultCode == RESULT_OK) {
                val task = GoogleSignIn.getSignedInAccountFromIntent(result.data)
                try {
                    val account = task.getResult(ApiException::class.java)
                    Log.d("LoginActivity", "Cuenta de Google obtenida: ${account.email}")
                    if (account.idToken != null) {
                        Log.d("LoginActivity", "ID Token obtenido, autenticando con Firebase...")
                        firebaseAuthWithGoogle(account.idToken!!)
                    } else {
                        Log.e("LoginActivity", "ID Token es nulo")
                        Toast.makeText(this, "Error: No se pudo obtener el token de Google", Toast.LENGTH_LONG).show()
                    }
                } catch (e: ApiException) {
                    Log.e("LoginActivity", "Error en Google Sign In - Código: ${e.statusCode}", e)
                    Toast.makeText(this, "Error en Google Sign In: ${e.message} (Código: ${e.statusCode})", Toast.LENGTH_LONG).show()
                }
            } else if (result.resultCode == RESULT_CANCELED) {
                Log.d("LoginActivity", "Google Sign-In cancelado por el usuario")
                Toast.makeText(this, "Inicio de sesión cancelado", Toast.LENGTH_SHORT).show()
            } else {
                Log.e("LoginActivity", "Google Sign-In falló con código: ${result.resultCode}")
                Toast.makeText(this, "Error en Google Sign-In", Toast.LENGTH_SHORT).show()
            }
        }

        // Intentar autenticación automática al iniciar
        attemptAutoSignIn()
        setupClickListeners()
    }

    // Efecto de barrido tipo agua para el título
    private fun startSweepEffect(textView: TextView) {
        textView.post {
            val textWidth = textView.paint.measureText(textView.text.toString())
            val viewWidth = textView.width.toFloat()
            val gradientWidth = textWidth / 2

            val animator = ValueAnimator.ofFloat(-gradientWidth, viewWidth + gradientWidth)
            animator.duration = 1200
            animator.addUpdateListener { animation ->
                val translateX = animation.animatedValue as Float
                val shader = LinearGradient(
                    translateX, 0f, translateX + gradientWidth, 0f,
                    intArrayOf(
                        textView.currentTextColor,
                        Color.parseColor("#53B8A9"),
                        textView.currentTextColor
                    ),
                    floatArrayOf(0f, 0.5f, 1f),
                    Shader.TileMode.CLAMP
                )
                textView.paint.shader = shader
                textView.invalidate()
            }
            animator.start()

            // Al terminar, deja el color original
            animator.doOnEnd {
                textView.paint.shader = null
                textView.invalidate()
            }
        }
    }

    // Ejecuta el efecto de barrido cada 8 segundos
    private fun scheduleSweepEffect() {
        sweepRunnable?.let { sweepHandler.removeCallbacks(it) }
        sweepRunnable = object : Runnable {
            override fun run() {
                startSweepEffect(binding.tvTitle)
                sweepHandler.postDelayed(this, 8000)
            }
        }
        sweepHandler.postDelayed(sweepRunnable!!, 8000)
    }

    override fun onDestroy() {
        super.onDestroy()
        sweepRunnable?.let { sweepHandler.removeCallbacks(it) }
    }

    private fun attemptAutoSignIn() {
        lifecycleScope.launch {
            try {
                val googleIdOption = GetGoogleIdOption.Builder()
                    .setFilterByAuthorizedAccounts(true)
                    .setServerClientId(getString(R.string.default_web_client_id))
                    .setAutoSelectEnabled(true)
                    .build()

                val request = GetCredentialRequest.Builder()
                    .addCredentialOption(googleIdOption)
                    .build()

                val response = credentialManager.getCredential(
                    request = request,
                    context = this@LoginActivity
                )

                handleCredentialResponse(response)
            } catch (e: GetCredentialException) {
                Log.d("LoginActivity", "Autenticación automática no disponible: ${e.message}")
            }
        }
    }

    private fun handleCredentialResponse(response: GetCredentialResponse) {
        val credential = response.credential

        when (credential) {
            is CustomCredential -> {
                if (credential.type == GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL) {
                    try {
                        val googleIdTokenCredential = GoogleIdTokenCredential
                            .createFrom(credential.data)
                        firebaseAuthWithGoogle(googleIdTokenCredential.idToken)
                    } catch (e: Exception) {
                        Log.e("LoginActivity", "Error al procesar credencial de Google", e)
                        Toast.makeText(this, "Error al iniciar sesión automáticamente", Toast.LENGTH_SHORT).show()
                    }
                }
            }
            else -> Log.e("LoginActivity", "Tipo de credencial no reconocido")
        }
    }

    private fun setupClickListeners() {
        binding.btnEmailLogin.setOnClickListener {
            val email = binding.etEmail.text.toString().trim()
            val password = binding.etPassword.text.toString()

            when {
                email.isEmpty() -> {
                    Toast.makeText(this, "Por favor ingresa tu correo electrónico", Toast.LENGTH_SHORT).show()
                    binding.etEmail.requestFocus()
                }
                !android.util.Patterns.EMAIL_ADDRESS.matcher(email).matches() -> {
                    Toast.makeText(this, "Por favor ingresa un correo válido", Toast.LENGTH_SHORT).show()
                    binding.etEmail.requestFocus()
                }
                password.isEmpty() -> {
                    Toast.makeText(this, "Por favor ingresa tu contraseña", Toast.LENGTH_SHORT).show()
                    binding.etPassword.requestFocus()
                }
                else -> {
                    loginWithEmail(email, password)
                }
            }
        }

        // Cambia el listener al LinearLayout personalizado
        binding.btnGoogleLogin.setOnClickListener {
            signInWithGoogle()
        }

        binding.btnGuest.setOnClickListener {
            val prefs = getSharedPreferences("user_prefs", Context.MODE_PRIVATE)
            prefs.edit().putBoolean("is_guest", true).apply()
            startActivity(Intent(this, MainActivity::class.java))
            finish()
        }

        binding.tvPrivacyPolicy.setOnClickListener {
            val intent = Intent(this, PrivacyPolicyActivity::class.java)
            startActivity(intent)
        }

        binding.btnRegister.setOnClickListener {
            val email = binding.etEmail.text.toString().trim()
            val password = binding.etPassword.text.toString()

            when {
                email.isEmpty() -> {
                    Toast.makeText(this, "Por favor ingresa tu correo electrónico", Toast.LENGTH_SHORT).show()
                    binding.etEmail.requestFocus()
                }
                !android.util.Patterns.EMAIL_ADDRESS.matcher(email).matches() -> {
                    Toast.makeText(this, "Por favor ingresa un correo válido", Toast.LENGTH_SHORT).show()
                    binding.etEmail.requestFocus()
                }
                password.isEmpty() -> {
                    Toast.makeText(this, "Por favor ingresa una contraseña", Toast.LENGTH_SHORT).show()
                    binding.etPassword.requestFocus()
                }
                password.length < 6 -> {
                    Toast.makeText(this, "La contraseña debe tener al menos 6 caracteres", Toast.LENGTH_SHORT).show()
                    binding.etPassword.requestFocus()
                }
                else -> {
                    registerWithEmail(email, password)
                }
            }
        }
    }

    private fun loginWithEmail(email: String, password: String) {
        auth.signInWithEmailAndPassword(email, password)
            .addOnCompleteListener(this) { task ->
                if (task.isSuccessful) {
                    val user = auth.currentUser
                    if (user != null) {
                        if (user.isEmailVerified) {
                            navigateToMain()
                        } else {
                            user.sendEmailVerification()
                            Toast.makeText(this, "Correo no verificado. Se envió un nuevo correo a ${user.email}", Toast.LENGTH_LONG).show()
                            startActivity(Intent(this, VerificationPendingActivity::class.java))
                            finish()
                        }
                    }
                } else {
                    val errorMsg = getFirebaseAuthErrorMessage(task.exception)
                    Toast.makeText(this, errorMsg, Toast.LENGTH_LONG).show()
                }
            }
    }

    private fun registerWithEmail(email: String, password: String) {
        auth.createUserWithEmailAndPassword(email, password)
            .addOnCompleteListener(this) { task ->
                if (task.isSuccessful) {
                    val user = auth.currentUser
                    user?.sendEmailVerification()
                    Toast.makeText(this, "Se envió un correo de verificación a ${user?.email}", Toast.LENGTH_LONG).show()
                    startActivity(Intent(this, VerificationPendingActivity::class.java))
                    finish()
                } else {
                    Toast.makeText(this, "Error en el registro: ${task.exception?.message}", Toast.LENGTH_SHORT).show()
                }
            }
    }

    private fun signInWithGoogle() {
        Log.d("LoginActivity", "Iniciando Google Sign-In...")
        try {
            val signInIntent = googleSignInClient.signInIntent
            signInLauncher.launch(signInIntent)
        } catch (e: Exception) {
            Log.e("LoginActivity", "Error al iniciar Google Sign-In", e)
            Toast.makeText(this, "Error al iniciar Google Sign-In: ${e.message}", Toast.LENGTH_LONG).show()
        }
    }

    private fun firebaseAuthWithGoogle(idToken: String) {
        Log.d("LoginActivity", "Iniciando autenticación de Firebase con Google...")
        val credential = GoogleAuthProvider.getCredential(idToken, null)
        auth.signInWithCredential(credential)
            .addOnCompleteListener(this) { task ->
                if (task.isSuccessful) {
                    Log.d("LoginActivity", "Autenticación de Firebase exitosa")
                    val user = auth.currentUser
                    if (user != null) {
                        Log.d("LoginActivity", "Usuario autenticado: ${user.email}, UID: ${user.uid}")
                        // Las cuentas de Google ya están verificadas por defecto
                        // No es necesario enviar correo de verificación
                        Toast.makeText(this, "Inicio de sesión exitoso con Google", Toast.LENGTH_SHORT).show()
                        navigateToMain()
                    } else {
                        Log.e("LoginActivity", "Usuario nulo después de autenticación exitosa")
                        Toast.makeText(
                            this,
                            "Error: Usuario nulo después de autenticación",
                            Toast.LENGTH_SHORT
                        ).show()
                    }
                } else {
                    Log.e("LoginActivity", "Error de autenticación de Firebase", task.exception)
                    val errorMsg = getFirebaseAuthErrorMessage(task.exception)
                    Toast.makeText(this, errorMsg, Toast.LENGTH_LONG).show()
                }
            }
    }

    private fun navigateToMain() {
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        }
        startActivity(intent)
        finish()
    }

    private fun getFirebaseAuthErrorMessage(exception: Exception?): String {
        return when (exception) {
            is FirebaseAuthInvalidUserException -> "Usuario no encontrado. ¿Estás registrado?"
            is FirebaseAuthInvalidCredentialsException -> "Contraseña o correo incorrectos."
            is FirebaseAuthUserCollisionException -> "Este correo ya está registrado."
            is FirebaseAuthWeakPasswordException -> "La contraseña es muy débil (mínimo 6 caracteres)."
            is FirebaseAuthEmailException -> "Hubo un error con el correo electrónico."
            is FirebaseAuthException -> "Error de autenticación: ${exception.message}"
            else -> "error"
        }
    }


    private fun setupWindowInsets() {
        // Aplicar insets al ScrollView principal para edge-to-edge
        ViewCompat.setOnApplyWindowInsetsListener(binding.root) { view, windowInsets ->
            val systemInsets = windowInsets.getInsets(WindowInsetsCompat.Type.systemBars())

            // Aplicar padding en todos los lados (izquierda, arriba, derecha, abajo)
            view.setPadding(
                systemInsets.left,
                systemInsets.top,
                systemInsets.right,
                systemInsets.bottom
            )

            windowInsets
        }
    }


    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)
        if (newConfig.orientation == Configuration.ORIENTATION_LANDSCAPE) {
        }
    }
}
