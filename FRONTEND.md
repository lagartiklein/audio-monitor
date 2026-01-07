# 🌐 FRONTEND - Web UI y PWA

## 📋 Tabla de Contenidos
1. [Estructura HTML](#estructura-html)
2. [Sistema de Estilos](#sistema-de-estilos)
3. [JavaScript y Socket.IO](#javascript-y-socketio)
4. [PWA y Service Worker](#pwa-y-service-worker)
5. [Componentes Principales](#componentes-principales)

---

## 📄 Estructura HTML

**Archivo**: [frontend/index.html](frontend/index.html)

### Layout Principal

```html
<!DOCTYPE html>
<html lang="es">
<head>
  <!-- PWA Meta Tags -->
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="theme-color" content="#58a6ff">
  <link rel="manifest" href="/manifest.json">
  <link rel="apple-touch-icon" href="/assets/icon-152.png">
</head>
<body>
  <!-- Header: Logo + Estado del servidor -->
  <header id="header">
    <div class="logo">Fichatech Monitor</div>
    <div class="server-status">
      <span id="status-indicator"></span>
      <span id="status-text">Conectando...</span>
    </div>
  </header>

  <!-- Main Content: Grid de canales/clientes -->
  <main id="channels-container">
    <!-- Canales insertados dinámicamente por JavaScript -->
  </main>

  <!-- Footer: Información de servidor -->
  <footer id="footer">
    <div id="stats"></div>
  </footer>

  <!-- Service Worker para PWA -->
  <script>
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js');
    }
  </script>
  
  <!-- Socket.IO Cliente -->
  <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.5.4/socket.io.min.js"></script>
  
  <!-- Heartbeat Worker (mantiene conexión viva) -->
  <script src="/heartbeat-worker.js"></script>
</body>
</html>
```

### Secciones Principales

#### 1. **Header**
```html
<header>
  <div class="logo-container">
    <h1>🎵 Fichatech Monitor</h1>
    <span id="connection-status" class="status-indicator"></span>
  </div>
  
  <div class="server-info">
    <span id="latency">Latencia: --ms</span>
    <span id="clients-count">Clientes: 0</span>
  </div>
</header>
```

#### 2. **Channels Container**
```html
<main id="channels-container" class="channels-grid">
  <!-- Generado dinámicamente -->
  <!-- Cada canal es un card con controles -->
</main>
```

#### 3. **Channel Card Template**
```html
<div class="channel-card" data-channel-id="0">
  <div class="channel-header">
    <h3 id="ch-name-0">Micrófono Principal</h3>
    <button class="btn-mute" data-channel="0">🔊</button>
  </div>
  
  <div class="channel-body">
    <!-- VU Meter -->
    <div class="vu-meter">
      <div class="vu-bar">
        <div id="vu-bar-0" class="vu-fill"></div>
      </div>
      <span id="vu-db-0">-∞ dB</span>
    </div>
    
    <!-- Slider de Ganancia -->
    <div class="control-group">
      <label>Ganancia</label>
      <input type="range" 
             id="gain-0" 
             class="gain-slider" 
             min="0" max="2" 
             step="0.01" 
             value="1.0">
      <span id="gain-text-0">0.0 dB</span>
    </div>
    
    <!-- Slider de Panorama -->
    <div class="control-group">
      <label>Panorama</label>
      <input type="range" 
             id="pan-0" 
             class="pan-slider" 
             min="-1" max="1" 
             step="0.01" 
             value="0">
      <span id="pan-text-0">Centro</span>
    </div>
  </div>
</div>
```

---

## 🎨 Sistema de Estilos

**Archivo**: [frontend/styles.css](frontend/styles.css)

### Variables CSS Principales
```css
:root {
  /* Colores Tema Oscuro (GitHub Dark) */
  --bg-primary: #0d1117;        /* Fondo principal */
  --bg-secondary: #161b22;      /* Secundario */
  --bg-tertiary: #21262d;       /* Terciario */
  
  --text-primary: #c9d1d9;      /* Texto principal */
  --text-secondary: #8b949e;    /* Texto secundario */
  
  --accent-primary: #58a6ff;    /* Azul primario */
  --accent-danger: #f85149;     /* Rojo (error/mute) */
  --accent-success: #3fb950;    /* Verde (activo) */
  
  --border-color: #30363d;      /* Bordes */
  
  /* Spacing */
  --spacing-xs: 4px;
  --spacing-sm: 8px;
  --spacing-md: 16px;
  --spacing-lg: 24px;
}
```

### Responsive Design
```css
/* Desktop (> 1024px) */
#channels-container {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 20px;
}

/* Tablet (768px - 1024px) */
@media (max-width: 1024px) {
  #channels-container {
    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  }
}

/* Mobile (< 768px) */
@media (max-width: 768px) {
  #channels-container {
    grid-template-columns: 1fr;
  }
  
  .channel-card {
    flex-direction: column;
  }
}
```

### Componentes Estilizados

#### VU Meter
```css
.vu-meter {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 15px;
}

.vu-bar {
  flex: 1;
  height: 20px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  overflow: hidden;
}

.vu-fill {
  height: 100%;
  width: 0%;
  background: linear-gradient(90deg, 
    #3fb950 0%,    /* Verde */
    #d29922 70%,   /* Amarillo */
    #f85149 100%   /* Rojo */
  );
  transition: width 0.05s linear;
}
```

#### Sliders
```css
input[type="range"] {
  width: 100%;
  height: 6px;
  background: var(--bg-tertiary);
  border-radius: 3px;
  outline: none;
  
  /* Thumb (Handle) */
  &::-webkit-slider-thumb {
    appearance: none;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--accent-primary);
    cursor: pointer;
  }
  
  &::-moz-range-thumb {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--accent-primary);
    cursor: pointer;
  }
}
```

---

## 💻 JavaScript y Socket.IO

### Inicialización
```javascript
// Conectar a servidor WebSocket
const socket = io({
  reconnection: true,
  reconnectionDelay: 1000,
  reconnectionDelayMax: 5000,
  reconnectionAttempts: 5
});

// Estructura de datos local
const state = {
  connected: false,
  channels: {},        // {id: {name, gain, pan, mute, rms, peak}}
  clients: {},         // {id: {name, type, status}}
  latency: null,
  serverVersion: null
};
```

### Eventos Socket.IO - Recibir

#### Conectado
```javascript
socket.on('connect', () => {
  state.connected = true;
  updateConnectionStatus('Conectado', true);
  
  // Solicitar estado inicial
  socket.emit('request_full_state');
});
```

#### Desconectado
```javascript
socket.on('disconnect', (reason) => {
  state.connected = false;
  updateConnectionStatus(`Desconectado: ${reason}`, false);
});
```

#### Estado de Canales
```javascript
socket.on('channel_state', (channelsData) => {
  // channelsData = {
  //   0: {name: "Micro 1", gain: 1.0, pan: 0, mute: false},
  //   1: {name: "Micro 2", gain: 0.8, pan: -0.5, mute: false}
  // }
  
  Object.entries(channelsData).forEach(([chId, chData]) => {
    state.channels[chId] = chData;
    updateChannelUI(chId, chData);
  });
});
```

#### VU Meters
```javascript
socket.on('vu_update', (vuData) => {
  // vuData = {
  //   0: {rms: -15.5, peak: -12.0},
  //   1: {rms: -20.0, peak: -18.5}
  // }
  
  Object.entries(vuData).forEach(([chId, {rms, peak}]) => {
    updateVUMeter(chId, rms, peak);
  });
});
```

#### Clientes Conectados
```javascript
socket.on('client_connected', (clientData) => {
  // {client_id: "xyz", device_name: "Android Tab", type: "native"}
  state.clients[clientData.client_id] = clientData;
  renderClientList();
});

socket.on('client_disconnected', (clientId) => {
  delete state.clients[clientId];
  renderClientList();
});
```

### Eventos Socket.IO - Enviar

#### Cambiar Ganancia
```javascript
document.getElementById('gain-0').addEventListener('change', (e) => {
  const gain = parseFloat(e.target.value);
  socket.emit('set_gain', {
    channel: 0,
    gain: gain
  });
});
```

#### Cambiar Panorama
```javascript
document.getElementById('pan-0').addEventListener('change', (e) => {
  const pan = parseFloat(e.target.value);
  socket.emit('set_pan', {
    channel: 0,
    pan: pan
  });
});
```

#### Mute
```javascript
document.querySelector('[data-channel="0"]').addEventListener('click', (e) => {
  if (e.target.classList.contains('btn-mute')) {
    const isMuted = !state.channels[0].mute;
    socket.emit('set_mute', {
      channel: 0,
      mute: isMuted
    });
  }
});
```

#### Reordenar Clientes
```javascript
function saveClientOrder() {
  const order = Array.from(document.querySelectorAll('.client-item'))
    .map(el => el.dataset.clientId);
  
  socket.emit('reorder_clients', { order });
}
```

---

## 📱 PWA y Service Worker

### Manifest.json
**Archivo**: [frontend/manifest.json](frontend/manifest.json)

```json
{
  "name": "Fichatech Audio Monitor",
  "short_name": "Fichatech",
  "description": "Monitoriza y controla audio profesional en tiempo real",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#0d1117",
  "theme_color": "#58a6ff",
  "orientation": "portrait-primary",
  
  "icons": [
    {
      "src": "/assets/icon-72.png",
      "sizes": "72x72",
      "type": "image/png",
      "purpose": "any"
    },
    {
      "src": "/assets/icon-192.png",
      "sizes": "192x192",
      "type": "image/png",
      "purpose": "any"
    },
    {
      "src": "/assets/icon-512.png",
      "sizes": "512x512",
      "type": "image/png",
      "purpose": "any"
    }
  ],
  
  "screenshots": [
    {
      "src": "/assets/screenshot-1.png",
      "sizes": "540x720",
      "type": "image/png"
    }
  ]
}
```

### Service Worker
**Archivo**: [frontend/sw.js](frontend/sw.js)

```javascript
const CACHE_NAME = 'fichatech-v1';
const urlsToCache = [
  '/',
  '/index.html',
  '/styles.css',
  '/manifest.json',
  '/assets/icon-192.png'
];

// Install event
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(urlsToCache);
    })
  );
});

// Fetch event (Network First, Cache Fallback)
self.addEventListener('fetch', (event) => {
  // Para WebSocket, dejar pasar
  if (event.request.url.includes('socket.io')) {
    return;
  }
  
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Cachear respuesta exitosa
        if (response.status === 200) {
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseClone);
          });
        }
        return response;
      })
      .catch(() => {
        // Si falla, usar cache
        return caches.match(event.request);
      })
  );
});
```

### Heartbeat Worker
**Archivo**: [frontend/heartbeat-worker.js](frontend/heartbeat-worker.js)

```javascript
/**
 * Worker que mantiene la conexión viva incluso cuando
 * la pestaña está inactiva (background)
 */

setInterval(() => {
  // Enviar latido al servidor cada 30 segundos
  fetch('/api/heartbeat', { method: 'POST' });
}, 30000);

// Escuchar mensajes del thread principal
self.onmessage = (event) => {
  if (event.data.type === 'ping') {
    self.postMessage({ type: 'pong' });
  }
};
```

---

## 🧩 Componentes Principales

### 1. **Panel de Control de Canal**

```javascript
class ChannelControlPanel {
  constructor(channelId, container) {
    this.channelId = channelId;
    this.container = container;
    this.render();
  }
  
  render() {
    const html = `
      <div class="channel-card" data-channel-id="${this.channelId}">
        <div class="channel-header">
          <h3>${this.getChannelName()}</h3>
          <button class="btn-mute" data-channel="${this.channelId}">🔊</button>
        </div>
        
        <div class="vu-meter">
          <div class="vu-bar">
            <div id="vu-fill-${this.channelId}" class="vu-fill"></div>
          </div>
          <span id="vu-db-${this.channelId}">-∞ dB</span>
        </div>
        
        <div class="control-group">
          <label>Ganancia</label>
          <input type="range" 
                 id="gain-${this.channelId}" 
                 class="gain-slider" 
                 min="0" max="2" step="0.01" value="1">
          <span id="gain-text-${this.channelId}">0 dB</span>
        </div>
        
        <div class="control-group">
          <label>Panorama</label>
          <input type="range" 
                 id="pan-${this.channelId}" 
                 class="pan-slider" 
                 min="-1" max="1" step="0.01" value="0">
          <span id="pan-text-${this.channelId}">Centro</span>
        </div>
      </div>
    `;
    
    this.container.insertAdjacentHTML('beforeend', html);
    this.attachEventListeners();
  }
  
  attachEventListeners() {
    const gainSlider = document.getElementById(`gain-${this.channelId}`);
    const panSlider = document.getElementById(`pan-${this.channelId}`);
    const muteBtn = this.container.querySelector(`[data-channel="${this.channelId}"]`);
    
    gainSlider.addEventListener('input', (e) => {
      socket.emit('set_gain', {
        channel: this.channelId,
        gain: parseFloat(e.target.value)
      });
    });
    
    panSlider.addEventListener('input', (e) => {
      socket.emit('set_pan', {
        channel: this.channelId,
        pan: parseFloat(e.target.value)
      });
    });
    
    muteBtn.addEventListener('click', () => {
      socket.emit('set_mute', {
        channel: this.channelId,
        mute: !state.channels[this.channelId].mute
      });
    });
  }
  
  updateVU(rms, peak) {
    const percentage = this.dbToPercentage(rms);
    const fillEl = document.getElementById(`vu-fill-${this.channelId}`);
    const dbEl = document.getElementById(`vu-db-${this.channelId}`);
    
    fillEl.style.width = `${percentage}%`;
    dbEl.textContent = `${rms.toFixed(1)} dB`;
  }
  
  dbToPercentage(db) {
    // -60dB = 0%, 0dB = 100%
    return Math.max(0, Math.min(100, (db + 60) / 0.6));
  }
}
```

### 2. **Indicador de Conexión**

```javascript
function updateConnectionStatus(message, connected) {
  const indicator = document.getElementById('status-indicator');
  const text = document.getElementById('status-text');
  
  indicator.className = connected ? 'connected' : 'disconnected';
  text.textContent = message;
  
  // Animación de pulso si desconectado
  if (!connected) {
    indicator.classList.add('pulse');
  } else {
    indicator.classList.remove('pulse');
  }
}
```

### 3. **Monitor de Estadísticas**

```javascript
function updateStats() {
  const stats = {
    latency: socket?.io?.engine?.transport?.pollInterval,
    clientCount: Object.keys(state.clients).length,
    channelCount: Object.keys(state.channels).length,
    timestamp: new Date().toLocaleTimeString()
  };
  
  document.getElementById('stats').innerHTML = `
    <span>Latencia: ${stats.latency || '--'}ms</span>
    <span>Clientes: ${stats.clientCount}</span>
    <span>Canales: ${stats.channelCount}</span>
  `;
}

setInterval(updateStats, 1000);
```

---

## 🔌 Flujo de Datos UI

```
Socket.IO Server
    ↓
channel_state event
    ↓
JavaScript recibe datos
    ↓
Actualiza state.channels
    ↓
updateChannelUI() actualiza DOM
    ↓
Usuario ve cambios en tiempo real

---

Usuario ajusta slider
    ↓
Evento 'change' en input
    ↓
JavaScript emite set_gain vía Socket.IO
    ↓
Server recibe y aplica cambio
    ↓
Server broadcast channel_state
    ↓
Todos los clientes web reciben actualización
    ↓
UI actualizada en tiempo real
```

---

## 📱 Experiencia Móvil

- **PWA**: Instalable como app nativa (iOS/Android)
- **Responsive**: Adaptado para pantallas pequeñas
- **Touch-friendly**: Sliders y botones ampliados para touch
- **Offline**: Servido desde cache si pierde conexión
- **Notificaciones**: Push notifications para eventos importantes

