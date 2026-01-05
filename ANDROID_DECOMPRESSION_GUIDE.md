# Android Decompression Implementation Guide (Opcional)

## Estado Actual

El servidor envía audio:
- **Con flag=1**: Datos comprimidos (Zlib)
- **Con flag=0**: Datos sin comprimir (fallback)

Android actualmente **ignora el flag y procesa como sin comprimir** (fallback automático).

## Implementación Completa (Opcional)

### Opción 1: Zlib en Android (Recomendada para compatibilidad)

Zlib está disponible en Android mediante `java.util.zip`:

```kotlin
// AudioDecompressor.kt
package com.fichatech.audioclient

import java.util.zip.Inflater
import kotlin.math.min

class AudioDecompressor {
    private val inflater = Inflater()
    
    /**
     * Descomprimir audio Zlib
     * 
     * @param compressedData: ByteArray con header (4 bytes tamaño) + datos Zlib
     * @return FloatArray descomprimido
     */
    fun decompressZlib(compressedData: ByteArray): FloatArray {
        if (compressedData.size < 4) {
            return FloatArray(0)
        }
        
        // Leer header (tamaño original en big-endian)
        val originalSize = ((compressedData[0].toInt() and 0xFF) shl 24) or
                          ((compressedData[1].toInt() and 0xFF) shl 16) or
                          ((compressedData[2].toInt() and 0xFF) shl 8) or
                          (compressedData[3].toInt() and 0xFF)
        
        // Descomprimir
        inflater.reset()
        inflater.setInput(compressedData, 4, compressedData.size - 4)
        
        val decompressed = ByteArray(originalSize)
        val uncompressedSize = inflater.inflate(decompressed)
        
        if (uncompressedSize != originalSize) {
            throw RuntimeException("Decompression size mismatch: $uncompressedSize vs $originalSize")
        }
        
        // Convertir PCM int16 a float32
        val floatArray = FloatArray(originalSize / 2)
        var floatIndex = 0
        
        for (i in 0 until originalSize step 2) {
            val byte1 = decompressed[i].toInt() and 0xFF
            val byte2 = decompressed[i + 1].toInt() and 0xFF
            val pcmValue = (byte2 shl 8) or byte1  // Little-endian
            val floatValue = pcmValue.toShort().toFloat() / 32767.0f
            floatArray[floatIndex++] = floatValue
        }
        
        return floatArray
    }
}
```

### Opción 2: Usar en NativeAudioClient

```kotlin
// NativeAudioClient.kt
class NativeAudioClient {
    private val decompressor = AudioDecompressor()
    
    fun processAudioPacket(packet: ByteArray) {
        // Leer header del paquete (igual que servidor)
        val isCompressed = (packet[COMPRESSION_FLAG_OFFSET].toInt() and 0xFF) == 1
        
        val audioData = if (isCompressed) {
            try {
                // Extraer datos comprimidos del paquete
                val compressedAudio = packet.sliceArray(DATA_OFFSET until packet.size)
                decompressor.decompressZlib(compressedAudio)
            } catch (e: Exception) {
                // Fallback: interpretar como uncompressed
                Log.w("AudioClient", "Decompression failed: ${e.message}")
                packet.sliceArray(DATA_OFFSET until packet.size)
                    .toByteArray()
                    .asFloatArray()  // Asume float32
            }
        } else {
            // Sin comprimir: procesar normalmente
            packet.sliceArray(DATA_OFFSET until packet.size)
                .toByteArray()
                .asFloatArray()
        }
        
        // Pasar a renderer
        audioRenderer.render(audioData)
    }
}
```

### Opción 3: Opus en Android (Mejor compresión: 4-8x)

Requiere biblioteca tercera (más complejo):

```kotlin
// Agregar dependency:
// implementation 'org.concentus:concentus:1.0'

import org.concentus.OpusDecoder

class OpusAudioDecompressor {
    private val decoder = OpusDecoder(48000, 1)  // 48kHz, mono
    
    fun decompressOpus(opusData: ByteArray): FloatArray {
        // El API de Opus esperado varía por biblioteca
        // Este es un ejemplo simplificado
        return try {
            val pcmData = decoder.decode(opusData, opusData.size)
            // Convertir a float
            val floats = FloatArray(pcmData.size / 2)
            for (i in 0 until pcmData.size step 2) {
                val sample = ((pcmData[i+1].toInt() shl 8) or 
                            (pcmData[i].toInt() and 0xFF)).toShort()
                floats[i / 2] = sample / 32768.0f
            }
            floats
        } catch (e: Exception) {
            FloatArray(0)  // Error
        }
    }
}
```

## Integración en NativeAudioStreamActivity

```kotlin
// NativeAudioStreamActivity.kt
class NativeAudioStreamActivity : AppCompatActivity() {
    private val audioDecompressor = AudioDecompressor()
    
    // ... OnAudioAvailable callback
    
    fun onAudioDataReceived(audioPacket: ByteArray) {
        val compressionFlag = audioPacket[COMPRESSION_FLAG_INDEX].toInt() and 0xFF
        
        val audioSamples = if (compressionFlag == 1) {
            // Compressed - decompress first
            try {
                val compressed = audioPacket.sliceArray(AUDIO_DATA_START until audioPacket.size)
                audioDecompressor.decompressZlib(compressed)
            } catch (e: Exception) {
                Log.e("AudioStream", "Failed to decompress: ${e.message}")
                FloatArray(0)  // Empty on error
            }
        } else {
            // Uncompressed - use directly
            audioPacket.sliceArray(AUDIO_DATA_START until audioPacket.size)
                .asFloatArray()
        }
        
        // Enviar a renderer
        oboeAudioRenderer?.render(audioSamples)
    }
}
```

## Testing en Android

```kotlin
// Test unitario
@RunWith(AndroidJUnit4::class)
class AudioDecompressorTest {
    
    private lateinit var decompressor: AudioDecompressor
    
    @Before
    fun setup() {
        decompressor = AudioDecompressor()
    }
    
    @Test
    fun testZlibDecompression() {
        // Generar audio de prueba
        val original = FloatArray(512) { it * 0.1f }
        
        // Comprimir en servidor (simular)
        val compressed = compressZlib(original)
        
        // Descomprimir en Android
        val decompressed = decompressor.decompressZlib(compressed)
        
        // Verificar
        Assert.assertEquals(original.size, decompressed.size)
        
        val error = original.zip(decompressed) { a, b -> 
            Math.abs(a - b) 
        }.average()
        
        Assert.assertTrue(error < 0.00002)  // Error imperceptible
    }
}
```

## Referencias

- **Zlib**: `java.util.zip.Inflater` (built-in)
- **Opus**: Requiere binding JNI o biblioteca como `concentus`
- **Float conversion**: PCM int16 → float32 (divide por 32767 o 32768)

## Recomendación

**Zlib es suficiente** para este caso:
- 50% compresión vs 75-88% de Opus
- Built-in en Android (sin dependencies)
- Compresión/descompresión rápida (<1ms)
- Error imperceptible

## Fallback Automático

Mientras no se implemente decompresión:
- Servidor envía audio sin comprimir (flag=0)
- Android lo procesa normalmente
- Sistema funciona correctamente

La implementación de decompresión es **mejora opcional**, no requisito.

---
**Nota**: Este código es para implementación futura.
El sistema actualmente funciona con fallback (sin comprimir).
