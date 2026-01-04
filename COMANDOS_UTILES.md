# 🛠️ Comandos Útiles - Fichatech PWA

## 🚀 Iniciar el Servidor

```bash
# Con virtual environment
cd C:\audio-monitor
.\.venv\Scripts\activate
python main.py

# Ver que está corriendo en puerto 5000
# Acceder en navegador: http://localhost:5000
```

---

## 🔍 Verificar Estado

### Service Worker Registrado

```javascript
// En consola del navegador (F12):
navigator.serviceWorker.getRegistrations()
  .then(regs => console.log(regs))

// Deberías ver:
// ServiceWorkerRegistration { 
//   scope: 'http://localhost:5000/' 
// }
```

### Cache Disponible

```javascript
// En consola:
caches.keys().then(names => console.log(names))

// Deberías ver:
// ['fichatech-audio-v1', 'fichatech-dynamic-v1']
```

### Lista de Iconos

```bash
# En PowerShell:
Get-ChildItem C:\audio-monitor\assets\icon-*.png | ForEach-Object { 
  Write-Host "$($_.Name) - $([math]::Round($_.Length/1KB, 1))KB"
}

# Resultado:
# icon-72.png - 2.1KB
# icon-96.png - 2.8KB
# icon-128.png - 3.5KB
# ... etc
```

---

## 📝 Generar Iconos (si necesitas regenerar)

```bash
# Desde el directorio raíz
.\.venv\Scripts\activate
python assets/generate_pwa_icons.py

# Resultado:
# 📦 Generando iconos PWA desde: C:\audio-monitor\assets\icon.png
# ✅ Generado: icon-72.png (72x72)
# ... etc
```

---

## 🔧 Limpiar Cache (si hay problemas)

### Opción 1: Desde DevTools

```
F12 → Application → Storage
  ├─ Click "Clear site data"
  ├─ Selecciona todo
  └─ Clear
```

### Opción 2: Desde Consola

```javascript
// Borrar todos los caches
caches.keys().then(names =>
  Promise.all(names.map(name => caches.delete(name)))
)

// Desregistrar Service Worker
navigator.serviceWorker.getRegistrations()
  .then(regs => regs.forEach(r => r.unregister()))
```

### Opción 3: Completa (reinstalar)

```bash
# 1. Cierra el navegador completamente
# 2. Elimina:
#    - AppData\Local\Google\Chrome\User Data (si quieres limpiar todo)
# 3. Reincicia el servidor
# 4. Abre en navegador fresh
```

---

## 🐛 Debugging

### Ver Logs del Servidor

```bash
# En la terminal donde corre main.py, busca logs que digan:
# [Sync] Mixer actualizado por cambio externo
# [PWA] ✅ Service Worker registrado
# [PWA] Nueva versión detectada
```

### Monitorear Sincronización

```javascript
// En consola del navegador:

// Monitorear cambios en clients
const original = controlCenter.socket.on;
controlCenter.socket.on = function(...args) {
  if (args[0] === 'clients_update') {
    console.log('[Monitor] clients_update received:', args[1]);
  }
  return original.apply(this, args);
};

// Monitorear renders
controlCenter.originalRender = controlCenter.renderMixer;
controlCenter.renderMixer = function(clientId) {
  console.log('[Monitor] renderMixer called for:', clientId);
  return controlCenter.originalRender.call(this, clientId);
};
```

### Ver Peticiones de Red

```
F12 → Network
  ├─ Filtra por "ws" para WebSocket
  ├─ Filtra por "socket.io" para eventos
  └─ Verifica latencia en cada mensaje
```

---

## 📊 Profiling de Rendimiento

### Latencia de Sincronización

```javascript
// En consola:
performance.mark('sync-start');

// ... espera a que llegue clients_update ...

performance.mark('sync-end');
performance.measure('sync', 'sync-start', 'sync-end');

const measures = performance.getEntriesByType('measure');
console.log('Latencia:', measures[0].duration, 'ms');
```

