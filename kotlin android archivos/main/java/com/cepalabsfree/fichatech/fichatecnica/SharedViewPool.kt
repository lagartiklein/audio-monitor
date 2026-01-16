package com.cepalabsfree.fichatech.fichatecnica

import androidx.recyclerview.widget.RecyclerView

object SharedViewPool {
    private var sharedPool: RecyclerView.RecycledViewPool? = null

    fun getPool(): RecyclerView.RecycledViewPool {
        return sharedPool ?: RecyclerView.RecycledViewPool().apply {
            setMaxRecycledViews(0, 50) // ✅ AUMENTADO a 50
            sharedPool = this
        }
    }

    fun clearPool() {
        sharedPool = null
    }
}