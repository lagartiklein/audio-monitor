# CMakeLists.txt para FichaTech Audio con Oboe + Opus (PRECOMPILADO)
cmake_minimum_required(VERSION 3.22.1)

project("fichatech_audio")

# Configuraciones básicas
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# C++17 requerido
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Flags de compilación básicos
add_compile_options(
        -Wall
        -Wextra
)

# Flags de optimización por tipo de build
set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} -O3 -ffast-math -DNDEBUG")
set(CMAKE_CXX_FLAGS_DEBUG "${CMAKE_CXX_FLAGS_DEBUG} -g -O0 -DDEBUG")

# ============================================================================
# 🔴 CRÍTICO: Flags de linker para 16KB alignment
# ============================================================================
set(CMAKE_SHARED_LINKER_FLAGS "${CMAKE_SHARED_LINKER_FLAGS} -Wl,-z,max-page-size=16384 -Wl,-z,common-page-size=16384")
set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -Wl,-z,max-page-size=16384 -Wl,-z,common-page-size=16384")

# Soporte para 16KB page size (Android 15+)
if(ANDROID_PLATFORM_LEVEL GREATER_EQUAL 35)
    add_compile_definitions(ANDROID_16KB_PAGES_SUPPORT=1)
    message(STATUS "✅ 16KB page size support enabled (Android 15+)")
endif()

# Configurar búsqueda de Prefab/Oboe
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE BOTH)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY BOTH)

# ============================================================================
# ✅ Buscar Oboe via Prefab
# ============================================================================
find_package(oboe REQUIRED CONFIG)

if(oboe_FOUND)
    message(STATUS "✅ Oboe encontrado! Version: ${oboe_VERSION}")
else()
    message(FATAL_ERROR "❌ Oboe no encontrado. Verifica que 'prefab = true' esté en build.gradle.kts")
endif()

# ============================================================================
# ✅ OPUS PRECOMPILADO - NO COMPILAR, SOLO LINKEAR
# ============================================================================

message(STATUS "🎵 Buscando Opus precompilado...")

# Ruta a jniLibs
set(OPUS_LIB_DIR "${CMAKE_SOURCE_DIR}/../jniLibs/${ANDROID_ABI}")
set(OPUS_INCLUDE_DIR "${CMAKE_SOURCE_DIR}/opus/include")

# Verificar que existe el .so precompilado
if(EXISTS "${OPUS_LIB_DIR}/libopus.so")
    message(STATUS "✅ Opus precompilado encontrado: ${OPUS_LIB_DIR}/libopus.so")

    # Crear imported library para Opus
    add_library(opus_imported SHARED IMPORTED)
    set_target_properties(opus_imported PROPERTIES
            IMPORTED_LOCATION "${OPUS_LIB_DIR}/libopus.so"
    )

    message(STATUS "✅ Opus SHARED library (precompilado) listo para linkear")

elseif(EXISTS "${OPUS_LIB_DIR}/libopus.a")
    message(STATUS "✅ Opus precompilado (static): ${OPUS_LIB_DIR}/libopus.a")

    # Crear imported library para Opus
    add_library(opus_imported STATIC IMPORTED)
    set_target_properties(opus_imported PROPERTIES
            IMPORTED_LOCATION "${OPUS_LIB_DIR}/libopus.a"
    )

    message(STATUS "✅ Opus STATIC library (precompilado) listo para linkear")

else()
    message(FATAL_ERROR "❌ libopus.so NO encontrado en ${OPUS_LIB_DIR}")
    message(FATAL_ERROR "   Debe existir: jniLibs/${ANDROID_ABI}/libopus.so")
    message(FATAL_ERROR "   Verifica que compilaste Opus para todas las architecturas")
endif()

# Incluir headers de Opus (si existen)
if(EXISTS "${OPUS_INCLUDE_DIR}")
    message(STATUS "✅ Headers de Opus encontrados en ${OPUS_INCLUDE_DIR}")
    include_directories(${OPUS_INCLUDE_DIR})
else()
    message(WARNING "⚠️ Headers de Opus NO encontrados, usando solo binarios")
endif()

# ============================================================================
# ✅ Crear biblioteca compartida principal
# ============================================================================
add_library(
        fichatech_audio
        SHARED
        native_audio_engine.cpp
        audio_callback.h
        opus_codec_jni.cpp
)

# Incluir headers
target_include_directories(
        fichatech_audio
        PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}
)

# Flags de compilación específicos para el target
target_compile_options(fichatech_audio PRIVATE
        -std=c++17
        -O3
        -ffast-math
        -DOBOE_ENABLE_LOGGING=1
)

# ============================================================================
# ✅ Linkear con Oboe, Opus precompilado y librerías del sistema
# ============================================================================
target_link_libraries(
        fichatech_audio
        oboe::oboe
        opus_imported               # ✅ Opus PRECOMPILADO (NO recompilar)
        android
        log
        # ✅ Flags de linker para 16KB alignment (CRÍTICO)
        -Wl,-z,max-page-size=16384
        -Wl,-z,common-page-size=16384
)

# ============================================================================
# ✅ Optimizaciones por arquitectura (SOLO flags de compilación)
# ============================================================================
if(${ANDROID_ABI} STREQUAL "arm64-v8a")
    message(STATUS "✅ Optimizando para ARM64")
    target_compile_options(fichatech_audio PRIVATE
            -march=armv8-a
    )
elseif(${ANDROID_ABI} STREQUAL "armeabi-v7a")
    message(STATUS "✅ Optimizando para ARMv7")
    target_compile_options(fichatech_audio PRIVATE
            -march=armv7-a
            -mfpu=neon
            -mfloat-abi=softfp
    )
elseif(${ANDROID_ABI} STREQUAL "x86_64")
    message(STATUS "✅ Optimizando para x86_64")
    target_compile_options(fichatech_audio PRIVATE
            -march=x86-64
    )
endif()

# Mantener símbolos de debug en release
if(CMAKE_BUILD_TYPE STREQUAL "Release")
    target_compile_options(fichatech_audio PRIVATE
            -g
            -gz
    )
endif()

# ============================================================================
# 📋 Información de compilación
# ============================================================================
message(STATUS "")
message(STATUS "========================================")
message(STATUS "FichaTech Audio Build Configuration")
message(STATUS "========================================")
message(STATUS "Build Type: ${CMAKE_BUILD_TYPE}")
message(STATUS "Android ABI: ${ANDROID_ABI}")
message(STATUS "Android Platform: ${ANDROID_PLATFORM}")
message(STATUS "C++ Standard: ${CMAKE_CXX_STANDARD}")
message(STATUS "Oboe Found: ${oboe_FOUND}")
message(STATUS "Opus Precompilado: ${OPUS_LIB_DIR}/libopus.so")
message(STATUS "16KB Alignment: ENABLED")
message(STATUS "=========================================")
message(STATUS "")