### Uso de Memoria

```javascript
// En consola:
if (performance.memory) {
  console.log({
    usedJSHeapSize: (performance.memory.usedJSHeapSize / 1048576).toFixed(2) + ' MB',
    totalJSHeapSize: (performance.memory.totalJSHeapSize / 1048576).toFixed(2) + ' MB',
    jsHeapSizeLimit: (performance.memory.jsHeapSizeLimit / 1048576).toFixed(2) + ' MB'
  });
}
```

---

## 🌐 Acceso desde Otros Dispositivos

### En la Misma Red

```
Tu IP (Windows):
  1. Win + R
  2. "cmd"
  3. ipconfig
  4. Busca "IPv4 Address" (ej: 192.168.1.100)
  5. En otro dispositivo: http://192.168.1.100:5000

Desde Android/iOS:
  1. Conecta a la misma WiFi
  2. Abre navegador
  3. http://tu-ip:5000
  4. Cuando aparezca el botón de instalar, haz clic
```

### Acceso Remoto (desde fuera de la red)

```
Opción 1: Tunnel (ngrok)
  1. Descarga: https://ngrok.com/download
  2. Descomprimir: ngrok.exe
  3. Ejecutar: ngrok http 5000
  4. Copiar URL que sale (ej: https://abc123.ngrok.io)
  5. Compartir URL con otros dispositivos

Opción 2: Port Forwarding (en tu router)
  1. Accede a router config (192.168.1.1)
  2. Busca "Port Forwarding"
  3. Forward puerto 5000 externo → tu-ip:5000 interno
  4. Compartir tu IP pública (ej: 203.0.113.42:5000)

Opción 3: VPN
  1. Configura una VPN en tu servidor
  2. Los clientes se conectan a la VPN
  3. Acceden como si estuvieran en la red local
```

---

## 🔐 Producción (HTTPS)

### Generar Certificado SSL (para HTTPS)

```bash
# Usando Python:
python -m http.server 5000

# Usando mkcert (recomendado):
# 1. Descargar: https://github.com/FiloSottile/mkcert
# 2. mkcert -install
# 3. mkcert localhost 127.0.0.1 ::1
# 4. Configurar en main.py para usar los certs

# En main.py:
# socketio.run(app, host='0.0.0.0', port=5000, 
#              ssl_context=('cert.pem', 'key.pem'))
```

### PWA Requisitos en Producción

```
✅ HTTPS (obligatorio)
✅ Service Worker activo
✅ Manifest.json válido
✅ Icons en múltiples tamaños
✅ Display: standalone
✅ Theme-color definido
✅ Responsive design

Nuestro sistema cumple todos ✅
```

---

## 🧹 Mantenimiento

### Backup de Configuración

```bash
# Guardar estado de clientes
Copy-Item C:\audio-monitor\config\devices.json `
          C:\backup\devices.json.bak

Copy-Item C:\audio-monitor\config\client_states.json `
          C:\backup\client_states.json.bak
```

### Limpiar Logs Antiguos

```bash
# Mantener solo últimos 7 días
Get-ChildItem C:\audio-monitor\logs\*.log |
  Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } |
  Remove-Item -Force
```

### Monitorear Espacio de Disco

```bash
# Cache de iconos
Get-Item C:\audio-monitor\assets\icon-*.png |
  Measure-Object -Property Length -Sum

# Resultado: tamaño total en bytes
```

---

## 📱 Instalar en Diferentes Navegadores

### Chrome / Edge (Windows)

```
1. http://localhost:5000
2. Click ⬇️ en barra de direcciones
3. "Instalar Fichatech Audio Control"
4. ✅ App instalada
```

### Safari (iOS / macOS)

```
1. Abre en Safari: http://tu-ip:5000
2. Compartir (ícono con flecha)
3. "Agregar a pantalla de inicio"
4. Nombre: "Fichatech"
5. ✅ App instalada
```

