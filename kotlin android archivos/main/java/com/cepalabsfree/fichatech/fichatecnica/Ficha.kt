package com.cepalabsfree.fichatech.fichatecnica

data class Ficha(
    var id: Int,
    val nombre: String,
    val descripcion: String,
    val canales: List<Canal>,
    val colorFondo: Int? = null,
    val orden: Int = 0,
    val ultimaModificacion: Long = System.currentTimeMillis() / 1000
)