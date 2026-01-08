package com.cepalabsfree.fichatech.planta

import android.content.Context
import android.graphics.*
import android.util.Log
import android.view.View
import android.widget.FrameLayout
import android.widget.ImageView
import com.cepalabsfree.fichatech.R
import androidx.core.graphics.createBitmap
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

object PlantaRenderer {

    // Dimensiones base consistentes con el fragmento
    private const val BASE_IMAGE_WIDTH = 740f
    private const val BASE_IMAGE_HEIGHT = 415f
    private const val ELEMENT_SIZE = 120

    // Cache para bitmaps (mejora rendimiento)
    private val bitmapCache = mutableMapOf<String, Bitmap>()
    private var backgroundBitmap: Bitmap? = null

    /**
     * Renderiza una planta de escenario como Bitmap de manera segura y eficiente
     * Cumple con las políticas de Google Play sobre memoria y rendimiento
     */
    suspend fun renderPlantaAsBitmap(
        context: Context,
        sceneName: String,
        dbHelper: PlantaEscenarioDatabaseHelper
    ): Bitmap? = withContext(Dispatchers.IO) {
        try {
            // 1. Validar contexto y parámetros
            if (!isContextValid(context)) {
                Log.w("PlantaRenderer", "Contexto no válido para renderizar")
                return@withContext null
            }

            if (sceneName.isBlank()) {
                Log.w("PlantaRenderer", "Nombre de escena vacío")
                return@withContext null
            }

            // 2. Crear contenedor con dimensiones base
            val frameLayout = createContainer(context)

            // 3. Obtener y agregar elementos usando coordenadas relativas
            val elementos = dbHelper.getSceneElements(sceneName)
            if (elementos.isEmpty()) {
                Log.w("PlantaRenderer", "No hay elementos para renderizar en la escena: $sceneName")
                return@withContext renderEmptyScene(context)
            }

            addElementsToContainer(context, frameLayout, elementos)

            // 4. Renderizar a bitmap
            renderToBitmap(context, frameLayout)

        } catch (e: OutOfMemoryError) {
            Log.e("PlantaRenderer", "Error de memoria al renderizar planta", e)
            cleanupResources()
            System.gc()
            null
        } catch (e: Exception) {
            Log.e("PlantaRenderer", "Error al renderizar planta: ${e.message}", e)
            cleanupResources()
            null
        }
    }

    /**
     * Valida que el contexto sea seguro de usar
     */
    private fun isContextValid(context: Context): Boolean {
        return try {
            when (context) {
                is android.app.Activity -> !context.isFinishing && !context.isDestroyed
                else -> true
            }
        } catch (e: Exception) {
            false
        }
    }

    /**
     * Crea el contenedor principal para los elementos
     */
    private fun createContainer(context: Context): FrameLayout {
        return FrameLayout(context).apply {
            layoutParams = FrameLayout.LayoutParams(
                BASE_IMAGE_WIDTH.toInt(),
                BASE_IMAGE_HEIGHT.toInt()
            )
            setWillNotDraw(false) // Asegurar que se dibuje
            setBackgroundColor(Color.TRANSPARENT) // Fondo transparente
        }
    }

    /**
     * Agrega elementos al contenedor con manejo seguro de errores
     */
    private fun addElementsToContainer(
        context: Context,
        container: FrameLayout,
        elementos: List<PlantaEscenarioDatabaseHelper.SceneElement>
    ) {
        elementos.forEachIndexed { index, elemento ->
            try {
                val imageView = createElementImageView(context, elemento)
                container.addView(imageView)
            } catch (e: Exception) {
                Log.w("PlantaRenderer", "Error agregando elemento $index: ${elemento.iconName}", e)
                // Continuar con los siguientes elementos en lugar de fallar completamente
            }
        }
    }

