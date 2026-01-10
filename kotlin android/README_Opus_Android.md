# 🎵 FichaTech Audio - Integración Opus para Android

## 📋 Requisitos Previos

- **Librería Opus compilada** para Android ARM64 (`libopus.so`)
- **Headers de Opus** (`opus/opus.h`, etc.)
- **Proyecto Android** con NDK configurado

## 🛠️ Pasos de Integración

### 1. Estructura de Archivos

Crea esta estructura en tu proyecto Android:

```
app/src/main/
├── jniLibs/
│   └── arm64-v8a/
│       └── libopus.so          # ← Coloca aquí tu librería compilada
├── cpp/
│   ├── AudioDecompressorJNI.cpp  # ← Copia este archivo
│   └── ... (otros archivos C++)
└── java/com/tu/paquete/
    └── AudioDecompressor.kt    # ← Modifica este archivo
```

### 2. Copiar Headers de Opus

```bash
# Crear directorio para headers
mkdir -p app/src/main/cpp/opus/

# Copiar headers (desde tu compilación de Opus)
cp -r /ruta/a/opus/include/opus/* app/src/main/cpp/opus/
```

### 3. Actualizar build.gradle.kts

```kotlin
android {
    defaultConfig {
        // ... configuración existente ...
        externalNativeBuild {
            cmake {
                arguments("-DANDROID_STL=c++_shared")
            }
        }
    }

    externalNativeBuild {
        cmake {
            path("src/main/cpp/CMakeLists.txt")
        }
    }
}
```

### 4. CMakeLists.txt (Proyecto Android)

```cmake
cmake_minimum_required(VERSION 3.22.1)

# Configurar Opus
set(OPUS_DIR "${CMAKE_CURRENT_SOURCE_DIR}")
set(OPUS_INCLUDE_DIR "${OPUS_DIR}/opus")
set(OPUS_LIBRARY "${CMAKE_CURRENT_SOURCE_DIR}/../jniLibs/${ANDROID_ABI}/libopus.so")

add_library(opus SHARED IMPORTED)
set_target_properties(opus PROPERTIES
    IMPORTED_LOCATION "${OPUS_LIBRARY}"
    INTERFACE_INCLUDE_DIRECTORIES "${OPUS_INCLUDE_DIR}"
)

# Tu biblioteca nativa
add_library(native-lib SHARED
    AudioDecompressorJNI.cpp
    # ... otros archivos
)

target_link_libraries(native-lib
    opus
    # ... otras dependencias
)
```

### 5. Modificar Recepción de Audio

En tu código que recibe datos del WebSocket:

```kotlin
// Cuando recibes master_audio_data
val audioData = AudioDecompressor.processAudioPacket(
    audioBytes,  // datos del WebSocket
    data.compression?.method ?: "none"  // método de compresión
)

// Usar audioData (FloatArray) para reproducción
```

## 🔧 Configuración del Servidor

Asegúrate de que el servidor tenga:

```python
# config.py
AUDIO_COMPRESSION_ENABLED = True
AUDIO_COMPRESSION_BITRATE = 32000
```

## 🧪 Verificación

Para verificar que funciona:

1. **Inicia el servidor** con compresión Opus
2. **Conecta cliente Android**
3. **Verifica logs** del servidor y Android
4. **Confirma calidad de audio**

## 📊 Rendimiento Esperado

- **Compresión**: ~95% reducción de ancho de banda
- **Calidad**: Profesional, baja latencia
- **CPU**: Mínimo impacto en dispositivos modernos

## 🐛 Troubleshooting

### "UnsatisfiedLinkError: libopus.so"
- Verifica que `libopus.so` esté en `jniLibs/arm64-v8a/`
- Confirma que el ABI coincida con tu dispositivo

### "Opus decode error"
- Verifica que los parámetros (sampleRate, channels) coincidan
- Revisa que los datos comprimidos sean válidos

### Audio distorsionado
- Verifica endianness de los datos
- Confirma formato PCM esperado (float32)

## 📞 Soporte

Si tienes problemas, verifica:
1. Logs de Android Studio
2. Logs del servidor Python
3. Que Opus esté compilado correctamente para ARM64</content>
<parameter name="filePath">c:\audio-monitor\kotlin android\README_Opus_Android.md