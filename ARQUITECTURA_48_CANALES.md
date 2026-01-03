# DIAGRAMA: Sistema de 48 Canales con Mapeo Automático

## Arquitectura General

```
┌─────────────────────────────────────────────────────────────────┐
│                     SERVIDOR AUDIO (Python)                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ✅ NUEVA CARACTERÍSTICA: Siempre 48 canales                   │
│                                                                  │
│  config.DEFAULT_NUM_CHANNELS = 48                              │
│         ↓                                                        │
│  main.py: num_channels = max(device_channels, 48)              │
│         ↓                                                        │
│  ChannelManager(48)  ← Siempre 48 canales                       │
│         ↓                                                        │
│  ┌─────────────────────────────────────────────────────┐        │
│  │  device_channel_map: Mapeo automático de interfaces │        │
│  │  ┌────────────────────────────────────────────────┐ │        │
│  │  │ device-001 (Android, 8ch)  → [0-7]  ✅ Verde  │ │        │
│  │  │ device-002 (Android, 16ch) → [8-23] ✅ Verde  │ │        │
│  │  │ device-003 (Android, 8ch)  → [24-31]✅ Verde  │ │        │
│  │  │ [32-47] ← Sin dispositivo   ⚫ Gris             │ │        │
│  │  └────────────────────────────────────────────────┘ │        │
│  └─────────────────────────────────────────────────────┘        │
│         ↓                                                        │
│  WebSocket Server                                               │
│  └─ emit('device_info') {                                       │
│     channels: 48,                                               │
│     operational_channels: [0,1,2,...,31]  ← NUEVO              │
│  }                                                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
           ↑                          ↑
           │                          │
    ┌──────┴──────┐        ┌─────────┴────────┐
    │             │        │                  │
    ▼             ▼        ▼                  ▼
 [WEB UI]    [Android A]  [Android B]  [Otros dispositivos]
  Chrome      8 Canales   16 Canales    (Futuros)
```

## Flujo de Mapeo de Dispositivos

```
1️⃣  Servidor inicia
    └─ ChannelManager(48)
       ├─ device_channel_map = {}
       └─ next_available_channel = 0

2️⃣  Android A conecta (8 canales)
    ├─ handshake recibido (num_channels=8)
    ├─ register_device_to_channels("uuid-A", 8)
    │  ├─ Calcula: start=0, num=8
    │  ├─ Actualiza: next_available_channel=8
    │  └─ Guarda: device_channel_map["uuid-A"] = {start:0, num:8, operacional:true}
    └─ device_info.operational_channels = [0,1,2,3,4,5,6,7]

3️⃣  Android B conecta (16 canales)
    ├─ handshake recibido (num_channels=16)
    ├─ register_device_to_channels("uuid-B", 16)
    │  ├─ Calcula: start=8, num=16
    │  ├─ Actualiza: next_available_channel=24
    │  └─ Guarda: device_channel_map["uuid-B"] = {start:8, num:16, operacional:true}
    └─ device_info.operational_channels = [0,1,2,...,23]

4️⃣  Android A desconecta y reconecta
    ├─ handshake recibido (num_channels=8)
    ├─ is_reconnection = true → NO llamar register_device_to_channels
    └─ Mantiene mapeo anterior: [0-7]
```

## Visualización en UI