    /**
     * Crea una ImageView para un elemento individual
     */
    private fun createElementImageView(
        context: Context,
        elemento: PlantaEscenarioDatabaseHelper.SceneElement
    ): ImageView {
        return ImageView(context).apply {
            // Obtener recurso de icono con fallback seguro
            val iconResource = try {
                getIconResource(elemento.iconName)
            } catch (e: Exception) {
                Log.w("PlantaRenderer", "Icono no encontrado: ${elemento.iconName}, usando fallback")
                R.drawable.exitico
            }
            setImageResource(iconResource)

            // Calcular posición basada en coordenadas relativas y dimensiones base
            val leftMargin = (elemento.xRel * BASE_IMAGE_WIDTH).toInt() - ELEMENT_SIZE / 2
            val topMargin = (elemento.yRel * BASE_IMAGE_HEIGHT).toInt() - ELEMENT_SIZE / 2

            layoutParams = FrameLayout.LayoutParams(ELEMENT_SIZE, ELEMENT_SIZE).apply {
                this.leftMargin = leftMargin.coerceIn(0, BASE_IMAGE_WIDTH.toInt() - ELEMENT_SIZE)
                this.topMargin = topMargin.coerceIn(0, BASE_IMAGE_HEIGHT.toInt() - ELEMENT_SIZE)
            }

            // Aplicar escala con límites seguros
            val safeScale = elemento.scale.coerceIn(0.1f, 5.0f)
            scaleX = safeScale
            scaleY = safeScale

            // Mejorar calidad de renderizado
            setLayerType(View.LAYER_TYPE_HARDWARE, null)
            adjustViewBounds = true
            contentDescription = elemento.iconName // Accesibilidad
        }
    }

