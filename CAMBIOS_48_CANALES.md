# Cambios: Sistema de 48 Canales por Defecto con Mapeo Automático

## Resumen
Se ha implementado un sistema que muestra siempre 48 canales en la interfaz, permitiendo que las interfaces físicas conectadas se mapeen automáticamente a estos canales según su cantidad de inputs.

## Cambios Realizados

### 1. **config.py**
- ✅ Agregado: `DEFAULT_NUM_CHANNELS = 48`
- Los canales son siempre visibles, incluso si el dispositivo físico tiene menos

### 2. **main.py** 
- ✅ Modificado: `AudioServerApp.start_server()`
- Ahora fuerza mínimo `config.DEFAULT_NUM_CHANNELS` canales
- Si el dispositivo captura menos de 48, se rellenan con 0
- Canales sin audio real simplemente no reciben datos

### 3. **audio_server/channel_manager.py**
- ✅ Nuevos atributos en `__init__`:
  - `device_channel_map`: Mapeo de dispositivos UUID a rangos de canales lógicos
  - `next_available_channel`: Contador para asignación secuencial

- ✅ Nuevos métodos:
  - `register_device_to_channels()`: Asigna automáticamente canales a un dispositivo
    - Primera interfaz con 8 canales → Canales 0-7
    - Segunda interfaz con 16 canales → Canales 8-23
    - Etc.
  
  - `get_device_channel_map()`: Obtiene el mapeo de un dispositivo
  
  - `get_operational_channels()`: Retorna el conjunto de canales que tienen dispositivos asignados

### 4. **audio_server/websocket_server.py**
- ✅ Modificado: Event `connect`
- Ahora envía `operational_channels` en el mensaje `device_info`
- Lista de canales que tienen interfaces físicas asignadas

### 5. **audio_server/native_server.py**
- ✅ Modificado: `_handle_control_message()` para 'handshake'
- Detecta conexión vs reconexión temprano
- Llama a `register_device_to_channels()` solo en primera conexión
- Mapea automáticamente dispositivos Android a canales lógicos

### 6. **frontend/index.html**
- ✅ Nuevos estilos CSS:
  - `.channel-strip.operational`: Clase para canales con dispositivos
  - Borde verde izquierdo de 4px
  - Sombra interna sutil
  - Número de canal resaltado en verde
  
- ✅ Modificado: `renderMixer()`
- Ahora verifica `operational_channels` del `deviceInfo`
- Aplica clase `operational` a canales que tienen dispositivos asignados

## Comportamiento

### Flujo Típico:
1. Servidor inicia con 48 canales siempre (incluso si el dispositivo tiene menos)
2. Cliente Android se conecta (8 canales) → Se mapea a canales 0-7
3. Cliente Android se conecta (16 canales) → Se mapea a canales 8-23
4. Cliente Android se conecta (4 canales) → Se mapea a canales 24-27
5. UI muestra todos los 48 canales
6. Canales 0-27 aparecen en VERDE BRILLANTE (operacionales)
7. Canales 28-47 aparecen en GRIS OSCURO (sin dispositivo)

### Persistencia:
- Mapeo de dispositivos NO persiste entre reinicios
- Se recalcula cada vez que el servidor inicia
- Esto permite flexibilidad en desconexión/reconexión

### Sin Interferencia:
- ✅ Control de canales funciona normalmente
- ✅ Clientes pueden seguir subscribiéndose a cualquier rango
- ✅ El audio solo fluye desde canales mapeados
- ✅ Canales vacíos no reciben audio ni causan errores

## Pruebas Recomendadas

1. Conectar interfaz con menos de 48 canales
   - Verificar que aparecen 48 canales en la UI
   
2. Conectar cliente Android/nativo
   - Verificar que se mapea automáticamente
   - Verificar que aparecen en color verde en la UI
   
3. Conectar múltiples clientes
   - Verificar que se mapean secuencialmente
   - Verificar conteo correcto de canales

4. Cambiar clientes (desconectar/reconectar)
   - Verificar que remapeo funciona correctamente

5. Funcionalidad existente
   - Verificar que mezcla de canales funciona
   - Verificar que ganancia/pan/mute funcionan
   - Verificar que audio fluye correctamente
