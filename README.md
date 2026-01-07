# 🎵 Fichatech Audio Monitor

Servidor de audio profesional multiplataforma para monitoreo, control y transmisión en tiempo real. Optimizado para ultra-baja latencia, múltiples clientes (Android, Web, Maestro) y aplicaciones RF.

---

## 🚀 Características Principales
- **Captura de audio** en tiempo real (48kHz, blocksize 64 = ~10ms latencia)
- **Transmisión simultánea** a clientes Android nativos, Web UI y cliente maestro
- **Control remoto** de ganancia, panorama y mute por canal
- **Compresión zlib** para eficiencia en RF
- **Persistencia** de dispositivos y estado de canales
- **Interfaz Web PWA**: control desde cualquier navegador, instalable como app
- **GUI Desktop**: monitoreo local, estadísticas y control

---

## 📦 Instalación

1. **Clona el repositorio o descarga el proyecto**
2. Instala dependencias:
   ```bash
   pip install -r requirements.txt
   ```
3. Inicia el servidor:
   ```bash
   python main.py
   ```
4. Accede a la Web UI:
   - [http://localhost:5000](http://localhost:5000)

---

## 🖥️ Estructura de Carpetas

```
├── main.py                # Punto de entrada principal
├── config.py              # Configuración global
├── gui_monitor.py         # GUI Desktop (customtkinter)
├── audio_server/          # Núcleo de servidor de audio
│   ├── audio_capture.py
│   ├── channel_manager.py
│   ├── audio_mixer.py
│   ├── websocket_server.py
│   ├── native_server.py
│   ├── device_registry.py
│   ├── audio_compression.py
│   └── latency_optimizer.py
├── frontend/              # Interfaz Web (PWA)
│   ├── index.html
│   ├── styles.css
│   ├── sw.js
│   ├── manifest.json
│   └── heartbeat-worker.js
├── config/                # Estado persistente
│   ├── devices.json
│   ├── channels_state.json
│   ├── client_states.json
│   └── web_ui_state.json
├── requirements.txt       # Dependencias Python
├── ARQUITECTURA.md        # Documentación de componentes
├── ANALISIS.md            # Análisis general
├── FRONTEND.md            # Documentación Web UI
├── PROTOCOLO_NATIVO.md    # Protocolo Android/RF
├── GUIA_USO.md            # Guía de uso y troubleshooting
├── INDICE.md              # Índice de documentación
```

---

## 📖 Documentación

- **[INDICE.md](INDICE.md)**: Guía de lectura y navegación
- **[ANALISIS.md](ANALISIS.md)**: Visión general y arquitectura
- **[ARQUITECTURA.md](ARQUITECTURA.md)**: Componentes backend
- **[FRONTEND.md](FRONTEND.md)**: Web UI y PWA
- **[PROTOCOLO_NATIVO.md](PROTOCOLO_NATIVO.md)**: Protocolo Android/RF
- **[GUIA_USO.md](GUIA_USO.md)**: Manual de uso y troubleshooting

---

## 🛠️ Tecnologías
- **Python 3.9 - 3.13**
- **sounddevice** (PortAudio)
- **Flask** + **Flask-SocketIO**
- **customtkinter** (GUI)
- **zlib** (compresión)
- **HTML/CSS/JS** (Web UI)
- **Kotlin/Oboe** (Android nativo)

---

## 📱 Clientes Soportados
- **Android nativo** (protocolo binario TCP/UDP)
- **Web UI** (Socket.IO, PWA)
- **Cliente Maestro** (streaming de mezcla)

---

## ⚡ Configuración Rápida

Edita `config.py` para:
- Sample rate, blocksize, número de canales
- Habilitar/deshabilitar cliente maestro
- Ajustar parámetros de red y rendimiento

---

## 📝 Licencia

Proyecto privado Fichatech. Uso interno y educativo.

---

## 📞 Soporte

Para dudas técnicas, revisa la documentación en los archivos `.md` o contacta al equipo Fichatech.
