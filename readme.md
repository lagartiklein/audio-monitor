# 🎚️ Audio Monitor - Sistema de Monitoreo Multi-canal via WiFi

Sistema de ultra-baja latencia para monitorear canales individuales de interfaces de audio profesionales via WiFi local. **Auto-configuración completa** - ¡Solo ejecuta y usa!

## ✨ Características

- ✅ **Auto-configuración**: Detecta automáticamente tu interfaz de audio
- ✅ Captura multi-canal (ASIO/WASAPI)
- ✅ Transmisión via WebSocket en tiempo real
- ✅ Control independiente de volumen por canal
- ✅ **Latencia optimizada: 20-40ms** (WiFi 5GHz)
- ✅ Interfaz web responsive (funciona en smartphones)
- ✅ Hasta 32 canales simultáneos
- ✅ AudioWorklet API para procesamiento en audio thread
- ✅ Reconexión automática
- ✅ Métricas en tiempo real

## 🚀 Instalación Rápida

### 1. Requisitos

- Python 3.8 o superior
- Interfaz de audio con más de 2 canales
- Drivers ASIO/WASAPI instalados (Windows) o JACK (Linux/Mac)

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. ¡Listo! Ejecutar

```bash
python main.py
```

El sistema:
- ✅ Detectará automáticamente tu interfaz de audio
- ✅ Configurará el sample rate óptimo
- ✅ Calculará el buffer ideal para baja latencia
- ✅ Abrirá automáticamente el navegador
- ✅ Mostrará la URL para dispositivos móviles

## 📱 Uso

### En tu computadora
El navegador se abrirá automáticamente en `http://localhost:5100`

### En tu smartphone/tablet
Usa la URL mostrada en consola (ej: `http://192.168.1.100:5100`)

### Controles
1. **Click en "Canal X"** → Activa/desactiva el canal
2. **Arrastra el slider** → Ajusta volumen (-60dB a +12dB)
3. **Observa las métricas** → Latencia, buffer health, ping de red

## 📊 Métricas en Tiempo Real

### Latencia Total
- 🟢 Verde (≤30ms): Excelente
- 🟠 Naranja (31-50ms): Buena
- 🔴 Rojo (>50ms): Revisar conexión WiFi

### Buffer Health
- 🟢 Verde (50-150%): Óptimo
- 🟠 Naranja (>150%): Lag aumentando
- 🔴 Rojo (<50%): Riesgo de cortes

### Latencia de Red
- 🟢 Verde (≤10ms): Excelente
- 🟠 Naranja (11-25ms): Aceptable
- 🔴 Rojo (>25ms): WiFi lento

## ⚙️ Configuración Avanzada

Si necesitas ajustar parámetros manualmente, edita `config.py`:

```python
# Tamaño de buffer (más bajo = menos latencia, menos estable)
BLOCKSIZE = 128  # 64, 128, 256

# Puerto del servidor
PORT = 5100

# Máximo de clientes simultáneos
MAX_CLIENTS = 8

# Habilitar métricas detalladas
SHOW_METRICS = True
```

## 🔧 Resolución de Problemas

### No detecta mi interfaz de audio

**Síntoma**: "No se encontraron interfaces multi-canal"

**Soluciones**:
1. Verifica que tu interfaz tenga más de 2 canales
2. Instala drivers ASIO oficiales de tu interfaz
3. En Windows: Intenta con ASIO4ALL como alternativa
4. En Linux: Configura JACK Audio

### Audio con cortes o glitches

**Síntoma**: Se escuchan clicks o silencios intermitentes

**Soluciones**:
1. Cambia a WiFi 5GHz (mucho mejor que 2.4GHz)
2. Acerca el dispositivo al router
3. Cierra otras aplicaciones que usen red
4. Si persiste, aumenta `BLOCKSIZE` a 256 en `config.py`

### Latencia muy alta (>60ms)

**Síntoma**: Delay notable entre acción y audio

**Prioridades**:
1. **WiFi 5GHz es crítico** - La diferencia es ~20-30ms
2. Reduce distancia al router
3. Configura QoS en router (priorizar puerto 5100)
4. Verifica que no haya interferencias WiFi

### El navegador pide "Iniciar Audio"

