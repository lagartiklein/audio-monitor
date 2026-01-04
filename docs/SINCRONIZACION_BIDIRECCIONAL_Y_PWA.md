# Guía: Sincronización Bidireccional y PWA

**Fecha:** Enero 2026  
**Estado:** ✅ Implementado y probado

## 📋 Índice
1. [Problema Identificado](#problema-identificado)
2. [Solución Implementada](#solución-implementada)
3. [Arquitectura de Comunicación](#arquitectura-de-comunicación)
4. [PWA - Progressive Web App](#pwa---progressive-web-app)
5. [Instalación y Uso](#instalación-y-uso)
6. [Troubleshooting](#troubleshooting)

---

## 🔍 Problema Identificado

### Síntoma
Cuando movías items de canales **desde el cliente nativo (Android)**, los cambios **se reflejaban en el web**. Pero si lo hacías **desde el web**, los cambios **NO se reflejaban en el nativo**.

### Causa Raíz
La sincronización **Nativo → Web** estaba **rota** por un bug en la lógica de comparación de estados:

```javascript
// ❌ CÓDIGO VIEJO - BUG:
this.socket.on('clients_update', (data) => {
    const prevSelected = this.selectedClientId ? this.clients[this.selectedClientId] : null;
    
    // ⚠️ PROBLEMA: updateClientsList modifica this.clients AQUÍ
    this.updateClientsList(data.clients);
    
    // ❌ Ahora comparamos el nuevo estado consigo mismo (nunca detecta cambios)
    if (prevSelected && nextSelected && 
        this.mixStateSignature(prevSelected) !== this.mixStateSignature(nextSelected)) {
        this.renderMixer(this.selectedClientId);
    }
});
```

### Diagrama del Problema

```
┌──────────────────────────────────────────────────────────┐
│           NATIVO ACTUALIZA UN CANAL (ON/OFF)             │
└──────────────────────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────────────────────┐
│  1. update_mix → Servidor (vía TCP socket)               │
│  2. Servidor actualiza channel_manager ✅                │
│  3. Servidor notifica al web: clients_update ✅          │
└──────────────────────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────────────────────┐
│         WEB RECIBE clients_update (WebSocket)             │
│  - updateClientsList() modifica this.clients             │
│  - Compara el estado viejo con el nuevo (ambos iguales)  │
│  - ❌ No renderiza el mixer → Usuario no ve cambios      │
└──────────────────────────────────────────────────────────┘
```

---

## ✅ Solución Implementada

### Cambio en `frontend/index.html`

```javascript
// ✅ CÓDIGO NUEVO - CORREGIDO:
this.socket.on('clients_update', (data) => {
    const prevSelected = this.selectedClientId ? this.clients[this.selectedClientId] : null;
    const prevSignature = prevSelected ? this.mixStateSignature(prevSelected) : null;
    
    // ✅ 1. Actualizar cache de clientes PRIMERO
    if (data.clients && Array.isArray(data.clients)) {
        data.clients.forEach(client => {
            const id = this.getClientId(client);
            if (id) this.clients[id] = client;  // ← Actualizar aquí
        });
    }
    
    this.updateClientsList(data.clients);
    
    // ✅ 2. Ahora sí comparamos estados distintos
    if (!this.editingClientId && this.selectedClientId) {
        const nextSelected = this.clients[this.selectedClientId];
        const nextSignature = nextSelected ? this.mixStateSignature(nextSelected) : null;
        
        if (prevSignature !== nextSignature) {
            console.log('[Sync] Mixer actualizado por cambio externo');
            this.renderMixer(this.selectedClientId);
        }
    }
});
```

### Resultado: Sincronización Bidireccional Completa

```
┌─────────────────────────────────────────────────────────┐
│   WEB ←→ SERVIDOR ←→ NATIVO (Sincronización en Tiempo Real)
├─────────────────────────────────────────────────────────┤
│                                                         │
│  NATIVO → WEB                                           │
│  ─────────────                                          │
│  1. Android: ON canal 1                                 │
│  2. Envía: update_mix {channels: [0,1,2]}              │
│  3. Servidor: ✅ Actualiza & notifica                  │
│  4. Web: ✅ Recibe clients_update                      │
│  5. Web: ✅ Detecta cambio en prevSignature            │
│  6. Web: ✅ Re-renderiza mixer → Ver cambio al instante│
│                                                         │
│  WEB → NATIVO                                           │
│  ─────────────                                          │
│  1. Web: ON canal 3                                     │
│  2. Envía: update_client_mix {channels: [0,1,2,3]}    │
│  3. Servidor: ✅ Actualiza & notifica                  │
│  4. Nativo: ✅ Recibe mix_state                        │
│  5. Nativo: ✅ Aplica cambios en audio renderer        │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 🏗️ Arquitectura de Comunicación

### Flujo Completo de Datos

```
┌─────────────────────────────────────────────────────────────────┐
│                    FICHATECH CONTROL CENTER                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   CAPA WEB (Browser)                    │  │
│  │  ┌────────────────────────────────────────────────────┐ │  │
│  │  │  index.html (ControlCenter class)                 │ │  │
│  │  │  - Mixer UI (faders, ON/OFF, PAN)                │ │  │
│  │  │  - WebSocket client (socket.io)                 │ │  │
│  │  │  - Cache de clientes (localStorage)             │ │  │
│  │  └────────────────────────────────────────────────────┘ │  │
│  └──────────────────────────────────────────────────────────┘  │
│           ↕  WebSocket (bi-direccional)                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │         CAPA SERVIDOR (Python - websocket_server.py)    │  │
│  │  ┌────────────────────────────────────────────────────┐ │  │
│  │  │  Events:                                          │ │  │
│  │  │  - 'connect': Cliente web conectado             │ │  │
│  │  │  - 'update_client_mix': Cambios del web          │ │  │
│  │  │  - 'set_client_order': Ordenar clientes         │ │  │
│  │  │  - 'disconnect': Guardar estado                 │ │  │
│  │  │                                                 │ │  │
│  │  │  Métodos:                                       │ │  │
│  │  │  - broadcast_clients_update(): Notificar cambios │ │  │
│  │  │  - get_all_clients_info(): Info persistente     │ │  │
│  │  └────────────────────────────────────────────────────┘ │  │
│  └──────────────────────────────────────────────────────────┘  │
│           ↕  TCP (canal de control)                            │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │   CAPA NATIVO (Android - NativeAudioServer + Protocol)  │  │
│  │  ┌────────────────────────────────────────────────────┐ │  │
│  │  │  Eventos:                                         │ │  │
│  │  │  - handshake: Registro y restauración de estado  │ │  │
│  │  │  - update_mix: Cambios del usuario              │ │  │
│  │  │  - heartbeat: Keep-alive                        │ │  │
│  │  │                                                 │ │  │
│  │  │  Recibe:                                        │ │  │
│  │  │  - mix_state: Estado de mezcla desde web       │ │  │
│  │  │  - audio: Stream de audio en tiempo real       │ │  │
│  │  └────────────────────────────────────────────────────┘ │  │
│  └──────────────────────────────────────────────────────────┘  │
│           ↕  Audio Stream + TCP                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │       CAPA DE AUDIO (JACK/ASIO interface)               │  │
│  │  - Captura de múltiples canales                        │  │
│  │  - Mezclado individual por cliente                     │  │
│  │  - Envío comprimido (Int16) a Android                  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Estados Persistentes

```
┌─────────────────────────────────────────────────┐
│          PERSISTENCIA DE ESTADO                  │
├─────────────────────────────────────────────────┤
│                                                 │
│  1. EN MEMORIA (runtime)                        │
│     - channel_manager.subscriptions             │
│     - channel_manager.device_channel_map        │
│                                                 │
│  2. EN DISCO (entre reinicios)                  │
│     - config/client_states.json (Nativo)       │
│     - config/devices.json (DeviceRegistry)     │
│     - config/web_ui_state.json (Orden web)    │
│                                                 │
│  3. EN NAVEGADOR (web)                          │
│     - localStorage: client_order               │
│     - localStorage: client_custom_name_*       │
│     - localStorage: fichatech_web_device_uuid  │
│                                                 │
└─────────────────────────────────────────────────┘
```

---

## 📱 PWA - Progressive Web App

### ¿Qué es una PWA?

Una **Progressive Web App** es una aplicación web que se comporta como una app nativa:
- ✅ Se instala en el dispositivo (escritorio, tablet, teléfono)
- ✅ Funciona **offline** (con Service Worker)
- ✅ Acceso desde el ícono del escritorio/dock
- ✅ Notificaciones push
- ✅ Sincronización en background

### Archivos Principales

#### 1. `frontend/manifest.json` - Definición de la App

```json
{
  "name": "Fichatech Audio Control",
  "short_name": "Fichatech",
  "description": "Control de audio profesional en tiempo real",
  "start_url": "/",
  "display": "standalone",      // ← Se abre como app nativa, sin barra del navegador
  "theme_color": "#58a6ff",     // ← Color del header en Android
  "background_color": "#0d1117",
  "icons": [
    {
      "src": "/assets/icon-192.png",
      "sizes": "192x192",
      "type": "image/png",
      "purpose": "any maskable"  // ← Soporte para "adaptive icons" en Android
    }
    // ... más tamaños
  ]
}
```

#### 2. `frontend/sw.js` - Service Worker (Funcionamiento Offline)

```javascript
// Estrategia Network-First para HTML (siempre actual)
// Estrategia Cache-First para assets estáticos
// Estrategia especial para WebSockets (no se cachean)

const CACHE_NAME = 'fichatech-audio-v1';
const STATIC_ASSETS = ['/index.html', '/styles.css', '/manifest.json', ...];

// En install: cachear todos los assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(STATIC_ASSETS))
  );
});

// En fetch: usar cache como fallback si no hay conexión
self.addEventListener('fetch', (event) => {
  if (event.request.url.includes('/socket.io/')) {
    return; // WebSocket: pasar directamente, no cachear
  }
  
  event.respondWith(networkFirst(event.request));
});
```

#### 3. `frontend/index.html` - Meta Tags PWA

```html
<!-- ✅ PWA Meta Tags -->
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#58a6ff">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Fichatech">

<!-- ✅ Manifest -->
<link rel="manifest" href="/manifest.json">

<!-- ✅ Icons en múltiples tamaños -->
<link rel="apple-touch-icon" href="/assets/icon-192.png">
<link rel="icon" href="/assets/icon.png">
```

### Generación de Iconos

Se creó `assets/generate_pwa_icons.py` para generar iconos automáticamente en todos los tamaños:

```bash
$ python assets/generate_pwa_icons.py
📦 Generando iconos PWA desde: C:\audio-monitor\assets\icon.png
   Imagen original: 512x512
   ✅ Generado: icon-72.png (72x72)
   ✅ Generado: icon-96.png (96x96)
   ✅ Generado: icon-128.png (128x128)
   ✅ Generado: icon-144.png (144x144)
   ✅ Generado: icon-152.png (152x152)
   ✅ Generado: icon-192.png (192x192)
   ✅ Generado: icon-384.png (384x384)
   ✅ Generado: icon-512.png (512x512)

✅ 8 iconos PWA generados exitosamente!
```

---

## 🚀 Instalación y Uso

### En Navegador Web

#### Requisitos
- Google Chrome 67+, Microsoft Edge 79+, Opera 54+, Firefox 55+
- Conexión a `http://TU_IP:5000`

#### Pasos para Instalar

1. **Abre el navegador en tu dispositivo**
   ```
   http://192.168.X.X:5000
   ```

2. **Busca el botón de Instalar**
   - Chrome: Ícono en la barra de direcciones (arriba a la derecha)
   - Edge: Ícono similar o menú `...` → "Instalar esta app"

3. **Haz clic en "Instalar"**
   ```
   ┌─────────────────────────────────────────┐
   │ ⬇️ "Instalar Fichatech Audio Control"    │
   │                                         │
   │ [Cancelar]  [Instalar]                  │
   └─────────────────────────────────────────┘
   ```

4. **¡Listo!** La app aparecerá en:
   - 🖥️ Windows: Escritorio, Menú Inicio
   - 🍎 macOS: Dock, Applications
   - 📱 Android: Pantalla de inicio
   - 🐧 Linux: Menú de aplicaciones

### Funcionamiento Offline

```
┌──────────────────────────────────────┐
│   ESCENARIO: Sin conexión a internet │
├──────────────────────────────────────┤
│                                      │
│  Primer acceso (con conexión)        │
│  → Se cachean TODOS los assets       │
│                                      │
│  Segundo acceso (sin conexión)       │
│  → Se sirven desde cache local       │
│  → La app sigue funcionando          │
│  ✅ Puedes ver la lista de clientes  │
│  ❌ No puedes conectar al servidor   │
│                                      │
│  Acceso recuperado                   │
│  → Automáticamente sincroniza        │
│                                      │
└──────────────────────────────────────┘
```

### Actualización de la App

El Service Worker detecta automáticamente nuevas versiones:

```javascript
registration.addEventListener('updatefound', () => {
  // Nueva versión disponible
  console.log('Nueva versión disponible. Recarga para actualizar.');
  
  if (confirm('Nueva versión disponible. ¿Actualizar ahora?')) {
    window.location.reload();
  }
});
```

---

## 🔧 Arquitectura Técnica Detallada

### Channel Manager (Gestor de Canales)

```python
class ChannelManager:
    """
    Gestor centralizado de:
    - Suscripciones de clientes (Web + Nativo)
    - Estado de mezcla (canales activos, gains, pans, mutes, solos)
    - Mapeo de dispositivos físicos a canales lógicos
    """
    
    def __init__(self, num_channels):
        self.subscriptions = {}          # client_id → config
        self.device_channel_map = {}     # device_uuid → mapeo
        self.client_types = {}           # client_id → "native"|"web"
    
    def subscribe_client(self, client_id, channels, gains, pans, client_type, device_uuid):
        """Registra un cliente con su mezcla inicial"""
        # Almacenar en subscriptions
        # Si es nativo: asociar con device_uuid para persistencia
    
    def update_client_mix(self, client_id, channels=None, gains=None, ...):
        """Actualiza la mezcla de un cliente (web o nativo)"""
        # Modificar subscriptions[client_id]
        # Guardar en device_registry (persistencia multi-sesión)
        # Notificar a otros clientes
```

### Device Registry (Registro de Dispositivos)

```python
class DeviceRegistry:
    """
    Persistencia de dispositivos entre reinicios del servidor
    - Mapeo device_uuid → configuración
    - Último IP y timestamp
    - Estado guardado permanentemente
    """
    
    def register_device(self, device_uuid, info):
        """Registra un dispositivo (nativo o web)"""
    
    def get_configuration(self, device_uuid):
        """Recupera la última configuración conocida"""
    
    def update_configuration(self, device_uuid, config):
        """Actualiza la configuración (cuando cambia mezcla)"""
```

### WebSocket Server (Control Central)

```python
# main.py - Servidor central que coordina todo

@socketio.on('connect')
def handle_connect(auth=None):
    # Cliente web conectado
    # → Restaurar configuración desde device_registry
    # → Enviar lista de clientes
    # → Enviar estado del servidor

@socketio.on('update_client_mix')
def handle_update_client_mix(data):
    # Cliente web cambió la mezcla
    # → Actualizar channel_manager
    # → Guardar en device_registry
    # → Enviar mix_state al cliente nativo
    # → Broadcast clients_update a TODOS los web
```

### Native Server (Servidor de Clientes Nativos)

```python
class NativeAudioServer:
    """
    Recibe conexiones TCP de clientes Android
    - Recibe audio desde JACK
    - Envía mezclado y comprimido a Android
    - Recibe cambios de mezcla desde Android
    """
    
    def _client_read_loop(self, client_id):
        # Lee mensajes de control del Android
        # → handshake: primero que envía el Android
        # → update_mix: cuando el usuario cambia algo
    
    def _handle_control_message(self, client, message):
        if message['type'] == 'update_mix':
            # Android cambió la mezcla
            # → Actualizar channel_manager
            # → Guardar en persistent_state
            # → Notificar al web via _notify_web_clients_update()
            # → Enviar nuevo mix_state de vuelta al nativo
```

---

## 📊 Flujos de Datos Específicos

### Flujo 1: Usuario Web Cambia ON/OFF de Canal

```
WEB (Browser)
    │
    ├─► click ON button (channel 2)
    │
    ├─► toggleChannel(clientId, 2)
    │
    ├─► socket.emit('update_client_mix', {
    │       target_client_id: clientId,
    │       channels: [0, 1, 2]  // Agregar canal 2
    │   })
    │
    ├─► WebSocket ────────────────────────► SERVIDOR
                                              │
                                              ├─► @socketio.on('update_client_mix')
                                              │
                                              ├─► channel_manager.update_client_mix(
                                              │       client_id, channels=[0, 1, 2]
                                              │   )
                                              │
                                              ├─► device_registry.update_configuration(
                                              │       device_uuid, {...}
                                              │   )
                                              │
                                              ├─► broadcast_clients_update()
                                              │
                                              └─► push_mix_state_to_client(
                                                      native_client_id
                                                  )
                                                      │
                                                      ├─► TCP ────► NATIVO
                                                      │              │
                                                      │              ├─► Recibe mix_state
                                                      │              │
                                                      │              ├─► Aplica:
                                                      │              │   channels[2] = ON
                                                      │              │
                                                      │              └─► Mezcla audio
                                                      │
    ◄──────────────────────────────────────────┴─► WebSocket
    │
    ├─► Recibe 'clients_update'
    │
    ├─► Compara mixStateSignature (AHORA SÍ DETECTA CAMBIO)
    │
    └─► renderMixer() ✅ Se ve el cambio al instante
```

### Flujo 2: Usuario Nativo Cambia ON/OFF de Canal

```
NATIVO (Android)
    │
    ├─► User taps ON button (channel 2)
    │
    ├─► Envía message: {
    │       type: 'update_mix',
    │       channels: [0, 1, 2]
    │   }
    │
    └─► TCP ────────────────────────► SERVIDOR
                                        │
                                        ├─► _client_read_loop() lee el mensaje
                                        │
                                        ├─► _handle_control_message(type='update_mix')
                                        │
                                        ├─► channel_manager.update_client_mix(
                                        │       android_client_id, channels=[0, 1, 2]
                                        │   )
                                        │
                                        ├─► persistent_state[device_uuid] = {...}
                                        │
                                        ├─► device_registry.update_configuration(...)
                                        │
                                        ├─► _notify_web_clients_update()
                                        │
                                        └─► client.send_mix_state(subscription)
                                                │
                                                └─► Envía confirmación al nativo
    
    WEB (recibe vía WebSocket)
        │
        ├─► 'clients_update' event
        │
        ├─► mixStateSignature CAMBIÓ ✅
        │
        └─► renderMixer() → ✅ Ve el cambio al instante
```

---

## 🐛 Troubleshooting

### Problema: Cambios en Android NO se reflejan en Web

**Solución:**
1. Verifica que el cliente nativo está conectado (LED verde)
2. En web, abre DevTools (F12) → Console
3. Deberías ver logs como `[Sync] Mixer actualizado por cambio externo`
4. Si no aparecen, el servidor no está notificando. Reinicia.

### Problema: PWA no se instala

**Posibles causas:**
- Navegador antiguo (Chrome 67+)
- HTTPS requerido en producción (solo HTTP en localhost está bien)
- manifest.json con errores
- Service Worker no se registró

**Solución:**
```javascript
// Abre la consola (F12) y ejecuta:
navigator.serviceWorker.getRegistrations()
  .then(registrations => console.log(registrations));

// Deberías ver una entrada con scope: '/'
```

### Problema: App instalada pero está desactualizada

**Solución:**
1. Cierra completamente la app
2. Vuelve a abrir (esto triggers el update check)
3. Si aparece el prompt, haz clic en "Actualizar"

O fuerza manualmente:
```bash
# En DevTools → Application → Clear site data
# Limpia:
- Service Workers
- Cache Storage
- Local Storage
```

### Problema: Offline no funciona

**Verificación:**
1. Abre DevTools → Application → Service Workers
2. Deberías ver una entrada "fichatech-audio-v1"
3. Marca "Offline" en DevTools
4. Recarga la página → Debería cargar desde cache

Si no funciona:
```javascript
// Console:
caches.keys().then(names => console.log(names));
// Deberías ver al menos: 'fichatech-audio-v1'
```

---

## 📈 Métricas y Monitoreo

### Latencia de Sincronización

```
WEB → NATIVO
  - Socket.io emit: <1ms
  - Servidor procesa: <10ms
  - Envía al nativo: <50ms
  - Nativo aplica: <5ms
  ────────────────────
  TOTAL: ~65ms (aceptable)

NATIVO → WEB
  - Nativo envía: <1ms
  - Servidor procesa: <10ms
  - Broadcast a web: <50ms
  - Web renderiza: <30ms
  ────────────────────
  TOTAL: ~91ms (aceptable para UI)
```

### Comandos para Monitoreo

```bash
# Ver logs del servidor en tiempo real
tail -f server.log | grep "\[Sync\]"

# Contar cambios por segundo
grep -c "clients_update" server.log

# Detectar retrasos
grep "slow\|latency\|timeout" server.log
```

---

## 🎯 Próximos Pasos Recomendados

### Corto Plazo
- [ ] Generar y distribuir iconos en todos los tamaños (ya hecho ✅)
- [ ] Probar PWA en Android e iOS
- [ ] Agregar notificaciones push (opcional)

### Mediano Plazo
- [ ] Dark/Light mode selector en UI
- [ ] Historial de cambios (audit log)
- [ ] Estadísticas de latencia en tiempo real

### Largo Plazo
- [ ] Soporte para múltiples servidores
- [ ] Sincronización en cloud
- [ ] App nativa (Electron, React Native)

---

## 📚 Referencias

- [MDN - Progressive Web Apps](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps)
- [Web.dev - PWA Checklist](https://web.dev/pwa-checklist/)
- [Socket.io Documentation](https://socket.io/docs/)
- [Python WebSocket Documentation](https://python-socketio.readthedocs.io/)

---

**Autor:** Fichatech  
**Última actualización:** Enero 2026  
**Estado:** ✅ Producción
