# GUÍA DE INTEGRACIÓN - SISTEMA DE IDENTIFICACIÓN PERSISTENTE

## 📋 Resumen del cambio

Se ha implementado un sistema de registro de dispositivos (`DeviceRegistry`) que permite identificar cada cliente de forma única y persistente, independientemente de cambios de IP, red o sesión.

---

## 🔧 Cambios implementados

### 1. **Nuevo archivo: `audio_server/device_registry.py`**

Clase principal: `DeviceRegistry` que gestiona:
- Registro único de dispositivos por UUID
- Persistencia en `config/devices.json`
- Limpieza automática de dispositivos expirados
- Mapeo de device_uuid → configuración

**Uso:**
```python
from audio_server.device_registry import get_device_registry

registry = get_device_registry()

# Registrar dispositivo
registry.register_device(
    device_uuid="550e8400-e29b-41d4-a716-446655440000",
    device_info={
        'type': 'web',
        'name': 'Mi Monitor',
        'primary_ip': '192.168.1.100',
        'user_agent': 'Mozilla/5.0...'
    }
)

# Obtener dispositivo
device = registry.get_device("550e8400-e29b-41d4-a716-446655440000")

# Guardar configuración
registry.update_configuration(device_uuid, {
    'channels': [0, 1, 2],
    'gains': {0: 1.0, 1: 0.8},
    'pans': {0: 0.0, 1: -0.5}
})
```

---

### 2. **Modificaciones en: `audio_server/channel_manager.py`**

**Cambios:**
- ✅ Agregado `device_uuid` al constructor de ChannelManager
- ✅ Agregado `device_client_map` para mapeo device_uuid → client_id
- ✅ Nuevo método `set_device_registry()`
- ✅ Nuevo método `get_client_by_device_uuid()`
- ✅ Actualizado `subscribe_client()` para aceptar `device_uuid`
- ✅ Actualizado `unsubscribe_client()` para limpiar mapeos

**Ejemplo:**
```python
# En channel_manager
channel_manager.subscribe_client(
    client_id='socket_123',
    channels=[0, 1, 2],
    gains={0: 1.0},
    pans={0: 0.0},
    client_type='web',
    device_uuid='550e8400-e29b-41d4-a716-446655440000'  # ✅ NUEVO
)

# Buscar cliente por device
client_id = channel_manager.get_client_by_device_uuid(device_uuid)
```

---

### 3. **Modificaciones en: `main.py`**

**Cambios:**
- ✅ Import de `init_device_registry`
- ✅ Inicialización del registry en `start_server()`
- ✅ Inyección del registry en channel_manager

**Código agregado:**
```python
# Inicializar Device Registry
device_registry = init_device_registry(
    persistence_file=os.path.join(os.path.dirname(__file__), "config", "devices.json")
)

# Inyectar en channel_manager
channel_manager.set_device_registry(device_registry)
```

---

## 🌐 Próximas fases: Integración con clientes

### **Fase 2: Native Server (Android)**

Modificar `audio_server/native_server.py`:

```python
def _handle_control_message(self, client: NativeClient, message: dict):
    if msg_type == 'handshake':
        # ✅ NUEVO: Leer device_uuid del handshake
        device_uuid = message.get('device_uuid')  # Enviado por app Android
        device_info = message.get('device_info')
        
        # Registrar dispositivo
        if device_uuid:
            device_registry.register_device(device_uuid, {
                'type': 'android',
                'mac_address': device_info.get('mac_address'),
                'primary_ip': client.address[0],
                'os': 'Android',
                'hostname': device_info.get('hostname')
            })
            
            # Restaurar configuración anterior si existe
            config = device_registry.get_configuration(device_uuid)
            if config:
                channel_manager.subscribe_client(
                    client.id,
                    config.get('channels', []),
                    config.get('gains', {}),
                    config.get('pans', {}),
                    client_type='native',
                    device_uuid=device_uuid
                )
```

---

### **Fase 3: WebSocket Server (Web)**

Modificar `audio_server/websocket_server.py`:

```python
@socketio.on('connect')
def handle_connect():
    client_id = request.sid
    device_uuid = request.args.get('device_uuid')  # ✅ Desde query string
    
    if not device_uuid:
        # Generar nuevo UUID si no existe
        device_uuid = str(uuid.uuid4())
        emit('device_uuid', {'uuid': device_uuid})
    
    # Registrar dispositivo
    device_registry.register_device(device_uuid, {
        'type': 'web',
        'primary_ip': request.remote_addr,
        'user_agent': request.headers.get('User-Agent'),
        'hostname': request.environ.get('REMOTE_HOST')
    })
    
    # Restaurar configuración anterior
    config = device_registry.get_configuration(device_uuid)
    if config:
        channel_manager.subscribe_client(
            client_id,
            config.get('channels', []),
            config.get('gains', {}),
            config.get('pans', {}),
            client_type='web',
            device_uuid=device_uuid
        )
```

---

### **Fase 4: Frontend (JavaScript)**

Modificar `frontend/index.html`:

