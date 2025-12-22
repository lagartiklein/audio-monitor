# 🎚️ Audio Monitor - Sistema de Monitoreo Multi-canal via WiFi

Sistema de baja latencia para monitorear canales individuales de interfaces de audio profesionales via WiFi local.

## 📋 Características

- ✅ Captura multi-canal de interfaces de audio (ASIO/WASAPI)
- ✅ Transmisión via WebSocket en red local
- ✅ Control independiente de volumen por canal
- ✅ Latencia optimizada: 40-60ms (WiFi 5GHz)
- ✅ Interfaz web responsive (funciona en smartphones)
- ✅ Hasta 32 canales simultáneos
- ✅ Configuración automática de sample rate

## 🚀 Instalación

### 1. Clonar/Descargar el proyecto

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Conectar interfaz de audio

Asegúrate de que tu interfaz esté conectada y tenga drivers instalados.

## 📁 Estructura del Proyecto

```
audio-monitor/
├── config.py              # Configuración (sample rate, buffer, etc)
├── main.py                # Entry point
├── requirements.txt
├── backend/
│   ├── audio_capture.py   # Captura con sounddevice
│   ├── channel_manager.py # Gestión de canales/ganancia
│   └── websocket_server.py# Flask + SocketIO
└── frontend/
    ├── index.html         # Interfaz web
    ├── app.js             # Lógica del cliente
    └── styles.css         # Estilos
```

## ▶️ Uso

### 1. Iniciar el servidor

```bash
python main.py
```

El servidor:
- Detectará automáticamente interfaces de audio
- Abrirá el navegador en `http://localhost:5000`
- Mostrará la URL de red local (ej: `http://192.168.1.100:5000`)

### 2. Conectar dispositivos

En tu smartphone o tablet, navega a la URL mostrada (ej: `http://192.168.1.100:5000`)

### 3. Monitorear audio

- Click en botones "Canal X" para activar/desactivar
- Usa sliders para ajustar volumen de cada canal
- Los canales activos se transmiten en tiempo real

## ⚙️ Configuración

Edita `config.py` para ajustar parámetros:

```python
SAMPLE_RATE = 44100  # 22050 o 44100
BLOCKSIZE = 256      # 128 (baja latencia) o 256 (estable)
JITTER_BUFFER_MS = 20  # 20ms para WiFi 5GHz, 40ms para 2.4GHz
```

### Perfiles recomendados

**WiFi 5GHz (óptimo)**:
```python
SAMPLE_RATE = 44100
BLOCKSIZE = 256
JITTER_BUFFER_MS = 20
```

**WiFi 2.4GHz (compatible)**:
```python
SAMPLE_RATE = 22050
BLOCKSIZE = 128
JITTER_BUFFER_MS = 40
```

## 🔧 Resolución de Problemas

### No se detectan interfaces multi-canal

**Problema**: Solo aparece interfaz de 2 canales (estéreo)

**Solución**:
- Verifica drivers ASIO/WASAPI instalados
- Instala JACK Audio si ASIO no funciona
- Algunas interfaces requieren configuración en su panel de control

### Audio con glitches/cortes

**Problema**: Se escuchan clicks o silencios

**Soluciones**:
1. Aumentar `BLOCKSIZE` a 512 en `config.py`
2. Aumentar `JITTER_BUFFER_MS` a 40ms
3. Cambiar a WiFi 5GHz si estás en 2.4GHz
4. Reducir número de canales activos
5. Acercar dispositivo al router

### Latencia muy alta (>100ms)

**Problema**: Delay notable entre audio y acción

**Soluciones**:
1. Usar WiFi 5GHz en vez de 2.4GHz
2. Reducir `SAMPLE_RATE` a 22050 Hz
3. Reducir `BLOCKSIZE` a 128
4. Cerrar otras aplicaciones que usen red
5. Configurar QoS en router (priorizar puerto 5000)

### El navegador se suspende (smartphone)

**Problema**: Audio se detiene al bloquear pantalla

**Solución**:
- Mantener pantalla encendida durante uso
- Usar navegador Chrome (mejor soporte de Web Audio en background)
- En el futuro: implementar PWA con wake lock

## 📊 Especificaciones Técnicas

- **Latencia total**: 40-60ms (WiFi 5GHz), 60-100ms (WiFi 2.4GHz)
- **Sample rates**: 22050 Hz o 44100 Hz
- **Formato**: Int16 (optimizado para bandwidth)
- **Protocolo**: WebSocket binario
- **Max canales**: 32 por interfaz
- **Max clientes**: ~5 simultáneos (depende del hardware)
- **Ancho de banda**: ~86 KB/s por canal @ 44100 Hz

## 🎯 Casos de Uso

✅ **Ideal para**:
- Monitoreo de mezcla en ensayos
- Sistema IEM (In-Ear Monitor) económico
- Configuraciones multi-room
- Mezclas personalizadas por músico

❌ **No recomendado para**:
- Tocar instrumentos en tiempo real (necesitas <10ms)
- Grabación multipista sincronizada
- Audio crítico de alta fidelidad

## 📝 Notas

- Primera interacción requiere click en navegador (política de autoplay)
- ASIO/WASAPI funciona mejor que drivers genéricos
- WiFi 6 (802.11ax) reduce latencia ~5-10ms adicional
- Para Android nativo (menos latencia): considerar implementación futura

## 🐛 Reportar Problemas

Si encuentras bugs o tienes sugerencias, documenta:
- Sistema operativo
- Interfaz de audio (modelo)
- Configuración de red (WiFi 5GHz/2.4GHz)
- Mensaje de error completo