# 🎙️ Fichatech Audio Monitor

**Sistema profesional de monitoreo y streaming de audio en tiempo real con latencia ultra-baja** para aplicaciones de audio profesional, live monitoring y transmisión remota.

---

## 📋 Tabla de Contenidos

- [Características](#características)
- [Requisitos](#requisitos)
- [Instalación](#instalación)
- [Uso Rápido](#uso-rápido)
- [Arquitectura](#arquitectura)
- [Documentación Completa](#documentación-completa)
- [Soporte y Contribuciones](#soporte-y-contribuciones)

---

## ✨ Características

### 🔊 Motor de Audio Avanzado
- **Captura de audio de baja latencia**: Bloque de 32 muestras @ 48kHz (~0.67ms)
- **Soporte multi-canal**: Captura simultánea de múltiples canales de entrada
- **Compresión inteligente**: Compresión zlib optimizada para streaming
- **Gestión de dispositivos**: Registro automático y detección de dispositivos de audio
- **Análisis en tiempo real**: Procesamiento FFT para análisis de frecuencias

### 🌐 Conectividad
- **WebSocket moderno**: Interfaz web contemporánea con comunicación bidireccional
- **Protocolo Nativo**: Protocolo binario optimizado para clientes nativos (Android, iOS)
- **Modo RF**: Reconexión automática con caché persistente de estados
- **Multi-cliente**: Soporte simultáneo para clientes web y nativos

### 🎚️ Interfaz Gráfica
- **Monitor en tiempo real**: Visualización dinámica del estado del servidor
- **Estadísticas de rendimiento**: CPU, memoria, latencia y throughput
- **Control centralizado**: Gestión simple del servidor desde la GUI

### 🔒 Características Técnicas
- **Baja latencia**: Optimizaciones para minimizar retardos de end-to-end
- **Alta disponibilidad**: Reconexión automática y manejo de errores robusto
- **Escalabilidad**: ThreadPool configurable para envío paralelo de audio
- **Monitoreo**: Logging detallado y métricas de rendimiento

---

## 📦 Requisitos

### Sistema Operativo
- **Windows** 10 o superior
- **Python** 3.8+

### Dependencias Principales
```
numpy>=1.21.0
sounddevice>=0.4.5
flask>=2.0.0
flask-socketio>=5.0.0
python-socketio>=5.0.0
```

Ver `requirements.txt` para la lista completa.

---

## 🚀 Instalación

### Opción 1: Instalación desde Fuentes
```bash
# Clonar repositorio
git clone <repository-url>
cd audio-monitor

# Crear entorno virtual
python -m venv .venv

# Activar entorno (Windows)
.venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt
```

### Opción 2: Ejecutable Portable
Descarga el archivo `FichatechMonitor.exe` desde la carpeta `release/` para ejecutar la aplicación sin necesidad de instalar Python.

---

## 🎯 Uso Rápido

### Inicio del Servidor
```bash
python main.py
```

La aplicación iniciará automáticamente:
1. **GUI de Monitoreo**: Ventana principal con estadísticas en tiempo real
2. **WebSocket Server**: Disponible en `http://localhost:5100`
3. **Protocolo Nativo**: Escuchando en puerto `5101`

### Acceso Web
Abre tu navegador en: `http://localhost:5100`

### Conexión de Clientes
- **Android/iOS**: Usa el protocolo nativo (puerto 5101)
- **Web**: Conecta directamente a través del WebSocket en el navegador

---

## 🏗️ Arquitectura

### Componentes Principales

```
┌─────────────────────────────────────────────────────┐
│         GUI Monitor (CustomTkinter)                 │
│    - Estadísticas en tiempo real                    │
│    - Control del servidor                           │
└──────────────────────┬──────────────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         │                           │
    ┌────▼──────┐         ┌─────────▼───────┐
    │ Audio     │         │  WebSocket      │
    │ Capture   │         │  Server         │
    │           │         │                 │
    │ 48kHz     │         │  Flask + SIO    │
    │ 32-block  │         │  Web UI         │
    └──────┬────┘         └────────┬────────┘
           │                       │
    ┌──────┴───────┐         ┌────▼────────┐
    │              │         │             │
┌───▼────┐  ┌──────▼──┐  ┌──▼─────┐  ┌───▼──────┐
│Channel │  │ Audio   │  │Native  │  │ Clients  │
│Manager │  │ Mixer   │  │Protocol│  │ Web      │
└────────┘  └────────┘  └────────┘  └──────────┘
```

### Flujo de Datos
1. **Captura**: Sounddevice captura audio del dispositivo
2. **Procesamiento**: Channel Manager gestiona múltiples canales
3. **Compresión**: Zlib comprime el audio para streaming
4. **Distribución**: WebSocket + Protocolo Nativo envían a clientes
5. **Rendering**: Clientes renderean el audio recibido

---

## 📚 Documentación Completa

### Documentos Disponibles

| Documento | Contenido |
|-----------|----------|
| **[ARQUITECTURA.md](ARQUITECTURA.md)** | Explicación técnica detallada de componentes y diseño |
| **[GUIA_TECNICA.md](GUIA_TECNICA.md)** | Motor de audio, servidor, optimizaciones y latencia |
| **[PROTOCOLOS.md](PROTOCOLOS.md)** | Protocolo Nativo, WebSocket y Modo RF |
| **[POLITICAS.md](POLITICAS.md)** | Políticas de privacidad, licencia y términos |

---

## 🔧 Configuración

Edita [config.py](config.py) para personalizar:

```python
# Motor de Audio
DEFAULT_SAMPLE_RATE = 48000        # Frecuencia de muestreo
BLOCKSIZE = 32                     # Tamaño de bloque (latencia)
FORCE_MONO_CAPTURE = False         # Captura mono vs estéreo

# Red
WEB_PORT = 5100                    # Puerto WebSocket
NATIVE_PORT = 5101                 # Puerto protocolo nativo
NATIVE_MAX_CLIENTS = 10            # Máximo clientes nativos

# Optimizaciones
AUDIO_SEND_POOL_SIZE = 6           # Hilos de envío paralelo
SOCKET_TIMEOUT = 3.0               # Timeout de socket
RF_RECONNECT_DELAY_MS = 1000       # Delay de reconexión
```

---

## 📊 Estadísticas en Tiempo Real

La GUI muestra:
- **CPU**: Uso de procesador
- **Memoria**: Consumo de RAM
- **Latencia**: Latencia de red
- **Clientes**: Activos y conectados
- **Throughput**: Datos enviados/recibidos

---

## 🛠️ Compilación a Ejecutable

Genera un EXE portable usando PyInstaller:

```bash
# Opción 1: Spec file
python -m PyInstaller FichatechMonitor.spec

# Opción 2: Parámetros directo
python -m PyInstaller --onefile --name FichatechMonitor main.py
```

Resultado: `release/FichatechMonitor.exe`

---

## 🐛 Troubleshooting

### Error: "No audio input device found"
- Verifica que tengas un dispositivo de entrada de audio conectado
- Abre Configuración > Sonido y revisa los dispositivos disponibles

### Latencia alta
- Reduce `BLOCKSIZE` en config.py (ej: 16 en lugar de 32)
- Aumenta `AUDIO_SEND_POOL_SIZE` para mejor paralelización
- Verifica la conexión de red (WiFi vs Ethernet)

### Clientes no se conectan
- Verifica que los puertos 5100 y 5101 estén disponibles
- Revisa el firewall de Windows
- Confirma que cliente y servidor estén en la misma red

### Alto consumo de memoria
- Verifica `RF_MAX_PERSISTENT_STATES` en config.py
- Limpia logs antiguos en la carpeta `logs/`

---

## 📈 Performance

### Especificaciones
- **Latencia end-to-end**: ~50-100ms (depende de red)
- **CPU**: 5-10% en muestreo 48kHz con 4 canales
- **Memoria**: ~100-200MB base + 50MB por cliente activo
- **Throughput**: ~2.3Mbps por cliente a 48kHz 16-bit estéreo

---

## 🤝 Soporte y Contribuciones

### Reportar Problemas
Abre un issue con:
- SO y versión de Python
- Configuración de dispositivos de audio
- Logs de error (`logs/` folder)

### Contribuir
1. Fork del repositorio
2. Crea una rama: `git checkout -b feature/nueva-funcionalidad`
3. Commit cambios: `git commit -am 'Agrega nueva funcionalidad'`
4. Push: `git push origin feature/nueva-funcionalidad`
5. Submit Pull Request

---

## 📜 Licencia

Consulta [POLITICAS.md](POLITICAS.md) para detalles completos de licencia y términos de uso.

---

## 📞 Contacto

Para preguntas o soporte técnico, revisa la documentación en `ARQUITECTURA.md` y `GUIA_TECNICA.md`.

---

**Versión**: 1.0  
**Última actualización**: Enero 2026  
**Estado**: Producción