    /**
     * Renderiza el contenedor completo a bitmap
     */
    private fun renderToBitmap(context: Context, frameLayout: FrameLayout): Bitmap? {
        var bitmap: Bitmap? = null

        try {
            // Medir y dibujar con dimensiones base
            frameLayout.measure(
                View.MeasureSpec.makeMeasureSpec(BASE_IMAGE_WIDTH.toInt(), View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(BASE_IMAGE_HEIGHT.toInt(), View.MeasureSpec.EXACTLY)
            )
            frameLayout.layout(0, 0, BASE_IMAGE_WIDTH.toInt(), BASE_IMAGE_HEIGHT.toInt())

            // Crear bitmap con configuración optimizada
            bitmap = try {
                createBitmap(BASE_IMAGE_WIDTH.toInt(), BASE_IMAGE_HEIGHT.toInt(), Bitmap.Config.ARGB_8888)
            } catch (e: OutOfMemoryError) {
                // Intentar con configuración más eficiente
                Log.w("PlantaRenderer", "Usando configuración RGB_565 por memoria")
                createBitmap(BASE_IMAGE_WIDTH.toInt(), BASE_IMAGE_HEIGHT.toInt(), Bitmap.Config.RGB_565)
            }

            val canvas = Canvas(bitmap)

            // Dibujar fondo del escenario
            drawBackground(context, canvas)

            // Dibujar el frameLayout
            frameLayout.draw(canvas)

            return bitmap

        } catch (e: OutOfMemoryError) {
            Log.e("PlantaRenderer", "Memoria insuficiente para crear bitmap")
            bitmap?.recycle()
            System.gc()
            return null
        } catch (e: Exception) {
            Log.e("PlantaRenderer", "Error en renderizado: ${e.message}", e)
            bitmap?.recycle()
            return null
        }
    }

    /**
     * Dibuja el fondo del escenario con manejo seguro
     */
    private fun drawBackground(context: Context, canvas: Canvas) {
        try {
            val background = context.getDrawable(R.drawable.escenarioplanta)
            if (background != null) {
                background.setBounds(0, 0, BASE_IMAGE_WIDTH.toInt(), BASE_IMAGE_HEIGHT.toInt())
                background.draw(canvas)
            } else {
                // Fallback: fondo sólido
                canvas.drawColor(Color.parseColor("#F0F0F0"))
                Log.w("PlantaRenderer", "Fondo no disponible, usando fallback")
            }
        } catch (e: Exception) {
            Log.w("PlantaRenderer", "No se pudo dibujar el fondo, usando fallback", e)
            // Dibujar fondo de fallback
            canvas.drawColor(Color.LTGRAY)
        }
    }

    /**
     * Renderiza una escena vacía (fallback)
     */
    private fun renderEmptyScene(context: Context): Bitmap? {
        return try {
            val bitmap = createBitmap(BASE_IMAGE_WIDTH.toInt(), BASE_IMAGE_HEIGHT.toInt(), Bitmap.Config.ARGB_8888)
            val canvas = Canvas(bitmap)
            drawBackground(context, canvas)

            // Dibujar mensaje de escena vacía
            val paint = Paint().apply {
                color = Color.DKGRAY
                textSize = 24f
                textAlign = Paint.Align.CENTER
            }
            canvas.drawText(
                "Escena vacía",
                BASE_IMAGE_WIDTH / 2,
                BASE_IMAGE_HEIGHT / 2,
                paint
            )

            bitmap
        } catch (e: Exception) {
            Log.e("PlantaRenderer", "Error renderizando escena vacía", e)
            null
        }
    }

    /**
     * Limpia recursos para evitar memory leaks
     */
    private fun cleanupResources() {
        try {
            bitmapCache.values.forEach { bitmap ->
                if (!bitmap.isRecycled) {
                    bitmap.recycle()
                }
            }
            bitmapCache.clear()

            backgroundBitmap?.let {
                if (!it.isRecycled) {
                    it.recycle()
                }
            }
            backgroundBitmap = null
        } catch (e: Exception) {
            Log.w("PlantaRenderer", "Error limpiando recursos", e)
        }
    }

    /**
     * Limpia cache explícitamente (llamar desde onDestroy)
     */
    fun clearCache() {
        cleanupResources()
    }

    /**
     * Obtiene el recurso de icono con cache básico
     */
    fun getIconResource(iconName: String): Int {
        return when (iconName) {
            "Batería" -> R.drawable.bateria1
            "Batería 2" -> R.drawable.bateria2
            "Batería 3" -> R.drawable.bateria3
            "Cajon peruano" -> R.drawable.cajonperuano
            "Bajo" -> R.drawable.bajo4
            "Bajo 2" -> R.drawable.bajo2
            "Bajo 3" -> R.drawable.bajo3
            "Contrabajo" -> R.drawable.contrabajo
            "Guitarra electrica" -> R.drawable.guitarraleectrica1
            "Guitarra electrica 2" -> R.drawable.guitarraelectrica2
            "Guitarra electrica 3" -> R.drawable.guitarraelectrica3
            "Guitarra acustica" -> R.drawable.guitarraacustica
            "Guitarra electroacustica" -> R.drawable.guitarraacustica2
            "Piano" -> R.drawable.piano1
            "Piano 2" -> R.drawable.piano2
            "Acordeon" -> R.drawable.acordeon
            "Melodica" -> R.drawable.melodica
            "Pendrive" -> R.drawable.pendrive
            "Pendrive 2" -> R.drawable.pendrive2
            "Celular" -> R.drawable.celular
            "Trompeta" -> R.drawable.trompeta
            "Conga" -> R.drawable.conga
            "Congas" -> R.drawable.congas2
            "Gong" -> R.drawable.gong
            "Djembe" -> R.drawable.djembe
            "Tumba" -> R.drawable.tumba
            "Pandero" -> R.drawable.pandero
            "Cabaza" -> R.drawable.cabaza
            "Castanuelas" -> R.drawable.castanuelas
            "Bongos" -> R.drawable.bongos
            "Shekere" -> R.drawable.shekere
            "Maracas" -> R.drawable.maracas
            "Huiro" -> R.drawable.huiro
            "Timbales" -> R.drawable.timbales
            "Trombon" -> R.drawable.trombon
            "Saxo" -> R.drawable.saxo
            "Tuba" -> R.drawable.tuba
            "Clarinete" -> R.drawable.clarinete
            "Teclado" -> R.drawable.teclado
            "Organo" -> R.drawable.organo
            "Estudio" -> R.drawable.estudio
            "Armonica" -> R.drawable.armonica
            "Arpa" -> R.drawable.arpa
            "Balalaica" -> R.drawable.balalaica
            "Banjo" -> R.drawable.banjo
            "Bombo leguero" -> R.drawable.bomboleguero
            "Campanas tubulares" -> R.drawable.campanastubulares
            "Charango" -> R.drawable.charango
            "Flauta" -> R.drawable.flauta
            "Clavecin" -> R.drawable.clavecin
            "Corneta" -> R.drawable.corneta
            "Corno frances" -> R.drawable.cornofrances
            "Cortina" -> R.drawable.cortina
            "Didgeridoo" -> R.drawable.didgeridoo
            "Fagot" -> R.drawable.fagot
            "Flauta traversa" -> R.drawable.flautatraversa
            "Koto" -> R.drawable.koto
            "Laud" -> R.drawable.laud
            "Mandolina" -> R.drawable.mandolina
            "Oboe" -> R.drawable.oboe
            "Quena" -> R.drawable.quena
            "Sintetizador" -> R.drawable.sintetizador
            "Sitar" -> R.drawable.sitar
            "Timbalorquesta" -> R.drawable.timbalorquesta
            "Ukelele" -> R.drawable.ukelele
            "Violonchelo" -> R.drawable.violonchelo
            "Violin" -> R.drawable.violin
            "Xilofono" -> R.drawable.xilofono
            "Zampona" -> R.drawable.zampona
            "Cuatro" -> R.drawable.cuatro

            "Voz 1" -> R.drawable.microfono3
            "Voz 2" -> R.drawable.microfono4
            "Voz 3" -> R.drawable.microfono5
            "Micrófono estudio" -> R.drawable.microfonoestudio
            "Mac" -> R.drawable.mac
            "Notebook" -> R.drawable.notebook
            "Tornamesa" -> R.drawable.torna

            "Monitor de piso" -> R.drawable.monitorpiso1
            "Monitor de piso 2" -> R.drawable.monitorpiso2
            "Monitor de piso 3" -> R.drawable.monitorpiso3
            "Side fill" -> R.drawable.drumfill
            "Side fill 2" -> R.drawable.drumfill2
            "Drum fill" -> R.drawable.sidefill
            "Drum fill 2" -> R.drawable.sidefill2
            "Array" -> R.drawable.array1
            "Array 2" -> R.drawable.array2
            "Array 3" -> R.drawable.array3
            "In ear" -> R.drawable.inear1
            "In ear 2" -> R.drawable.inear2
            "Audifonos de estudio" -> R.drawable.audifonosestudio
            "Audifonos de estudio 2" -> R.drawable.audifonosestudio2

            "Mezcla 1" -> R.drawable.mezcla1
            "Mezcla 2" -> R.drawable.mezcla2
            "Mezcla 3" -> R.drawable.mezcla3
            "Mezcla 4" -> R.drawable.mezcla4
            "Mezcla 5" -> R.drawable.mezcla5
            "Mezcla 6" -> R.drawable.mezcla6
            "Mezcla 7" -> R.drawable.mezcla7
            "Mezcla 8" -> R.drawable.mezcla8
            "Mezcla 9" -> R.drawable.mezcla9
            "Mezcla 10" -> R.drawable.mezcla10
            "Mezcla 11" -> R.drawable.mezcla11
            "Mezcla 12" -> R.drawable.mezcla12
            "Mezcla 13" -> R.drawable.mezcla13
            "Mezcla 14" -> R.drawable.mezcla14
            "Mezcla 15" -> R.drawable.mezcla15
            "Mezcla 16" -> R.drawable.mezcla16

            "Alargador 1" -> R.drawable.alargador1
            "Alargador 2" -> R.drawable.alargador2

            else -> R.drawable.exitico
        }
    }
}