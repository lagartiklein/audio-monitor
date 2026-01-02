# CMakeLists.txt para FichaTech Audio con Oboe
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

# CRÍTICO: Flags de linker para 16KB alignment
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

# Buscar Oboe via Prefab
find_package(oboe REQUIRED CONFIG)

if(oboe_FOUND)
    message(STATUS "✅ Oboe encontrado! Version: ${oboe_VERSION}")
else()
    message(FATAL_ERROR "❌ Oboe no encontrado. Verifica que 'prefab = true' esté en build.gradle.kts")
endif()

# Crear biblioteca compartida
add_library(
        fichatech_audio
        SHARED
        native_audio_engine.cpp
        audio_callback.mm
)

# Incluir headers
target_include_directories(
        fichatech_audio
        PRIVATE
        "../../../../../../../../../audio-monitor/kotlin android"
)

# Flags de compilación específicos para el target
target_compile_options(fichatech_audio PRIVATE
        -std=c++17
        -O3
        -ffast-math
        -DOBOE_ENABLE_LOGGING=1
)

# Linkear con Oboe y bibliotecas del sistema CON FLAGS DE 16KB
target_link_libraries(
        fichatech_audio
        oboe::oboe
        android
        log
        # ✅ Flags de linker para 16KB alignment
        -Wl,-z,max-page-size=16384
        -Wl,-z,common-page-size=16384
)

# Optimizaciones por arquitectura (SOLO flags de compilación)
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

# Información de compilación
message(STATUS "========================================")
message(STATUS "FichaTech Audio Build Configuration")
message(STATUS "========================================")
message(STATUS "Build Type: ${CMAKE_BUILD_TYPE}")
message(STATUS "Android ABI: ${ANDROID_ABI}")
message(STATUS "Android Platform: ${ANDROID_PLATFORM}")
message(STATUS "C++ Standard: ${CMAKE_CXX_STANDARD}")
message(STATUS "Oboe Found: ${oboe_FOUND}")
message(STATUS "16KB Alignment: ENABLED")
message(STATUS "========================================")