### Chrome (Android)

```
1. Abre en Chrome: http://tu-ip:5000
2. Menú (⋮) → "Instalar app"
3. Confirma
4. ✅ App instalada
```

### Firefox (múltiples plataformas)

```
Nota: Firefox tiene soporte PWA limitado
Funciona mejor en Firefox 55+

1. Abre: http://tu-ip:5000
2. Menú (☰) → "Aplicaciones" → "Instalar esta app"
3. ✅ App instalada
```

---

## ⚙️ Variables de Configuración

### En `config.py`

```python
# Puerto servidor web
WEB_PORT = 5000

# Puerto servidor nativo (Android)
NATIVE_PORT = 5555

# Sample rate de audio
SAMPLE_RATE = 48000

# Blocksize (tamaño de buffer)
BLOCKSIZE = 256  # ~5.33ms de latencia

# Debug mode
DEBUG = False

# Log level
LOG_LEVEL = 'INFO'

# Cambiar estas si necesitas ajustar rendimiento
```

---

## 🚨 Errores Comunes y Soluciones

### Error: "Service Worker failed to register"

```javascript
// Solución:
// 1. Asegurate que está en HTTPS (o localhost)
// 2. Verifica que sw.js existe en frontend/sw.js
// 3. Limpia el cache: DevTools → Clear site data
// 4. Recarga completamente: Ctrl+Shift+R
```

### Error: "Cannot connect to server"

```bash
# 1. Verifica que el servidor está corriendo:
netstat -an | findstr 5000

# 2. Verifica firewall:
# Windows: Settings → Privacy → Firewall → Allow app
# macOS: System Preferences → Security → Firewall

# 3. Verifica que usas la IP correcta:
ipconfig | findstr IPv4
```

### Error: "Mixer no se actualiza"

```javascript
// 1. Abre consola (F12)
// 2. Busca logs de [Sync]
// 3. Si no hay, la sincronización no está llegando

// 4. Verifica conexión WebSocket:
// F12 → Network → WS → filtra por socket.io
// Deberías ver conexión establecida
```

### Error: "PWA no se instala"

```
1. ¿Navegador compatible? 
   Chrome 67+, Edge 79+, Firefox 55+, Safari 14+

2. ¿HTTP o HTTPS? 
   Producción NECESITA HTTPS
   Desarrollo OK con localhost

3. ¿Manifest.json válido?
   F12 → Application → Manifest
   Busca errores en rojo

4. Limpia cache:
   DevTools → Clear site data → Refresh
```

---

## 📚 Referencias Rápidas

```bash
# Documentación
📖 docs/SINCRONIZACION_BIDIRECCIONAL_Y_PWA.md    # Completo
⚡ docs/GUIA_RAPIDA_PWA.md                        # Rápido
📋 docs/README_DOCUMENTACION.md                  # Índice

# Resumen
📄 RESUMEN_CAMBIOS.md                            # Ejecutivo
🎨 DIAGRAMA_VISUAL.txt                          # Visual

# Archivos de configuración
⚙️  config.py                                     # Config
📄 frontend/manifest.json                        # PWA metadata
🔄 frontend/sw.js                                # Service Worker
📱 frontend/index.html                           # UI principal
```

---

## 🎯 Próximos Comandos a Probar

```bash
# 1. Verificar instalación
node -v && npm -v  # Si quieres instalar dependencias JS

# 2. Probar con diferentes IPs
ping tu-ip

# 3. Ver procesos Python
Get-Process python

# 4. Monitorear puerto 5000
netstat -ano | findstr :5000
```

---

**💡 Tip:** Guarda estos comandos en un archivo batch para acceso rápido

```batch
@echo off
REM start-fichatech.bat

cd C:\audio-monitor
.\.venv\Scripts\activate
python main.py
```

Luego ejecuta: `start-fichatech.bat`
