package com.cepalabsfree.fichatech.documentos

data class Documento(
    val id: Long,
    val nombre: String,
    val descripcion: String,
    val fechaCreacion: String,
    val tipo: TipoDocumento,
    var isSelected: Boolean = false
)
//prueba
enum class TipoDocumento {
    FICHA_TECNICA,
    PLANTA_ESCENARIO,
}