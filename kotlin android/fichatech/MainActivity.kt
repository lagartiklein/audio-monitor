package com.cepalabsfree.fichatech

import android.content.Intent
import android.content.res.Configuration
import android.os.Bundle
import android.view.Menu
import android.view.MenuItem
import android.widget.TextView
import androidx.activity.addCallback
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.widget.Toolbar
import androidx.core.net.toUri
import androidx.core.view.GravityCompat
import androidx.drawerlayout.widget.DrawerLayout
import com.google.android.material.navigation.NavigationView
import androidx.fragment.app.Fragment
import androidx.appcompat.app.ActionBarDrawerToggle
import androidx.fragment.app.FragmentManager
import androidx.appcompat.app.AppCompatDelegate
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import com.cepalabsfree.fichatech.documentos.DocumentosFragment
import com.cepalabsfree.fichatech.fichatecnica.FichaTecnicaFragment
import com.cepalabsfree.fichatech.planta.PlantaEscenarioFragment
import com.cepalabsfree.fichatech.recording.RecordPlaybackFragment
import com.cepalabsfree.fichatech.sonometro.SonometroFragment
import com.cepalabsfree.fichatech.tuner.TunerFragment
import com.google.android.gms.ads.AdRequest
import com.google.android.gms.ads.AdView
import com.google.android.gms.ads.MobileAds
import android.animation.ValueAnimator
import android.graphics.LinearGradient
import android.graphics.Shader
import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.ViewGroup
import androidx.core.animation.doOnEnd
import androidx.core.graphics.toColorInt
import com.cepalabsfree.fichatech.audiostream.NativeAudioStreamActivity
import com.google.android.gms.ads.AdListener
import com.google.android.gms.ads.LoadAdError
import com.google.android.ump.ConsentRequestParameters
import com.google.android.ump.UserMessagingPlatform
import com.google.firebase.auth.FirebaseAuth
import java.util.Locale

