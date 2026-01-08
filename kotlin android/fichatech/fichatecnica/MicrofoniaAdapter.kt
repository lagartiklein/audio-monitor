package com.cepalabsfree.fichatech.fichatecnica

import android.content.Context
import android.widget.ArrayAdapter
import androidx.annotation.Keep


@Keep
class MicrofoniaAdapter(context: Context, resource: Int, objects: List<String>) : ArrayAdapter<String>(context, resource, objects) {
    init {
        setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
    }
}