```
╔════════════════════════════════════════════════════════════════╗
║              FICHATECH MONITOR - CONTROL CENTER                ║
║════════════════════════════════════════════════════════════════║
║ Dispositivo: Audio Interface RF | 48 Canales                  ║
╠════════════════════════════════════════════════════════════════╣
║                                                                 ║
║  ┌─ CH 1 ─┐  ┌─ CH 2 ─┐  ┌─ CH 3 ─┐  ┌─ CH 4 ─┐              ║
║  │ ═══════ │  │ ═══════ │  │ ═══════ │  │ ═══════ │  ◄─ Verde  ║
║  │ [ON] S  │  │ [ON] S  │  │ [ON] S  │  │ [ON] S  │     Operacional
║  │  PFL    │  │  PFL    │  │  PFL    │  │  PFL    │     (con audio)
║  └─────────┘  └─────────┘  └─────────┘  └─────────┘              ║
║                                                                 ║
║  ┌─ CH 5 ─┐  ┌─ CH 6 ─┐  ┌─ CH 7 ─┐  ┌─ CH 8 ─┐              ║
║  │ ═══════ │  │ ═══════ │  │ ═══════ │  │ ═══════ │  ◄─ Verde  ║
║  │ [ON] S  │  │ [ON] S  │  │ [ON] S  │  │ [ON] S  │     Operacional
║  │  PFL    │  │  PFL    │  │  PFL    │  │  PFL    │              ║
║  └─────────┘  └─────────┘  └─────────┘  └─────────┘              ║
║                                                                 ║
║  ┌─ CH 9 ─┐  ┌─ CH 10─┐  ┌─ CH 11─┐  ┌─ CH 12─┐              ║
║  │ ═══════ │  │ ═══════ │  │ ═══════ │  │ ═══════ │  ◄─ Verde  ║
║  │ [ON] S  │  │ [ON] S  │  │ [ON] S  │  │ [ON] S  │     Operacional
║  │  PFL    │  │  PFL    │  │  PFL    │  │  PFL    │     (Android B)
║  └─────────┘  └─────────┘  └─────────┘  └─────────┘              ║
║                                                                 ║
║  ... [CH 13 a CH 32]                                           ║
║                                                                 ║
║  ┌─ CH 33─┐  ┌─ CH 34─┐  ┌─ CH 35─┐  ┌─ CH 36─┐              ║
║  │        │  │        │  │        │  │        │  ◄─ Gris      ║
║  │ [OFF]S │  │ [OFF]S │  │ [OFF]S │  │ [OFF]S │     Sin audio
║  │  PFL    │  │  PFL    │  │  PFL    │  │  PFL    │     (vacío)
║  └─────────┘  └─────────┘  └─────────┘  └─────────┘              ║
║                                                                 ║
║  ... [CH 37 a CH 48]                                           ║
║                                                                 ║
║════════════════════════════════════════════════════════════════║
```

## Tabla de Estados

| Rango | Canales | Dispositivo | Color | Audio | Notas |
|-------|---------|-------------|-------|-------|-------|
| 0-7 | 8 | Android A | Verde ✅ | ✓ Sí | Primer dispositivo |
| 8-23 | 16 | Android B | Verde ✅ | ✓ Sí | Segundo dispositivo |
| 24-47 | 24 | Vacío | Gris ⚫ | ✗ No | Reservados pero sin audio |

## Cambios Compatibilidad

```
✅ SIN CAMBIOS:
   - Lógica de mezcla de canales
   - Control de ganancia/pan/mute
   - Suscripción de clientes web
   - Restauración de configuración
   - Auto-reconexión de dispositivos

⚠️  CAMBIOS VISUALES SOLAMENTE:
   - 48 canales siempre visibles
   - Canales operacionales resaltados
   - Canales vacíos en gris

🔧 NUEVOS MÉTODOS (no interfieren):
   - register_device_to_channels()
   - get_operational_channels()
   - get_device_channel_map()
```

## Pseudo-código: Flujo Completo

```python
# 1. Servidor inicia
num_channels = max(device_channels, DEFAULT_NUM_CHANNELS=48)
channel_manager = ChannelManager(num_channels=48)

# 2. Cliente Android se conecta
client.num_channels = 8  # Del handshake
device_mapping = channel_manager.register_device_to_channels(
    device_uuid="android-uuid-123",
    physical_channels=8
)
# Result: device_mapping = {
#   'start_channel': 0,
#   'num_channels': 8,
#   'physical_channels': 8,
#   'operacional': True
# }

# 3. Web client se conecta
device_info = {
    'channels': 48,  # SIEMPRE 48
    'operational_channels': [0,1,2,3,4,5,6,7]  # NUEVO
}
emit('device_info', device_info)

# 4. Frontend renderiza
for (let i = 0; i < 48; i++) {
    const isOperational = operational_channels.includes(i);
    if (isOperational) {
        strip.classList.add('operational');  // Verde brillante
    }
}
```