**Síntoma**: Botón azul "🔊 Iniciar Audio"

**Causa**: Política de autoplay de navegadores (normal)

**Solución**: Simplemente haz click en el botón - es un requisito de seguridad

### Audio se detiene al bloquear pantalla (móvil)

**Síntoma**: Smartphone suspende la reproducción

**Soluciones**:
1. Mantén pantalla encendida durante uso
2. Usa Chrome (mejor soporte de Web Audio)
3. En el futuro: implementaremos PWA con wake lock

## 🎯 Casos de Uso Ideales

### ✅ Perfecto para:
- 🎸 Monitoreo de mezcla en ensayos
- 🎤 Sistema IEM (In-Ear Monitor) económico
- 🏠 Configuraciones multi-room
- 🎹 Mezclas personalizadas por músico
- 🎧 Estudio casero con múltiples posiciones

### ⚠️ No recomendado para:
- 🎮 Gaming con feedback visual (necesitas <10ms)
- 🎹 Tocar instrumentos virtuales en tiempo real
- 🎬 Grabación multipista sincronizada profesional
- 🎵 Masterización de audio crítico

## 📊 Especificaciones Técnicas

| Parámetro | Valor |
|-----------|-------|
| **Latencia típica** | 20-40ms (WiFi 5GHz) |
| **Sample rates** | Auto-detectado (22050-192000 Hz) |
| **Formato** | Float32 (sin conversiones) |
| **Protocolo** | WebSocket binario |
| **Max canales** | 32 por interfaz |
| **Max clientes** | 8 simultáneos |
| **Ancho de banda** | ~86 KB/s por canal @ 44100 Hz |
| **CPU (servidor)** | ~5-10% en CPU moderna |
| **CPU (cliente)** | ~2-5% por canal activo |

## 🏗️ Arquitectura

```
┌─────────────────┐
│ Interfaz Audio  │
│   (Captura)     │ ─── Sounddevice (ASIO/WASAPI)
└────────┬────────┘
         │ Float32 @ 128 samples
         ▼
┌─────────────────┐
│ Channel Manager │ ─── Procesamiento por cliente
└────────┬────────┘
         │ Binary packets [uint32 + float32[]]
         ▼
┌─────────────────┐
│ WebSocket       │ ─── Flask-SocketIO
│   (Servidor)    │
└────────┬────────┘
         │ WiFi
         ▼
┌─────────────────┐
│ Cliente Web     │ ─── AudioWorklet API
│  (Navegador)    │     ├─ Jitter buffer
└─────────────────┘     └─ Web Audio API
```

## 🐛 Reporte de Problemas

Si encuentras bugs, por favor incluye:

1. **Sistema operativo**: (Windows 10, macOS 13, Ubuntu 22.04, etc.)
2. **Interfaz de audio**: Modelo y drivers instalados
3. **Configuración de red**: WiFi 5GHz/2.4GHz, distancia al router
4. **Navegador**: Chrome 120, Firefox 119, Safari 17, etc.
5. **Logs del servidor**: Output completo de la consola
6. **Métricas**: Latencia, buffer health, ping mostrados

## 📝 Cambios en esta Versión

### ✅ Corregido
- Alineación de datos Float32 (uint32 en lugar de byte)
- Timestamp ping/pong en milisegundos
- Race conditions en inicialización de AudioWorklet
- Buffer underruns en AudioWorklet
- Manejo de reconexión WebSocket
- Auto-configuración de sample rate y jitter buffer

### ✨ Nuevo
- Auto-detección y configuración completa
- Apertura automática del navegador
- Métricas mejoradas con colores dinámicos
- Mejor manejo de errores y logging
- Reconexión automática de clientes
- Interfaz mejorada y responsive

## 📄 Licencia

Este proyecto es de código abierto. Úsalo libremente para proyectos personales o comerciales.

## 🙏 Créditos

- [sounddevice](https://python-sounddevice.readthedocs.io/) - Captura de audio
- [Flask-SocketIO](https://flask-socketio.readthedocs.io/) - WebSocket server
- [Web Audio API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API) - Reproducción en navegador

---

**¿Preguntas? ¿Sugerencias?** Abre un issue en el repositorio.