package com.cepalabsfree.fichatech.fichatecnica
// Importar clases necesarias para implementar Parcelable

import android.os.Parcel
import android.os.Parcelable
import androidx.annotation.Keep

@Keep
// Data class que representa un Canal en la ficha técnica.
// Se implementa Parcelable para poder enviar instancias entre Activities/Fragments
// a través de Intents/Bundles si fuese necesario.
data class Canal(
    var id: Int = -1,                    // Identificador en la BD; -1 indica "no persistido aún"
    var numeroCanal: Int = 1,            // Número de canal (1-based). Mutable porque puede cambiar al reordenar/eliminar.
    var nombre: String = "",           // Nombre del canal; nunca debe ser null (se inicializa con "")
    var microfonia: String = "",       // Texto con información de microfonía; nunca null
    var fx: String = "",               // Efectos asociados al canal; nunca null
    var color: Int = 0,                  // Color asociado al canal (entero ARGB o index según implementación)
    var faderLevel: Int = 0              // Nivel del fader (ej. 0..100). Valor por defecto 0
) : Parcelable {

    // Constructor secundario que crea un Canal a partir de un Parcel.
    // El orden de lectura aquí debe coincidir exactamente con el orden de escritura
    // en writeToParcel para que los valores se deserialicen correctamente.
    constructor(parcel: Parcel) : this(
        parcel.readInt(), // id
        parcel.readInt(), // numeroCanal
        parcel.readString() ?: "", // nombre (si es null, usar cadena vacía)
        parcel.readString() ?: "", // microfonia (fallback a "")
        parcel.readString() ?: "", // fx (fallback a "")
        parcel.readInt(), // color
        parcel.readInt()  // faderLevel
    )

    // writeToParcel serializa los campos del objeto en el Parcel.
    // Debe escribir los mismos campos y en el mismo orden que el constructor que lee el Parcel.
    override fun writeToParcel(parcel: Parcel, flags: Int) {
        parcel.writeInt(id) // id del canal
        parcel.writeInt(numeroCanal) // número de canal
        parcel.writeString(nombre) // nombre del canal
        parcel.writeString(microfonia) // microfonía
        parcel.writeString(fx) // efectos
        parcel.writeInt(color) // color (entero)
        parcel.writeInt(faderLevel) // nivel del fader
    }

    // describeContents suele devolver 0. Se utiliza para indicar si el Parcelable contiene
    // descriptores de archivo (FileDescriptor), lo cual no aplica aquí.
    override fun describeContents(): Int {
        return 0
    }

    // Companion object que implementa Parcelable.Creator para crear instancias de Canal
    // desde un Parcel y para crear arrays de Canal. Este objeto es requerido por el framework.
    companion object CREATOR : Parcelable.Creator<Canal> {

        // Crea una nueva instancia de Canal a partir del Parcel recibido.
        override fun createFromParcel(parcel: Parcel): Canal {
            return Canal(parcel)
        }

        // Crea un array de Canal de tamaño `size`. Se usa en ciertos APIs del sistema.
        override fun newArray(size: Int): Array<Canal?> {
            return arrayOfNulls(size)
        }

    }

}
