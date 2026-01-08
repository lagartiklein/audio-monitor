package com.cepalabsfree.fichatech.auth

import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import com.cepalabsfree.fichatech.MainActivity
import com.cepalabsfree.fichatech.R
import com.google.firebase.auth.FirebaseAuth

class VerificationPendingActivity : AppCompatActivity() {

    private lateinit var auth: FirebaseAuth

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Configurar Edge to Edge
        enableEdgeToEdge()

        setContentView(R.layout.activity_verification_pending)

        // Configurar insets
        setupWindowInsets()

        auth = FirebaseAuth.getInstance()
        val user = auth.currentUser
        val email = user?.email

        val txtEmail = findViewById<TextView>(R.id.txt_verification_email)
        val btnCheck = findViewById<Button>(R.id.btn_check_verification)

        // Mostrar mensaje con el correo
        txtEmail.text = "Correo: $email\nRevisa tu bandeja de entrada y spam."

        btnCheck.setOnClickListener {
            user?.reload()?.addOnCompleteListener { task ->
                if (task.isSuccessful) {
                    if (auth.currentUser?.isEmailVerified == true) {
                        navigateToMain()
                    } else {
                        Toast.makeText(this, "Aún no has verificado tu correo.", Toast.LENGTH_SHORT).show()
                    }
                } else {
                    Toast.makeText(this, "Error al verificar el estado.", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun setupWindowInsets() {
        val rootView = findViewById<android.view.View>(android.R.id.content)
        ViewCompat.setOnApplyWindowInsetsListener(rootView) { view, windowInsets ->
            val insets = windowInsets.getInsets(WindowInsetsCompat.Type.systemBars())
            view.setPadding(
                insets.left,
                insets.top,
                insets.right,
                insets.bottom
            )
            WindowInsetsCompat.CONSUMED
        }
    }

    private fun navigateToMain() {
        val intent = Intent(this, MainActivity::class.java)
        intent.flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        startActivity(intent)
        finish()
    }
}
