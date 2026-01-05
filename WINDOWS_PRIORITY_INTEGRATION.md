# 🔧 Integración: Prioridad en Windows para Audio Tiempo Real

## Cambios Realizados

### Archivo: `audio_server/audio_capture.py`

1. **Nuevo método: `_set_windows_priority()`** (línea ~135)
   - Eleva la prioridad del proceso Python a `HIGH_PRIORITY_CLASS` en Windows
   - Usa APIs de Windows (kernel32) mediante `ctypes`
   - Manejo robusto de errores

2. **Actualización: `set_realtime_priority()`** (línea ~134)
   - Ahora llama a `_set_windows_priority()` en Windows
   - Funciona en paralelo con las implementaciones en Linux y macOS

## Cómo Funciona

```
┌─────────────────────────────────────────────────────┐
│ AudioCapture.__init__()                             │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
        AudioCapture.start_capture()
                     │
                     ▼
        AudioCapture.set_realtime_priority()
                     │
        ┌────────────┼────────────┐
        │            │            │
       Linux      macOS        Windows
        │            │            │
        ▼            ▼            ▼
    SCHED_FIFO   setpriority  _set_windows_priority()
    (RT)         -20          (HIGH_PRIORITY_CLASS)
```

## Detalles de Windows

**`_set_windows_priority()` hace lo siguiente:**
1. Obtiene el PID actual del proceso Python
2. Abre un handle al proceso con `OpenProcess()`
3. Establece `HIGH_PRIORITY_CLASS` (0x80)
4. Cierra el handle

**Constantes usadas:**
- `PROCESS_SET_INFORMATION = 0x0200` (permiso necesario)
- `HIGH_PRIORITY_CLASS = 0x00000080` (prioridad ALTA - recomendado para audio)
- `REALTIME_PRIORITY_CLASS = 0x00000100` (no usado; muy agresivo)

## Logs Esperados

Al iniciar el servidor, verás:
```
[RF] ✅ Prioridad ALTA establecida (Windows - HIGH_PRIORITY_CLASS)
```

O si hay error:
```
[RF] ⚠️ Error estableciendo prioridad Windows: <error>
```

## Beneficios

| Aspecto | Antes | Después |
|--------|-------|---------|
| **Prioridad Windows** | Normal (20) | ALTA (-7) |
| **Latencia de captura** | Variable, puede sufrir interrupciones | Consistente |
| **CPU scheduling** | Compartido con otras tareas | Preferencia para audio |
| **Estabilidad** | Fluctúa con carga del sistema | Más estable |

## Requisitos

- **Windows 7+** (todo moderno)
- **No requiere privilegios administrativos** (HIGH_PRIORITY_CLASS es accesible)
- **Seguro**: No usa REALTIME_PRIORITY_CLASS (que podría freezear el sistema)

## Testing

Para ver el impacto en tiempo real:

1. Abre **Task Manager** (Ctrl+Shift+Esc)
2. Ve a **Detalles** → busca `python.exe` (tu proceso)
3. Click derecho → **Establecer prioridad**
4. Sin este cambio verías: `Normal`
5. Con este cambio debería estar: `Alta`

## Rollback

Si quieres deshacer:
1. Comenta la línea `self._set_windows_priority()` en `set_realtime_priority()`
2. Comenta el método `_set_windows_priority()`

## Compatibilidad

- ✅ Windows (XP+)
- ✅ Linux (SCHED_FIFO)
- ✅ macOS (setpriority)
- ✅ Falla gracefully si los permisos no lo permiten
