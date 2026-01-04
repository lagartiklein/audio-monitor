# 🔍 DIAGNÓSTICO: Problema de Conexión Android (3 Intentos + Desconexión)

## 🎯 PROBLEMA REPORTADO
- **Síntomas:** Se tarda ~3 intentos para conectar desde Android al servidor
- **Comportamiento:** Una vez que "conecta", se desconecta inmediatamente
- **Patrón:** Necesita reintentar varias veces hasta que funciona

## ⚠️ CAUSAS IDENTIFICADAS

### 1. **TIMEOUT DE SOCKET DESINCRONIZADO** ❌
**Archivo:** [native_server.py](audio_server/native_server.py#L48)
```python
self.socket.settimeout(5.0)  # ⚠️ PROBLEMA 1
self.socket.setblocking(False)  # ⚠️ PROBLEMA 2 (conflictivo con settimeout)
```

**Problema:**
- El socket está configurado como **no-bloqueante** (`setblocking(False)`)
- Pero luego se intenta usar **timeout** (`settimeout(5.0)`)
- Esto causa comportamiento impredecible: el timeout se ignora en sockets no-bloqueantes

### 2. **PROTOCOLO BINARIO SIN SINCRONIZACIÓN INICIAL** ❌
**Archivo:** [native_server.py](audio_server/native_server.py#L546)
```python
header_data = self._recv_exact(client.socket, HEADER_SIZE)
if not header_data: 
    break

magic, version, typeAndFlags, timestamp, payloadLength = struct.unpack('!IHHII', header_data)

if magic != NativeAndroidProtocol.MAGIC_NUMBER:
    consecutive_errors += 1
    if config.DEBUG:
        logger.warning(f"⚠️ Magic inválido #{consecutive_errors} - {client_id[:15]}")

    if consecutive_errors >= 5:
        logger.warning(f"⚠️ Demasiados errores - {client_id[:15]}")
        break

    time.sleep(0.1)
    continue
```

**Problema:**
- Si llega **cualquier byte basura** (WiFi noise, timeouts, etc.), el magic falla
- El servidor **continúa** intentando parsear desde una posición incorrecta
- Después de 5 errores, cierra la conexión completamente
- **NO HAY sincronización**: No busca el magic number nuevamente en el stream

### 3. **HANDSHAKE RACING CONDITION** ⚠️
**Archivo:** [native_server.py](audio_server/native_server.py#L688-L715)
```python
with self.client_lock:
    # Si ya existe, CERRAR el socket viejo
    if persistent_id in self.clients:
        old_client = self.clients[persistent_id]
        
        logger.info(f"🔄 Reconexión detectada: {persistent_id[:15]}")
        logger.info(f"   Cerrando conexión anterior...")
        
        # ✅ CERRAR socket viejo
        try:
            old_client.status = 0
            old_client.close()
        except Exception as e:
            logger.warning(f"⚠️ Error cerrando cliente viejo: {e}")
```

**Problema:**
- Si el handshake llega pero el socket viejo **no está completamente cerrado**, causa conflicto
- El `close()` puede fallar silenciosamente
- Los threads de lectura del cliente viejo **siguen corriendo**

### 4. **RECV_EXACT SIN MANEJO DE ERRORES DE RED** ❌
**Archivo:** [native_server.py](audio_server/native_server.py#L601-L617)
```python
def _recv_exact(self, sock: socket.socket, size: int):
    data = b''
    timeout = 10.0  # ✅ REDUCIDO: 10s (era 60s)
    start = time.time()
    
    while len(data) < size and (time.time() - start) < timeout:
        try:
            chunk = sock.recv(min(size - len(data), 65536))
            if not chunk: 
                return None
            data += chunk
        except socket.timeout: 
            continue
        except:
            return None
    
    return data if len(data) == size else None
```

**Problema:**
- Timeout de 10 segundos es **MUY LARGO** en WiFi inestable
- Si llega un paquete TCP retransmitido, causa delay acumulativo
- No distingue entre timeout real y errores de socket

### 5. **CLIENTE ANDROID: ENVÍO DE HANDSHAKE BLOQUEANTE** ⚠️
**Archivo:** [NativeAudioClient.kt](kotlin%20android/clases/NativeAudioClient.kt#L185-L210)
```kotlin
outputStream = DataOutputStream(socket?.getOutputStream()?.buffered(SOCKET_SNDBUF))

// ...

sendHandshake()  // ⚠️ Envío síncrono
startReaderThread()
startHeartbeat()
```

**Problema:**
- `sendHandshake()` hace envío síncrono
- Si el servidor tarda en responder, el cliente puede timeout mientras espera
- No hay confirmación de que el handshake llegó

### 6. **CLIENTE ANDROID: LÓGICA DE MAGIA DEMASIADO ESTRICTA** ❌
**Archivo:** [NativeAudioClient.kt](kotlin%20android/clases/NativeAudioClient.kt#L481-L490)
```kotlin
if (header.magic != MAGIC_NUMBER) {
    consecutiveMagicErrors++
    if (consecutiveMagicErrors >= maxConsecutiveMagicErrors) {
        handleConnectionLost("Protocolo inválido")
        break
    }
    continue
}
```

**Problema:**
- Solo 3 errores de magic y desconecta completamente
- No intenta **re-sincronizar** el stream
- Una ráfaga de WiFi noise causa desconexión instantánea

---

## 🛠️ SOLUCIONES RECOMENDADAS

### **SOLUCIÓN 1: Sincronización Robusta de Protocolo**
Implementar "frame sync" buscando el MAGIC_NUMBER en el stream:

```python
def _sync_to_magic(sock: socket.socket, timeout: float = 2.0) -> bytes:
    """Buscar MAGIC_NUMBER en el stream con timeout"""
    buffer = b''
    start = time.time()
    
    while time.time() - start < timeout:
        try:
            byte = sock.recv(1)
            if not byte:
                return None
            buffer += byte
            
            # Buscar MAGIC en los últimos 4 bytes
            if len(buffer) >= 4:
                last_4 = buffer[-4:]
                if struct.unpack('!I', last_4)[0] == NativeAndroidProtocol.MAGIC_NUMBER:
                    return buffer[:-4] + last_4  # Retornar con MAGIC al inicio
                
                # Limpiar buffer si crece demasiado
                if len(buffer) > 1000:
                    buffer = buffer[-4:]
        except socket.timeout:
            continue
        except:
            return None
    
    return None
```

### **SOLUCIÓN 2: Configuración de Socket Correcta**
```python
# ✅ CORRECTO:
self.socket.setblocking(True)  # Bloqueante
self.socket.settimeout(5.0)    # Timeout de 5s
# ✅ O ALTERNATIVA:
self.socket.setblocking(False)  # No-bloqueante
# Usar select() para esperar datos, no settimeout()
```

### **SOLUCIÓN 3: Timeout Adaptativo**
```python
def _recv_exact(self, sock: socket.socket, size: int, timeout: float = 2.0):
    """Timeout más agresivo y adaptativo"""
    data = b''
    start = time.time()
    sock.settimeout(0.5)  # Timeout de socket más corto
    
    while len(data) < size and (time.time() - start) < timeout:
        try:
            chunk = sock.recv(min(size - len(data), 65536))
            if not chunk: 
                return None
            data += chunk
        except socket.timeout: 
            # OK, intentar de nuevo
            continue
        except:
            return None
    
    return data if len(data) == size else None
```

### **SOLUCIÓN 4: Heartbeat más Agresivo**
Aumentar frecuencia de heartbeat para detectar desconexiones rápido:

```python
# config.py
HEARTBEAT_INTERVAL_MS = 3000   # Cada 3 segundos (no 5)
HEARTBEAT_TIMEOUT_MS = 9000    # Timeout después de 9 segundos
CLIENT_ALIVE_TIMEOUT = 15.0    # Reducido de 30s
```

### **SOLUCIÓN 5: Limpieza Agresiva de Recursos**
```python
def close(self):
    """Cerrar cliente correctamente"""
    self.send_running = False
    self.status = 0
    
    # Cerrar streams primero
    try:
        self.socket.shutdown(socket.SHUT_RDWR)
    except:
        pass
    
    try:
        self.socket.close()
    except:
        pass
    
    self.socket = None
```

---

## 📊 TABLA DE CAMBIOS RECOMENDADOS

| Problema | Ubicación | Cambio | Impacto |
|----------|-----------|--------|---------|
| Socket blocking/timeout conflictivo | `native_server.py:48` | `setblocking(True)` + `settimeout(5.0)` | ✅ Elimina race conditions |
| Magic sync ausente | `native_server.py:546-562` | Implementar `_sync_to_magic()` | ✅ Resincroniza automáticamente |
| Timeout recv muy largo | `native_server.py:601-617` | Reducir a 1-2s | ✅ Detección rápida |
| Heartbeat muy lento | `config.py` | 3s en lugar de 5s | ✅ Detecta muertes 40% más rápido |
| Errores magic demasiado estrictos | `NativeAudioClient.kt:483` | Aumentar a 10 errores | ⚠️ Temporal |
| Close no es robusto | `native_server.py:200+` | Implementar `close()` completo | ✅ Limpieza garantizada |

---

## ✅ PRIORIDAD DE IMPLEMENTACIÓN

1. **CRÍTICO (Implementar primero):**
   - [ ] Sincronización de protocolo robusta
   - [ ] Configuración correcta de socket
   - [ ] Timeout adaptativo

2. **ALTA (Implementar después):**
   - [ ] Limpieza agresiva de recursos
   - [ ] Heartbeat más rápido
   
3. **MEDIA (Optimizar después):**
   - [ ] Métricas de diagnóstico
   - [ ] Logging mejorado