```javascript
// 1. Generar/recuperar UUID del dispositivo
function getDeviceUUID() {
    let uuid = localStorage.getItem('device_uuid');
    
    if (!uuid) {
        uuid = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            var r = Math.random() * 16 | 0;
            var v = c == 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
        localStorage.setItem('device_uuid', uuid);
    }
    
    return uuid;
}

// 2. Conectar con device_uuid
const socket = io('/', {
    query: {
        device_uuid: getDeviceUUID()  // ✅ Enviar UUID
    }
});

// 3. Escuchar si servidor genera nuevo UUID
socket.on('device_uuid', (data) => {
    localStorage.setItem('device_uuid', data.uuid);
});

// 4. Restaurar configuración al conectar
socket.on('connect', () => {
    // Emit auto-subscribe con device_uuid
    fetch(`/api/device/${getDeviceUUID()}/config`)
        .then(r => r.json())
        .then(config => {
            socket.emit('subscribe', {
                channels: config.channels,
                gains: config.gains,
                pans: config.pans
            });
        });
});
```

---

## 📊 Estructura de archivos generados

```
config/
└── devices.json          # Persistencia de dispositivos
    
    Ejemplo:
    {
        "550e8400-e29b-41d4-a716-446655440000": {
            "uuid": "550e8400-e29b-41d4-a716-446655440000",
            "type": "web",
            "name": "Mi Monitor - Habitación",
            "mac_address": null,
            "primary_ip": "192.168.1.100",
            "device_info": {
                "type": "web",
                "primary_ip": "192.168.1.100",
                "user_agent": "Mozilla/5.0..."
            },
            "first_seen": 1735849200.123,
            "last_seen": 1735849326.456,
            "reconnections": 5,
            "configuration": {
                "channels": [0, 1, 2, 3],
                "gains": {0: 1.0, 1: 0.8, 2: 0.9, 3: 1.2},
                "pans": {0: 0.0, 1: -0.5, 2: 0.5, 3: 0.0},
                "master_gain": 1.0
            },
            "tags": ["habitacion", "monitor-principal"],
            "active": true
        }
    }
```

---

## 🔄 Flujo completo (Fase 4)

```
┌─ CLIENTE WEB (Fase 4) ───────────────────────────┐
│                                                     │
│ 1️⃣ Abre navegador, localStorage sin UUID         │
│ 2️⃣ JavaScript genera UUID: uuid-123-456         │
│ 3️⃣ localStorage.setItem('device_uuid', uuid)    │
│ 4️⃣ Conecta: io('/?device_uuid=uuid-123-456')   │
│ 5️⃣ Servidor recibe en query parameter ✅        │
│ 6️⃣ registry.register_device(uuid, info)         │
│ 7️⃣ Restaura config anterior (si existe)        │
│ 8️⃣ Se suscribe a canales guardados             │
│ 9️⃣ Estado se guarda en registry ✅             │
│                                                     │
│ 🔄 CAMBIO DE RED (WiFi → móvil)               │
│ 1️⃣ localStorage AÚN tiene uuid-123-456         │
│ 2️⃣ Reconecta con MISMO UUID ✅                 │
│ 3️⃣ Servidor encuentra dispositivo               │
│ 4️⃣ Restaura MISMA configuración ✅             │
│ 5️⃣ NO CREA NUEVO CLIENTE ✅✅✅                │
│                                                     │
└─────────────────────────────────────────────────────┘

┌─ CLIENTE NATIVO (Fase 2) ─────────────────────┐
│                                                 │
│ 1️⃣ App genera UUID en SharedPreferences      │
│ 2️⃣ Conecta a servidor RF                     │
│ 3️⃣ Envía handshake con device_uuid           │
│ 4️⃣ Servidor recibe, registry.register()      │
│ 5️⃣ Restaura config, se suscribe ✅           │
│ 6️⃣ Guarda config en registry ✅              │
│                                                 │
│ 🔄 APP REINICIA O RED CAMBIA                │
│ 1️⃣ UUID AÚN está en SharedPreferences       │
│ 2️⃣ Reconecta, handshake con MISMO UUID      │
│ 3️⃣ Servidor encuentra dispositivo ✅        │
│ 4️⃣ Restaura MISMA config ✅                 │
│ 5️⃣ NO HAY PÉRDIDA DE CONFIGURACIÓN ✅✅     │
│                                                 │
└─────────────────────────────────────────────────┘
```

---

## ✅ Beneficios del sistema

| Beneficio | Antes | Después |
|-----------|-------|---------|
| **Cambio de IP** | ❌ Nuevo cliente | ✅ Mismo dispositivo |
| **Cambio de red** | ❌ Pierde config | ✅ Restaura config |
| **Reinicio de app** | ❌ Nuevo cliente | ✅ Mismo dispositivo |
| **Persistencia** | 5 minutos | **7 días** |
| **Múltiples dispositivos** | Imposible | ✅ Diferenciados por UUID |
| **Identificación** | IP + User-Agent | **UUID único** |
| **Sincronización** | No existe | ✅ Base para sincro |

---

## 🚀 Cronograma

| Fase | Componente | Duración | Estado |
|------|-----------|----------|--------|
| **1** | Device Registry | ✅ COMPLETADA | ✅ |
| **2** | Native Server | Semana 1 | ⏳ |
| **3** | WebSocket Server | Semana 1 | ⏳ |
| **4** | Frontend JavaScript | Semana 1 | ⏳ |
| **5** | Tests e integración | Semana 2 | ⏳ |

---

## 📝 Notas importantes

1. **Formato de UUID:** Se usa UUID v4 estándar (36 caracteres)
2. **Persistencia:** Archivos JSON en `config/devices.json`
3. **Limpieza automática:** Cada 1 hora, elimina dispositivos no vistos en 7 días
4. **Máximo de dispositivos:** 500 simultáneos (configurable)
5. **Thread-safe:** Usa locks para acceso concurrente
6. **Backward compatible:** No rompe código existente

