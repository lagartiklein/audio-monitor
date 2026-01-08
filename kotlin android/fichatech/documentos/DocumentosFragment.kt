package com.cepalabsfree.fichatech.documentos

import android.app.Activity
import android.content.Intent
import android.graphics.*
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.DocumentsContract
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.Toast
import androidx.annotation.RequiresApi
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import androidx.recyclerview.widget.DividerItemDecoration
import androidx.recyclerview.widget.LinearLayoutManager
import com.cepalabsfree.fichatech.R
import com.cepalabsfree.fichatech.databinding.FragmentDocumentosBinding
import com.cepalabsfree.fichatech.fichatecnica.FichaDatabaseHelper
import com.cepalabsfree.fichatech.planta.PlantaEscenarioDatabaseHelper
import com.cepalabsfree.fichatech.planta.PlantaRenderer
import com.google.android.gms.ads.AdRequest
import com.itextpdf.text.BaseColor
import com.itextpdf.text.Chunk
import com.itextpdf.text.Element
import com.itextpdf.text.Font
import com.itextpdf.text.Paragraph
import com.itextpdf.text.Phrase
import com.itextpdf.text.pdf.PdfPCell
import com.itextpdf.text.pdf.PdfPTable
import com.itextpdf.text.pdf.draw.LineSeparator
import com.itextpdf.text.pdf.PdfPageEventHelper
import com.itextpdf.text.pdf.PdfContentByte
import com.itextpdf.text.pdf.PdfGState
import com.itextpdf.text.FontFactory
import kotlinx.coroutines.runBlocking
import java.io.ByteArrayOutputStream
import java.text.SimpleDateFormat
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import java.util.Date
import java.util.Locale
import kotlin.math.max
import kotlin.math.min