class MainActivity : AppCompatActivity(),
    NavigationView.OnNavigationItemSelectedListener,
    FragmentManager.OnBackStackChangedListener {

    private lateinit var drawerLayout: DrawerLayout
    private lateinit var navView: NavigationView
    private lateinit var toolbar: Toolbar
    private lateinit var adView: AdView
    private lateinit var toolbarTitle: TextView
    private lateinit var interstitialAdManager: InterstitialAdManager

    private val sweepHandler = Handler(Looper.getMainLooper())
    private var sweepRunnable: Runnable? = null

    // Variables para detectar pantallas grandes (Android 16)
    private var isTablet = false
    private var isLargeScreen = false


    private var lastInterstitialTime: Long = 0L
    private val INTERSTITIAL_INTERVAL_MS = 8 * 60 * 1000L // 8 minutos en milisegundos

    // Nueva variable para almacenar el inset inferior (altura de la barra de navegación)
    private var bottomInset = 0

    override fun onCreate(savedInstanceState: Bundle?) {
        // ✅ Aplicar idioma guardado ANTES de super.onCreate
        val languagePrefs = getSharedPreferences("language_prefs", MODE_PRIVATE)
        val languageCode = languagePrefs.getString("language", "es") ?: "es"
        applyLanguage(languageCode)

        // Modo claro por defecto, salvo que el usuario haya elegido otro modo
        val prefs = getSharedPreferences("theme_prefs", MODE_PRIVATE)
        val mode = prefs.getInt("theme_mode", AppCompatDelegate.MODE_NIGHT_NO)
        AppCompatDelegate.setDefaultNightMode(mode)

        super.onCreate(savedInstanceState)

        // Habilita Edge-to-Edge ANTES de setContentView (requerido en Android 15)
        enableEdgeToEdge()
        // Eliminado: hideSystemBars() para no ocultar barras de estado
        // Detectar tamaño de pantalla para layouts adaptativos (Android 16)
        setupAdaptiveLayout()

        setContentView(R.layout.activity_main)

        // Inicializar vistas PRIMERO
        initializeAds()  // Inicializar adView sincrónicamente
        setupToolbarAndNavigation()  // Inicializar toolbar, navView, drawerLayout

        // Aplicar WindowInsets para Edge-to-Edge según Android 15 (DESPUÉS de inicializar vistas)
        setupEdgeToEdgeInsets()

        requestConsentAndInitializeAds()  // Solicitar consentimiento y cargar anuncios después
        setupBackPressedCallback()
        loadInitialFragment()

        // ✅ Verificar autenticación al iniciar
        checkAuthentication()

        // --- NUEVO: Forzar título correcto tras rotación/restauración ---
        supportFragmentManager.findFragmentById(R.id.fragment_container)?.let { fragment ->
            when (fragment) {
                is InicioFragment -> setToolbarTitle("Inicio")
                is FichaTecnicaFragment -> setToolbarTitle("Canales")
                is DocumentosFragment -> setToolbarTitle("Documentos")
                is PlantaEscenarioFragment -> setToolbarTitle("Escenario")
                is RecordPlaybackFragment -> setToolbarTitle("Grabaciones")
                is TunerFragment -> setToolbarTitle("Afinador")
                is SonometroFragment -> setToolbarTitle("Sonómetro")
                is AjustesFragment -> setToolbarTitle("Ajustes")
                is AyudaFragment -> setToolbarTitle("Ayuda")
            }
            // --- Ajustar visibilidad del banner y padding tras rotación ---
            when (fragment) {
                is InicioFragment -> {
                    adView.visibility = View.GONE
                    adjustFragmentContainerPadding()
                }
                is PlantaEscenarioFragment -> {
                    adView.visibility = View.GONE
                    adjustFragmentContainerPadding()
                }
                else -> {
                    adView.visibility = View.VISIBLE
                    adjustFragmentContainerPadding()
                }
            }
        }


        // interstitialAdManager se inicializa después del consentimiento en initializeAds()

        // Iniciar el efecto de barrido en el título de la toolbar
        scheduleSweepEffect(toolbarTitle)
    }

    private fun initializeAds() {
        MobileAds.initialize(this) {}

        // ✅ Configurar restricciones de contenido de anuncios (IMPORTANTE PARA POLÍTICAS)
        val requestConfiguration = MobileAds.getRequestConfiguration()
            .toBuilder()
            .setMaxAdContentRating(com.google.android.gms.ads.RequestConfiguration.MAX_AD_CONTENT_RATING_T) // Teen (13+)
            // Si tu app es para niños, cambia a:
            // .setTagForChildDirectedTreatment(RequestConfiguration.TAG_FOR_CHILD_DIRECTED_TREATMENT_TRUE)
            // .setMaxAdContentRating(RequestConfiguration.MAX_AD_CONTENT_RATING_G)
            .build()
        MobileAds.setRequestConfiguration(requestConfiguration)

        adView = findViewById(R.id.adView)
        ViewCompat.setOnApplyWindowInsetsListener(adView) { v, insets ->
            val navBar = insets.getInsets(WindowInsetsCompat.Type.navigationBars())
            val params = v.layoutParams as? ViewGroup.MarginLayoutParams ?: ViewGroup.MarginLayoutParams(v.layoutParams)
            params.bottomMargin = navBar.bottom
            v.layoutParams = params
            insets
        }
        adView.adListener = object : AdListener() {
            override fun onAdFailedToLoad(error: LoadAdError) {
                android.util.Log.e("AdMob", "Banner ad failed to load: ${error.message}")
            }
            override fun onAdLoaded() {
                android.util.Log.d("AdMob", "Banner ad loaded successfully")
            }
        }
        // loadAdBanner() removed to be called after consent
    }

    /**
     * Solicita el consentimiento del usuario para GDPR/CCPA antes de inicializar anuncios
     */
    private fun requestConsentAndInitializeAds() {
        val consentInformation = UserMessagingPlatform.getConsentInformation(this)
        val params = ConsentRequestParameters.Builder()
            .setTagForUnderAgeOfConsent(false) // Ajustar si es necesario para menores
            .build()

        consentInformation.requestConsentInfoUpdate(this, params,
            {
                // Información de consentimiento actualizada
                if (consentInformation.isConsentFormAvailable) {
                    loadAndShowConsentForm()
                } else {
                    loadAdBanner()
                    initializeInterstitial()
                }
            },
            { error ->
                // Manejar error en la solicitud de consentimiento
                android.util.Log.e("UMP", "Error al solicitar consentimiento: ${error.message}")
                loadAdBanner()
                initializeInterstitial() // Proceder sin consentimiento en caso de error
            }
        )
    }

    /**
     * Carga y muestra el formulario de consentimiento
     */
    private fun loadAndShowConsentForm() {
        UserMessagingPlatform.loadConsentForm(this,
            { consentForm ->
                consentForm.show(this) { formError ->
                    if (formError != null) {
                        android.util.Log.e("UMP", "Error en el formulario de consentimiento: ${formError.message}")
                    }
                    // Formulario de consentimiento descartado, proceder con la carga de anuncios
                    loadAdBanner()
                    initializeInterstitial()
                }
            },
            { loadError ->
                android.util.Log.e("UMP", "Error al cargar formulario de consentimiento: ${loadError.message}")
                loadAdBanner()
                initializeInterstitial() // Proceder sin formulario en caso de error
            }
        )
    }

    /**
     * Configura layouts adaptativos para pantallas grandes según Android 16
     * Ref: https://developer.android.com/about/versions/16/behavior-changes-16#large-screens-form-factors
     */
    private fun setupAdaptiveLayout() {
        // Detectar tamaño de pantalla usando Configuration (compatible con API 24+)
        val configuration = resources.configuration
        val smallestWidthDp = configuration.smallestScreenWidthDp

        // Clasificación según Material Design 3 y Android 16
        isTablet = smallestWidthDp >= 600        // Tablets y plegables abiertos
        isLargeScreen = smallestWidthDp >= 840   // Pantallas grandes (tablets grandes, escritorio)
    }

    /**
     * Configura Edge-to-Edge según requisitos de Android 15
     * Ref: https://developer.android.com/about/versions/15/behavior-changes-15#edge-to-edge
     */
    private fun setupEdgeToEdgeInsets() {
        // ✅ Configuración principal del CoordinatorLayout
        val coordinatorLayout = findViewById<androidx.coordinatorlayout.widget.CoordinatorLayout>(R.id.coordinator_layout)
        ViewCompat.setOnApplyWindowInsetsListener(coordinatorLayout) { view, windowInsets ->
            val systemInsets = windowInsets.getInsets(WindowInsetsCompat.Type.systemBars())
            val imeInsets = windowInsets.getInsets(WindowInsetsCompat.Type.ime())

            // Aplicar padding lateral pero no superior/inferior (lo manejan los hijos)
            view.setPadding(
                systemInsets.left,
                0, // No aplicar top padding aquí
                systemInsets.right,
                0  // No aplicar bottom padding aquí
            )

            // Guardar bottom inset para uso posterior
            bottomInset = maxOf(systemInsets.bottom, imeInsets.bottom)

            windowInsets
        }

        // ✅ Configuración del AppBarLayout (barra de estado superior)
        val appBarLayout = findViewById<com.google.android.material.appbar.AppBarLayout>(R.id.appbar_layout)
        ViewCompat.setOnApplyWindowInsetsListener(appBarLayout) { view, windowInsets ->
            val insets = windowInsets.getInsets(WindowInsetsCompat.Type.systemBars())
            view.setPadding(
                0, // El padding lateral lo maneja el CoordinatorLayout
                insets.top,
                0,
                0
            )
            windowInsets
        }

        // ✅ Configuración del Toolbar
        ViewCompat.setOnApplyWindowInsetsListener(toolbar) { _, windowInsets ->
            // El toolbar no necesita padding adicional, lo hereda del AppBarLayout
            windowInsets
        }

        // ✅ Configuración del NavigationView (drawer)
        ViewCompat.setOnApplyWindowInsetsListener(navView) { view, windowInsets ->
            val insets = windowInsets.getInsets(WindowInsetsCompat.Type.systemBars())
            view.setPadding(
                0,
                insets.top,
                0,
                insets.bottom
            )
            windowInsets
        }

        // ✅ Configuración del fragment_container
        val fragmentContainer = findViewById<android.widget.FrameLayout>(R.id.fragment_container)
        ViewCompat.setOnApplyWindowInsetsListener(fragmentContainer) { view, windowInsets ->
            val systemInsets = windowInsets.getInsets(WindowInsetsCompat.Type.systemBars())
            val imeInsets = windowInsets.getInsets(WindowInsetsCompat.Type.ime())

            // Actualizar bottomInset incluyendo teclado
            bottomInset = maxOf(systemInsets.bottom, imeInsets.bottom)

            // Aplicar padding solo si no hay banner visible
            val currentFragment = supportFragmentManager.findFragmentById(R.id.fragment_container)
            val shouldShowBanner = currentFragment !is InicioFragment && currentFragment !is PlantaEscenarioFragment

            view.setPadding(
                0, // El padding lateral lo maneja el CoordinatorLayout
                0,
                0,
                if (shouldShowBanner) 0 else bottomInset
            )

            windowInsets
        }

        // ✅ Configuración del AdView (banner)
        ViewCompat.setOnApplyWindowInsetsListener(adView) { view, windowInsets ->
            val navBar = windowInsets.getInsets(WindowInsetsCompat.Type.navigationBars())
            val params = view.layoutParams as? ViewGroup.MarginLayoutParams
                ?: ViewGroup.MarginLayoutParams(view.layoutParams)
            params.bottomMargin = navBar.bottom
            view.layoutParams = params
            windowInsets
        }
    }

    private fun setupToolbarAndNavigation() {
        toolbar = findViewById(R.id.toolbar)
        toolbarTitle = findViewById(R.id.toolbar_title)
        setSupportActionBar(toolbar)
        supportActionBar?.setDisplayShowTitleEnabled(false)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.setHomeButtonEnabled(true)

        drawerLayout = findViewById(R.id.drawer_layout)
        navView = findViewById(R.id.nav_view)

        ActionBarDrawerToggle(
            this, drawerLayout, toolbar,
            R.string.navigation_drawer_open,
            R.string.navigation_drawer_close
        ).apply {
            isDrawerSlideAnimationEnabled = true
            drawerLayout.addDrawerListener(this)
            syncState()
        }

        navView.setNavigationItemSelectedListener(this)
        supportFragmentManager.addOnBackStackChangedListener(this)
    }

    /**
     * Configura el manejo del botón Back según Android 15
     * onBackPressed() está deprecated, se usa OnBackPressedCallback
     */
    private fun setupBackPressedCallback() {
        onBackPressedDispatcher.addCallback(this) {
            when {
                drawerLayout.isDrawerOpen(GravityCompat.START) -> {
                    drawerLayout.closeDrawer(GravityCompat.START)
                }
                supportFragmentManager.backStackEntryCount > 0 -> {
                    supportFragmentManager.popBackStack()
                }
                else -> {
                    // Si no hay más fragmentos en el stack, terminar la actividad
                    finish()
                }
            }
        }
    }

    private fun loadInitialFragment() {
        if (supportFragmentManager.findFragmentById(R.id.fragment_container) == null) {
            supportFragmentManager.beginTransaction()
                .replace(R.id.fragment_container, InicioFragment())
                .commit()
            navView.setCheckedItem(R.id.nav_home)
            setToolbarTitle("Inicio")
            adView.visibility = View.GONE // Oculta el banner en inicio
        }
    }

    private fun loadAdBanner() {
        val adRequest = AdRequest.Builder().build()
        adView.loadAd(adRequest)
    }

    /**
     * Inicializa el administrador de anuncios intersticiales
     */
    private fun initializeInterstitial() {
        interstitialAdManager = InterstitialAdManager(this, "ca-app-pub-5677027647580832/8238774321")
        interstitialAdManager.loadAd()
        lastInterstitialTime = System.currentTimeMillis()
    }

    override fun onCreateOptionsMenu(menu: Menu?): Boolean {
        menuInflater.inflate(R.menu.menu_main, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        return when (item.itemId) {
            R.id.action_documents -> {
                navigateToFragment(DocumentosFragment())
                setToolbarTitle("Documentos")
                true
            }
            R.id.nav_stage_plan -> {
                navigateToFragment(PlantaEscenarioFragment())
                setToolbarTitle("Escenario")
                true
            }
            R.id.nav_technical_data -> {
                navigateToFragment(FichaTecnicaFragment())
                setToolbarTitle("Canales")
                true
            }
            R.id.nav_home -> {
                navigateToFragment(InicioFragment())
                setToolbarTitle("Home")
                true
            }
            R.id.action_info -> {
                showInfoMenu()
                true
            }
            else -> super.onOptionsItemSelected(item)
        }
    }

    private fun showInfoMenu() {
        // Crear un popup menu para mostrar las opciones de información
        val popup = androidx.appcompat.widget.PopupMenu(this, toolbar.findViewById(R.id.action_info))
        popup.menuInflater.inflate(R.menu.info_menu, popup.menu)

        popup.setOnMenuItemClickListener { item ->
            when (item.itemId) {
                R.id.menu_privacy_policy -> {
                    showPrivacyPolicy()
                    true
                }
                R.id.menu_terms_conditions -> {
                    showTermsAndConditions()
                    true
                }
                R.id.menu_about -> {
                    showAbout()
                    true
                }
                else -> false
            }
        }
        popup.show()
    }

    private fun showPrivacyPolicy() {
        // URL de la política de privacidad
        val privacyUrl = "https://cepalabs.cl/fichatech/privacy-policy"
        val intent = Intent(Intent.ACTION_VIEW, privacyUrl.toUri())
        try {
            startActivity(intent)
        } catch (_: Exception) {
            // Si no hay navegador, mostrar un diálogo con el mensaje
            androidx.appcompat.app.AlertDialog.Builder(this)
                .setTitle(getString(R.string.menu_privacy_policy))
                .setMessage("No se pudo abrir el navegador. Visita: $privacyUrl")
                .setPositiveButton("OK", null)
                .show()
        }
    }

    private fun showTermsAndConditions() {
        // URL de términos y condiciones
        val termsUrl = "https://cepalabs.cl/fichatech/terms-and-conditions"
        val intent = Intent(Intent.ACTION_VIEW, termsUrl.toUri())
        try {
            startActivity(intent)
        } catch (_: Exception) {
            // Si no hay navegador, mostrar un diálogo con el mensaje
            androidx.appcompat.app.AlertDialog.Builder(this)
                .setTitle(getString(R.string.menu_terms_conditions))
                .setMessage("No se pudo abrir el navegador. Visita: $termsUrl")
                .setPositiveButton("OK", null)
                .show()
        }
    }

    private fun showAbout() {
        // Mostrar información "Acerca de" la aplicación
        val versionName = try {
            packageManager.getPackageInfo(packageName, 0).versionName
        } catch (_: Exception) {
            "Desconocida"
        }

        val aboutMessage = """
           
            Versión: $versionName
            
            Aplicación profesional para gestión de Listas de canales de audio, plantas de escenario y herramientas de sonido en vivo.
            
            Desarrollado por: Cepalabs
            Sitio web: cepalabs.cl/fichatech
            
             Para soporte técnico o consultas:
            Email: contacto.cepalabs@gmail.com
            
            © ${java.util.Calendar.getInstance().get(java.util.Calendar.YEAR)} Cepalabs Chile. Todos los derechos reservados.
            
        """.trimIndent()

        androidx.appcompat.app.AlertDialog.Builder(this)
            .setTitle("Acerca de FICHATECH")
            .setMessage(aboutMessage)
            .setPositiveButton("OK", null)
            .setNeutralButton("Eliminar Cuenta") { _, _ ->
                val deleteAccountUrl = "https://cepalabs.cl/fichatech/delete-account"
                val intent = Intent(Intent.ACTION_VIEW, deleteAccountUrl.toUri())
                try {
                    startActivity(intent)
                } catch (_: Exception) {
                    androidx.appcompat.app.AlertDialog.Builder(this)
                        .setTitle("Eliminar Cuenta")
                        .setMessage("Para eliminar tu cuenta, visita:\n\n$deleteAccountUrl\n\nO envía un email a: contacto.cepalabs@gmail.com")
                        .setPositiveButton("OK", null)
                        .show()
                }
            }
            .show()
    }

    private fun navigateToFragment(fragment: Fragment) {
        supportFragmentManager.beginTransaction()
            .replace(R.id.fragment_container, fragment)
            .addToBackStack(null)
            .commit()
        // Oculta el banner si es InicioFragment o PlantaEscenarioFragment, lo muestra en otros casos
        if (fragment is InicioFragment || fragment is PlantaEscenarioFragment) {
            adView.visibility = View.GONE
            adjustFragmentContainerPadding()
        } else {
            adView.visibility = View.VISIBLE
            adjustFragmentContainerPadding()
            // Lógica intersticial: solo si han pasado 8 minutos desde el último
            val now = System.currentTimeMillis()
            if (::interstitialAdManager.isInitialized) {
                if (now - lastInterstitialTime >= INTERSTITIAL_INTERVAL_MS) {
                    interstitialAdManager.showAdIfAvailable(this)
                    lastInterstitialTime = now
                }
            }
        }
    }

    /**
     * Ajusta el padding del fragment_container para que el contenido
     * no se superponga con la barra de navegación (y teclado si está abierto)
     */
    private fun adjustFragmentContainerPadding() {
        val fragmentContainer = findViewById<View>(R.id.fragment_container)
        fragmentContainer.setPadding(
            fragmentContainer.paddingLeft,
            fragmentContainer.paddingTop,
            fragmentContainer.paddingRight,
            bottomInset
        )
    }

    override fun onNavigationItemSelected(item: MenuItem): Boolean {
        val (selectedFragment, title) = when (item.itemId) {
            R.id.nav_home -> Pair(InicioFragment(), "Inicio")
            R.id.nav_technical_data -> Pair(FichaTecnicaFragment(), "Canales")
            R.id.nav_documents -> Pair(DocumentosFragment(), "Documentos")
            R.id.nav_stage_plan -> Pair(PlantaEscenarioFragment(), "Escenario")
            R.id.nav_record_playback -> Pair(RecordPlaybackFragment(), "Grabadora")
            R.id.nav_tuner -> Pair(TunerFragment(), "Afinador")
            R.id.nav_sonometro -> Pair(SonometroFragment(), "Sonómetro")
            R.id.nav_settings -> Pair(AjustesFragment(), "Ajustes")
            R.id.nav_ayuda -> Pair(AyudaFragment(), "Ayuda")
            R.id.nav_exit -> {
                finishAffinity() // Cierra la app completamente
                return true
            }
            R.id.nav_monitor -> {
                val intent = Intent(this, NativeAudioStreamActivity::class.java)
                startActivity(intent)
                return true
            }
            else -> return false
        }

        if (supportFragmentManager.findFragmentById(R.id.fragment_container)?.javaClass != selectedFragment.javaClass) {
            setToolbarTitle(title)
            navigateToFragment(selectedFragment)
        }

        drawerLayout.closeDrawer(GravityCompat.START)
        return true
    }

    override fun onBackStackChanged() {
        supportFragmentManager.findFragmentById(R.id.fragment_container)?.let { fragment ->
            when (fragment) {
                is InicioFragment -> {
                    navView.setCheckedItem(R.id.nav_home)
                    setToolbarTitle("Inicio")
                    adView.visibility = View.GONE
                    adjustFragmentContainerPadding()
                }
                is FichaTecnicaFragment -> {
                    navView.setCheckedItem(R.id.nav_technical_data)
                    setToolbarTitle("Canales")
                    adView.visibility = View.VISIBLE
                    adjustFragmentContainerPadding()
                }
                is DocumentosFragment -> {
                    navView.setCheckedItem(R.id.nav_documents)
                    setToolbarTitle("Documentos")
                    adView.visibility = View.VISIBLE
                    adjustFragmentContainerPadding()
                }
                is PlantaEscenarioFragment -> {
                    navView.setCheckedItem(R.id.nav_stage_plan)
                    setToolbarTitle("Escenario")
                    adView.visibility = View.GONE
                    adjustFragmentContainerPadding()
                }
                is RecordPlaybackFragment -> {
                    navView.setCheckedItem(R.id.nav_record_playback)
                    setToolbarTitle("Grabaciones")
                    adView.visibility = View.VISIBLE
                    adjustFragmentContainerPadding()
                }
                is TunerFragment -> {
                    navView.setCheckedItem(R.id.nav_tuner)
                    setToolbarTitle("Afinador")
                    adView.visibility = View.VISIBLE
                    adjustFragmentContainerPadding()
                }
                is SonometroFragment -> {
                    navView.setCheckedItem(R.id.nav_sonometro)
                    setToolbarTitle("Sonómetro")
                    adView.visibility = View.VISIBLE
                    adjustFragmentContainerPadding()
                }
                is AjustesFragment -> {
                    navView.setCheckedItem(R.id.nav_settings)
                    setToolbarTitle("Ajustes")
                    adView.visibility = View.VISIBLE
                    adjustFragmentContainerPadding()
                }
                is AyudaFragment -> {
                    navView.setCheckedItem(R.id.nav_ayuda)
                    setToolbarTitle("Ayuda")
                    adView.visibility = View.VISIBLE
                    adjustFragmentContainerPadding()
                }
                else -> {
                    adView.visibility = View.VISIBLE
                    adjustFragmentContainerPadding()
                }
            }
        }
    }


    private fun setToolbarTitle(title: String) {
        toolbarTitle.text = title
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
                        "#4FC3F7".toColorInt(), // Azul claro para el barrido
                        textView.currentTextColor
                    ),
                    floatArrayOf(0f, 0.5f, 1f),
                    Shader.TileMode.CLAMP
                )
                textView.paint.shader = shader
                textView.invalidate()
            }
            animator.start()

            animator.doOnEnd {
                textView.paint.shader = null
                textView.invalidate()
            }
        }
    }

    // Ejecuta el efecto de barrido cada 8 segundos
    private fun scheduleSweepEffect(textView: TextView) {
        sweepRunnable?.let { sweepHandler.removeCallbacks(it) }
        sweepRunnable = object : Runnable {
            override fun run() {
                startSweepEffect(textView)
                sweepHandler.postDelayed(this, 8000)
            }
        }
        sweepHandler.postDelayed(sweepRunnable!!, 8000)
    }

    override fun onPause() {
        super.onPause()
        adView.pause()
    }

    override fun onResume() {
        super.onResume()
        adView.resume()
    }

    override fun onDestroy() {
        super.onDestroy()
        sweepRunnable?.let { sweepHandler.removeCallbacks(it) }
        adView.destroy()
    }

    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)
        // Reconfigurar pantallas adaptativas después de rotación
        setupAdaptiveLayout()
        // Reaplicar insets después de cambio de configuración
        setupEdgeToEdgeInsets()
    }

    /**
     * Verificar autenticación del usuario
     */
    private fun checkAuthentication() {
        val userPrefs = getSharedPreferences("user_prefs", MODE_PRIVATE)
        val isGuest = userPrefs.getBoolean("is_guest", false)

        // Si es invitado, permitir acceso sin autenticación
        if (isGuest) {
            return
        }

        // Verificar si hay un usuario autenticado de Firebase
        val currentUser = FirebaseAuth.getInstance().currentUser
        if (currentUser == null || !currentUser.isEmailVerified) {
            // No hay usuario o no está verificado -> redirigir a LoginActivity
            val intent = Intent(this, com.cepalabsfree.fichatech.auth.LoginActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            }
            startActivity(intent)
            finish()
        }
    }

    /**
     * Aplica el idioma guardado a la configuración de la aplicación
     */
    private fun applyLanguage(languageCode: String) {
        val locale = Locale.Builder().setLanguage(languageCode).build()
        Locale.setDefault(locale)
        val config = resources.configuration
        config.setLocale(locale)
        @Suppress("DEPRECATION")
        resources.updateConfiguration(config, resources.displayMetrics)
    }
}
