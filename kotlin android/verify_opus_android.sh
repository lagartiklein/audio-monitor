#!/bin/bash
# verify_opus_android.sh - Verificar configuración de Opus en Android

echo "🔍 Verificando configuración de Opus para Android..."
echo "=================================================="

# Verificar estructura de directorios
echo ""
echo "📁 Verificando estructura de archivos:"

DIRS=(
    "opus-android/lib/arm64-v8a"
    "opus-android/include/opus"
)

for dir in "${DIRS[@]}"; do
    if [ -d "$dir" ]; then
        echo "✅ $dir - OK"
    else
        echo "❌ $dir - FALTA"
    fi
done

# Verificar librería
echo ""
echo "📚 Verificando librería Opus:"
if [ -f "opus-android/lib/arm64-v8a/libopus.so" ]; then
    echo "✅ libopus.so encontrado"
    file opus-android/lib/arm64-v8a/libopus.so
else
    echo "❌ libopus.so no encontrado"
fi

# Verificar headers
echo ""
echo "📄 Verificando headers:"
HEADERS=(
    "opus-android/include/opus/opus.h"
    "opus-android/include/opus/opus_types.h"
    "opus-android/include/opus/opus_defines.h"
)

for header in "${HEADERS[@]}"; do
    if [ -f "$header" ]; then
        echo "✅ $header - OK"
    else
        echo "❌ $header - FALTA"
    fi
done

# Verificar archivos modificados
echo ""
echo "🔧 Verificando archivos modificados:"
FILES=(
    "CMakeLists.txt"
    "AudioDescompressor.kt"
    "AudioDecompressorJNI.cpp"
)

for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "✅ $file - OK"
    else
        echo "❌ $file - FALTA"
    fi
done

echo ""
echo "📋 Próximos pasos:"
echo "1. Copia libopus.so a tu proyecto Android: app/src/main/jniLibs/arm64-v8a/"
echo "2. Copia headers a: app/src/main/cpp/opus/"
echo "3. Copia AudioDecompressorJNI.cpp a: app/src/main/cpp/"
echo "4. Actualiza CMakeLists.txt en tu proyecto Android"
echo "5. Modifica AudioDecompressor.kt según el ejemplo"
echo "6. Reconstruye tu app Android"
echo ""
echo "🎯 ¡Listo para integrar Opus!"</content>
<parameter name="filePath">c:\audio-monitor\kotlin android\verify_opus_android.sh