class DocumentosFragment : Fragment() {
    private var _binding: FragmentDocumentosBinding? = null
    private val binding get() = _binding!!
    private lateinit var adapter: DocumentosAdapter
    private lateinit var fichaDbHelper: FichaDatabaseHelper
    private lateinit var plantaDbHelper: PlantaEscenarioDatabaseHelper

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentDocumentosBinding.inflate(inflater, container, false)
        return binding.root
    }

    @RequiresApi(Build.VERSION_CODES.O)
    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        fichaDbHelper = FichaDatabaseHelper(requireContext())
        plantaDbHelper = PlantaEscenarioDatabaseHelper(requireContext())
        setupRecyclerView()
        setupExportButton()
        cargarDocumentos()
    }

    private fun setupRecyclerView() {
        adapter = DocumentosAdapter(mutableListOf()) { documento, isSelected ->
            documento.isSelected = isSelected
        }
        binding.recyclerViewDocumentos.apply {
            layoutManager = LinearLayoutManager(context)
            adapter = this@DocumentosFragment.adapter
            addItemDecoration(DividerItemDecoration(context, DividerItemDecoration.VERTICAL))
        }
    }

    private fun setupExportButton() {
        binding.btnExportar.setOnClickListener {
            exportarDocumentosSeleccionados()
        }
    }

    @RequiresApi(Build.VERSION_CODES.O)
    private fun cargarDocumentos() {
        val documentos = mutableListOf<Documento>()

        // Cargar fichas técnicas
        fichaDbHelper.getAllFichas().forEach { ficha ->
            documentos.add(
                Documento(
                    id = ficha.id.toLong(),
                    nombre = ficha.nombre,
                    descripcion = "Lista de canales",
                    fechaCreacion = LocalDateTime.now().format(DateTimeFormatter.ISO_DATE),
                    tipo = TipoDocumento.FICHA_TECNICA
                )
            )
        }

        // Cargar plantas de escenario
        plantaDbHelper.getAllScenes().forEach { scene ->
            documentos.add(
                Documento(
                    id = scene.id,
                    nombre = scene.name,
                    descripcion = "Planta de Escenario",
                    fechaCreacion = LocalDateTime.now().format(DateTimeFormatter.ISO_DATE),
                    tipo = TipoDocumento.PLANTA_ESCENARIO
                )
            )
        }
        adapter.updateDocumentos(documentos)
    }

    private fun exportarDocumentosSeleccionados() {
        val documentosSeleccionados = adapter.documentos.filter { it.isSelected }
        if (documentosSeleccionados.isEmpty()) {
            Toast.makeText(context, "Selecciona al menos un documento", Toast.LENGTH_SHORT).show()
            return
        }

        // Crear nombre de archivo con fecha
        val dateFormat = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.getDefault())
        val fecha = dateFormat.format(Date())
        val fileName = "Documentos_$fecha.pdf"

        val intent = Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "application/pdf"
            putExtra(Intent.EXTRA_TITLE, fileName)
            // Opcional: especificar directorio inicial
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                putExtra(
                    DocumentsContract.EXTRA_INITIAL_URI, DocumentsContract.buildDocumentUri(
                        "com.android.externalstorage.documents",
                        "primary:Documents"
                    )
                )
            }
        }

        startActivityForResult(intent, REQUEST_CODE_EXPORT_PDF)
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQUEST_CODE_EXPORT_PDF && resultCode == Activity.RESULT_OK) {
            data?.data?.let { uri ->
                try {
                    val documentosSeleccionados = adapter.documentos.filter { it.isSelected }
                    if (documentosSeleccionados.isEmpty()) {
                        Toast.makeText(
                            context,
                            "No hay documentos seleccionados",
                            Toast.LENGTH_SHORT
                        ).show()
                        return
                    }

                    escribirContenidoPDF(uri, documentosSeleccionados)

                } catch (e: Exception) {
                    Toast.makeText(context, "Error al exportar: ${e.message}", Toast.LENGTH_SHORT)
                        .show()
                    e.printStackTrace()
                }
            }
        }
    }

    private fun escribirContenidoPDF(uri: Uri, documentos: List<Documento>) {
        val pdfDocument =
            com.itextpdf.text.Document(com.itextpdf.text.PageSize.A4, 20f, 20f, 20f, 20f)

        try {
            val outputStream = requireContext().contentResolver.openOutputStream(uri)
            val pdfWriter = com.itextpdf.text.pdf.PdfWriter.getInstance(pdfDocument, outputStream)

            // --- Marca de agua cruzada ---
            pdfWriter.pageEvent = object : PdfPageEventHelper() {
                override fun onEndPage(
                    writer: com.itextpdf.text.pdf.PdfWriter?,
                    document: com.itextpdf.text.Document?
                ) {
                    val cb: PdfContentByte = writer!!.directContentUnder
                    val gState = PdfGState()
                    gState.setFillOpacity(0.08f)
                    cb.saveState()
                    cb.setGState(gState)
                    val watermarkText = "fichatech"
                    val font = FontFactory.getFont(
                        FontFactory.HELVETICA_BOLD,
                        60f,
                        com.itextpdf.text.Font.NORMAL,
                        BaseColor.LIGHT_GRAY
                    )
                    val width = document!!.pageSize.width
                    val height = document.pageSize.height
                    val step = 300
                    for (x in -100..width.toInt() step step) {
                        for (y in 0..height.toInt() step step) {
                            cb.saveState()
                            cb.beginText()
                            cb.setFontAndSize(font.baseFont, 60f)
                            cb.setColorFill(BaseColor.LIGHT_GRAY)
                            cb.showTextAligned(
                                com.itextpdf.text.Element.ALIGN_CENTER,
                                watermarkText,
                                x.toFloat(),
                                y.toFloat(),
                                45f
                            )
                            cb.endText()
                            cb.restoreState()
                        }
                    }
                    cb.restoreState()
                }
            }
            // --- Fin marca de agua ---

            // Configuración del documento
            pdfDocument.open()
            val fontBold = Font(Font.FontFamily.HELVETICA, 12f, Font.BOLD)
            val fontNormal = Font(Font.FontFamily.HELVETICA, 10f, Font.NORMAL)

            documentos.forEach { doc ->
                when (doc.tipo) {
                    TipoDocumento.FICHA_TECNICA -> {
                        // Encabezado
                        pdfDocument.add(Paragraph("Ficha Técnica", fontBold))
                        pdfDocument.add(Paragraph("Proyecto: ${doc.nombre}", fontNormal))
                        pdfDocument.add(Paragraph("Descripción: ${doc.descripcion}", fontNormal))
                        pdfDocument.add(Paragraph(" "))

                        // Contenido de la ficha
                        agregarTablaFichaTecnica(pdfDocument, doc)
                    }

                    TipoDocumento.PLANTA_ESCENARIO -> {
                        pdfDocument.add(Paragraph("Planta de Escenario: ${doc.nombre}", fontBold))
                        pdfDocument.add(Paragraph("Descripción: Planta de escenario", fontNormal))
                        pdfDocument.add(Paragraph(" "))

                        // Renderizar la planta centrada usando el renderizador mejorado
                        renderPlantaInPdf(pdfDocument, doc)
                    }
                }

                // Agregar nueva página para el siguiente documento (excepto para el último)
                if (doc != documentos.last()) {
                    pdfDocument.newPage()
                }
            }

            Toast.makeText(context, "PDF exportado exitosamente", Toast.LENGTH_SHORT).show()
        } catch (e: Exception) {
            Toast.makeText(
                context,
                "Error al generar PDF: ${e.localizedMessage}",
                Toast.LENGTH_LONG
            ).show()
            Log.e("DocumentosFragment", "Error al generar PDF", e)
        } finally {
            pdfDocument.close()
        }
    }

    private fun renderPlantaInPdf(pdfDocument: com.itextpdf.text.Document, doc: Documento) {
        try {
            // Usar runBlocking para operación síncrona en este contexto específico
            val plantaBitmap = runBlocking {
                PlantaRenderer.renderPlantaAsBitmap(requireContext(), doc.nombre, plantaDbHelper)
            }

            if (plantaBitmap == null) {
                pdfDocument.add(
                    Paragraph(
                        "Error: No se pudo generar la planta '${doc.nombre}'",
                        Font(Font.FontFamily.HELVETICA, 10f, Font.ITALIC, BaseColor.RED)
                    )
                )
                return
            }

            // Convertir a imagen PDF
            val stream = ByteArrayOutputStream()
            plantaBitmap.compress(Bitmap.CompressFormat.PNG, 100, stream)
            val image = com.itextpdf.text.Image.getInstance(stream.toByteArray())

            // Calcular espacio disponible
            val pageWidth = pdfDocument.pageSize.width - pdfDocument.leftMargin() - pdfDocument.rightMargin()
            val pageHeight = pdfDocument.pageSize.height - pdfDocument.topMargin() - pdfDocument.bottomMargin() - 80f

            // Calcular escalado manteniendo relación de aspecto
            val widthRatio = pageWidth / image.width
            val heightRatio = pageHeight / image.height
            val scaleRatio = min(widthRatio, heightRatio) * 0.95f

            // Aplicar escalado
            image.scaleAbsolute(image.width * scaleRatio, image.height * scaleRatio)
            image.alignment = com.itextpdf.text.Image.ALIGN_CENTER

            // Agregar imagen centrada
            pdfDocument.add(image)

            // Liberar recursos
            plantaBitmap.recycle()
            stream.close()

        } catch (e: Exception) {
            pdfDocument.add(
                Paragraph(
                    "Error al renderizar la planta '${doc.nombre}': ${e.message}",
                    Font(Font.FontFamily.HELVETICA, 10f, Font.ITALIC, BaseColor.RED)
                )
            )
            Log.e("DocumentosFragment", "Error al renderizar planta ${doc.nombre}", e)
        }
    }

    private fun agregarTablaFichaTecnica(
        documento: com.itextpdf.text.Document,
        documentoModelo: Documento
    ) {
        val ficha = fichaDbHelper.getFichaById(documentoModelo.id.toInt()) ?: return

        // Crear tabla con 4 columnas
        val tabla = PdfPTable(4)
        tabla.setWidthPercentage(100f)
        tabla.setSpacingBefore(10f)

        // Establecer anchos relativos de las columnas
        val anchosColumnas = floatArrayOf(1f, 2f, 2f, 2f)
        tabla.setWidths(anchosColumnas)

        // Agregar encabezados
        val headers = arrayOf("Canal", "Nombre", "Microfonía", "FX")
        headers.forEach { header ->
            val cell = PdfPCell(Phrase(header))
            cell.horizontalAlignment = Element.ALIGN_CENTER
            cell.backgroundColor = BaseColor.LIGHT_GRAY
            tabla.addCell(cell)
        }

        // Agregar datos de los canales
        ficha.canales.forEachIndexed { index, canal ->
            // Número de canal
            tabla.addCell(PdfPCell(Phrase("${index + 1}")).apply {
                horizontalAlignment = Element.ALIGN_CENTER
            })

            // Nombre del canal
            tabla.addCell(PdfPCell(Phrase(canal.nombre)).apply {
                horizontalAlignment = Element.ALIGN_LEFT
            })

            // Microfonía
            tabla.addCell(PdfPCell(Phrase(if (canal.microfonia == "Por definir") "" else canal.microfonia)).apply {
                horizontalAlignment = Element.ALIGN_LEFT
            })

            // FX
            tabla.addCell(PdfPCell(Phrase(if (canal.fx == "Sin efecto") "" else canal.fx)).apply {
                horizontalAlignment = Element.ALIGN_LEFT
            })
        }

        // Agregar la tabla al documento
        documento.add(tabla)
        documento.add(Chunk.NEWLINE)
    }

    override fun onDestroyView() {
        super.onDestroyView()

        // Limpiar cache del renderizador
        PlantaRenderer.clearCache()
        _binding = null
    }

    companion object {
        private const val REQUEST_CODE_EXPORT_PDF = 1001
    }
}