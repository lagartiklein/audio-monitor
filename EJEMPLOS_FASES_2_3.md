# EJEMPLOS DE CÓDIGO - Fases 2 y 3

## 📱 FASE 2: Native Server (Android)

### Archivo: `audio_server/native_server.py`

**Cambios en método `_handle_control_message`:**

```python
def _handle_control_message(self, client: NativeClient, message: dict):
    msg_type = message.get('type', '')

    if msg_type == 'handshake':
        # ✅ NUEVO: Obtener device_uuid del handshake
        device_uuid = message.get('device_uuid')
        device_info = message.get('device_info', {})

        if not device_uuid:
            logger.error(f"❌ Handshake sin device_uuid desde {client.address}")
            return

        # ✅ Buscar dispositivo existente
        is_reconnection = False
        existing_device = None
        
        if self.channel_manager.device_registry:
            existing_device = self.channel_manager.device_registry.get_device(device_uuid)
            
            if existing_device:
                is_reconnection = True
                logger.info(f"🔄 RECONEXIÓN detectada: {device_uuid[:12]}")
                logger.info(f"   Reconexiones previas: {existing_device.get('reconnections', 0)}")

        # ✅ Registrar/actualizar dispositivo
        if self.channel_manager.device_registry:
            self.channel_manager.device_registry.register_device(
                device_uuid,
                {
                    'type': 'android',
                    'name': device_info.get('device_name', f'Android-{device_uuid[:8]}'),
                    'primary_ip': client.address[0],
                    'mac_address': device_info.get('mac_address'),
                    'os': 'Android',
                    'hostname': device_info.get('hostname'),
                    'app_version': device_info.get('app_version'),
                    'device_model': device_info.get('device_model')
                }
            )
            
            logger.info(f"✅ Dispositivo registrado/actualizado: {device_uuid[:12]}")

        # ✅ Actualizar cliente con device_uuid
        client.device_uuid = device_uuid
        client.persistent_id = device_uuid
        client.rf_mode = message.get('rf_mode', False)
        client.persistent = message.get('persistent', False)
        client.auto_reconnect = message.get('auto_reconnect', False)

        # Cambiar ID del cliente
        persistent_id = device_uuid
        is_reconnection_old = False
        old_temp_id = client.id

        with self.client_lock:
            # Si ya existe un cliente con este device_uuid, cerrar el viejo
            if persistent_id in self.clients and persistent_id != old_temp_id:
                old_client = self.clients[persistent_id]
                is_reconnection_old = True
                
                logger.info(f"   Cerrando conexión anterior...")
                try:
                    old_client.status = 0
                    old_client.close()
                except Exception as e:
                    logger.warning(f"⚠️ Error cerrando cliente viejo: {e}")

            # Actualizar diccionario
            if old_temp_id != persistent_id and old_temp_id in self.clients:
                del self.clients[old_temp_id]

            # Agregar con nuevo ID
            client.id = persistent_id
            self.clients[persistent_id] = client

        logger.info(f"✅ ID actualizado: {old_temp_id[:25]} → {persistent_id[:15]}")

        # ✅ RESTAURAR CONFIGURACIÓN SI EXISTE
        restored_config = None
        if self.channel_manager.device_registry:
            restored_config = self.channel_manager.device_registry.get_configuration(device_uuid)
        
        if restored_config and restored_config.get('channels'):
            logger.info(f"💾 Restaurando configuración para {device_uuid[:12]}:")
            logger.info(f"   Canales: {restored_config.get('channels')}")
            logger.info(f"   Ganancia master: {restored_config.get('master_gain', 1.0)}")
            
            # Suscribir con configuración anterior
            self.channel_manager.subscribe_client(
                persistent_id,
                restored_config.get('channels', []),
                gains=restored_config.get('gains', {}),
                pans=restored_config.get('pans', {}),
                client_type="native",
                device_uuid=device_uuid  # ✅ NUEVO
            )
            
            # Aplicar otras configuraciones
            if restored_config.get('mutes'):
                self.channel_manager.subscriptions[persistent_id]['mutes'] = restored_config['mutes']
            if restored_config.get('solos'):
                self.channel_manager.subscriptions[persistent_id]['solos'] = set(restored_config['solos'])
            if restored_config.get('master_gain'):
                self.channel_manager.subscriptions[persistent_id]['master_gain'] = restored_config['master_gain']
        else:
            # Suscripción normal
            self.channel_manager.subscribe_client(
                persistent_id,
                [],  # Sin canales predefinidos para Android
                client_type="native",
                device_uuid=device_uuid  # ✅ NUEVO
            )

        logger.info(f"🤝 {persistent_id[:15]} HANDSHAKE OK:")
        logger.info(f"   Tipo: Android")
        logger.info(f"   Reconexión: {'SÍ' if is_reconnection else 'NO'}")
        logger.info(f"   Auto-reconexión: {'ENABLED' if client.auto_reconnect else 'disabled'}")
        logger.info(f"   Config restaurada: {'SÍ' if restored_config else 'NO (nueva suscripción)'}")

        # ✅ Guardar estado de inicio en registry
        if self.channel_manager.device_registry:
            subscription = self.channel_manager.subscriptions.get(persistent_id, {})
            self.channel_manager.device_registry.update_configuration(
                device_uuid,
                {
                    'channels': subscription.get('channels', []),
                    'gains': subscription.get('gains', {}),
                    'pans': subscription.get('pans', {}),
                    'mutes': subscription.get('mutes', {}),
                    'solos': list(subscription.get('solos', set())),
                    'master_gain': subscription.get('master_gain', 1.0)
                }
            )

    # ✅ RESTO DE MENSAJES...
    elif msg_type == 'subscribe':
        # ... código existente ...
        # ✅ AGREGAR AL FINAL: Guardar configuración
        if hasattr(client, 'device_uuid') and client.device_uuid:
            if self.channel_manager.device_registry:
                subscription = self.channel_manager.subscriptions.get(client.id, {})
                self.channel_manager.device_registry.update_configuration(
                    client.device_uuid,
                    {
                        'channels': subscription.get('channels', []),
                        'gains': subscription.get('gains', {}),
                        'pans': subscription.get('pans', {}),
                        'mutes': subscription.get('mutes', {}),
                        'solos': list(subscription.get('solos', set())),
                        'master_gain': subscription.get('master_gain', 1.0)
                    }
                )

    elif msg_type == 'update_mix':
        # ... código existente ...
        # ✅ AGREGAR AL FINAL: Guardar configuración actualizada
        if hasattr(client, 'device_uuid') and client.device_uuid:
            if self.channel_manager.device_registry:
                subscription = self.channel_manager.subscriptions.get(client.id, {})
                self.channel_manager.device_registry.update_configuration(
                    client.device_uuid,
                    {
                        'channels': subscription.get('channels', []),
                        'gains': subscription.get('gains', {}),
                        'pans': subscription.get('pans', {}),
                        'mutes': subscription.get('mutes', {}),
                        'solos': list(subscription.get('solos', set())),
                        'master_gain': subscription.get('master_gain', 1.0)
                    }
                )
```

---

## 🌐 FASE 3: WebSocket Server (Web)

### Archivo: `audio_server/websocket_server.py`

**Cambios en evento `connect`:**

```python
import uuid as uuid_module

@socketio.on('connect')
def handle_connect():
    """Cliente web conectado - CON DEVICE REGISTRY"""
    client_id = request.sid
    
    # ✅ NUEVO: Obtener device_uuid del query string
    device_uuid = request.args.get('device_uuid')
    
    if not device_uuid:
        # Generar nuevo UUID si no existe
        device_uuid = str(uuid_module.uuid4())
        logger.info(f"[WebSocket] 🆕 Generando nuevo device_uuid: {device_uuid[:12]}")
    else:
        logger.info(f"[WebSocket] ✅ Device UUID recibido: {device_uuid[:12]}")

    # ✅ Registrar en device registry
    if channel_manager and hasattr(channel_manager, 'device_registry') and channel_manager.device_registry:
        device_registry = channel_manager.device_registry
        
        device_registry.register_device(
            device_uuid,
            {
                'type': 'web',
                'primary_ip': request.remote_addr,
                'user_agent': request.headers.get('User-Agent', 'Unknown')[:200],
                'hostname': request.environ.get('REMOTE_HOST', 'unknown')
            }
        )
        
        logger.info(f"[WebSocket] 📱 Dispositivo registrado: {device_uuid[:12]} ({request.remote_addr})")
        
        # ✅ Restaurar configuración anterior si existe
        saved_config = device_registry.get_configuration(device_uuid)
        
        if saved_config and saved_config.get('channels'):
            logger.info(f"[WebSocket] 💾 Restaurando configuración anterior:")
            logger.info(f"   Canales: {saved_config.get('channels')}")
            logger.info(f"   Ganancia: {saved_config.get('gains')}")
            
            try:
                channel_manager.subscribe_client(
                    client_id,
                    saved_config.get('channels', []),
                    gains=saved_config.get('gains', {}),
                    pans=saved_config.get('pans', {}),
                    client_type="web",
                    device_uuid=device_uuid  # ✅ NUEVO
                )
                
                # Aplicar otras configuraciones
                if client_id in channel_manager.subscriptions:
                    sub = channel_manager.subscriptions[client_id]
                    if saved_config.get('mutes'):
                        sub['mutes'] = saved_config['mutes']
                    if saved_config.get('solos'):
                        sub['solos'] = set(saved_config['solos'])
                    if saved_config.get('master_gain'):
                        sub['master_gain'] = saved_config['master_gain']
                
                logger.info(f"[WebSocket] ✅ Configuración restaurada para {client_id[:8]}")
                
                # Notificar al cliente
                emit('config_restored', {
                    'device_uuid': device_uuid,
                    'channels': saved_config.get('channels', []),
                    'gains': saved_config.get('gains', {}),
                    'pans': saved_config.get('pans', {}),
                    'master_gain': saved_config.get('master_gain', 1.0)
                })
                
            except Exception as e:
                logger.error(f"[WebSocket] Error restaurando config: {e}")
    
    # ✅ Enviar device_uuid al cliente (si fue generado)
    if not request.args.get('device_uuid'):
        emit('device_uuid_assigned', {
            'device_uuid': device_uuid,
            'message': 'Por favor, guarda este UUID en localStorage'
        })
    
    # ... resto del código de connect() ...
```

**Cambios en evento `disconnect`:**

```python
@socketio.on('disconnect')
def handle_disconnect():
    """Cliente web desconectado - GUARDAR CONFIG EN REGISTRY"""
    client_id = request.sid
    
    # ✅ Obtener device_uuid del cliente
    device_uuid = None
    if channel_manager and client_id in channel_manager.subscriptions:
        subscription = channel_manager.subscriptions[client_id]
        device_uuid = subscription.get('device_uuid')
    
    # ✅ NUEVO: Guardar configuración en registry antes de desuscribir
    if channel_manager and hasattr(channel_manager, 'device_registry') and channel_manager.device_registry:
        if device_uuid:
            subscription = channel_manager.get_client_subscription(client_id)
            if subscription:
                channel_manager.device_registry.update_configuration(
                    device_uuid,
                    {
                        'channels': subscription.get('channels', []),
                        'gains': subscription.get('gains', {}),
                        'pans': subscription.get('pans', {}),
                        'mutes': subscription.get('mutes', {}),
                        'solos': list(subscription.get('solos', set())),
                        'master_gain': subscription.get('master_gain', 1.0)
                    }
                )
                logger.info(f"[WebSocket] 💾 Config guardada para device {device_uuid[:12]}")
    
    # Remover de tracking
    with web_clients_lock:
        client_info = web_clients.pop(client_id, None)
    
    if client_info:
        connection_duration = time.time() - client_info['connected_at']
        logger.info(f"[WebSocket] 🔌 Cliente web desconectado: {client_id[:8]} "
                   f"({connection_duration:.1f}s)")
    
    # Desuscribir del channel manager
    if channel_manager:
        try:
            channel_manager.unsubscribe_client(client_id)
        except Exception as e:
            logger.error(f"[WebSocket] Error desuscribiendo: {e}")
    
    # Notificar a otros clientes
    try:
        broadcast_clients_update()
    except:
        pass
```

**Cambios en evento `subscribe`:**

```python
@socketio.on('subscribe')
def handle_subscribe(data):
    """Suscribir cliente web a canales - GUARDAR EN REGISTRY"""
    client_id = request.sid
    
    # ✅ Actualizar actividad
    update_client_activity(client_id)
    
    if not channel_manager:
        emit('error', {'message': 'Channel manager not available'})
        return
    
    try:
        channels = data.get('channels', [])
        gains = data.get('gains', {})
        pans = data.get('pans', {})
        device_uuid = data.get('device_uuid')  # ✅ NUEVO: Podría venir en data
        
        # ✅ Convertir keys a int
        gains_int = {}
        pans_int = {}
        
        for k, v in gains.items():
            try:
                gains_int[int(k)] = float(v)
            except:
                pass
        
        for k, v in pans.items():
            try:
                pans_int[int(k)] = float(v)
            except:
                pass
        
        # ✅ Obtener device_uuid de la suscripción anterior si existe
        if not device_uuid and client_id in channel_manager.subscriptions:
            device_uuid = channel_manager.subscriptions[client_id].get('device_uuid')
        
        # Suscribir cliente
        channel_manager.subscribe_client(
            client_id, 
            channels, 
            gains_int,
            pans_int,
            client_type="web",
            device_uuid=device_uuid  # ✅ NUEVO
        )
        
        # ✅ NUEVO: Guardar config en registry
        if device_uuid and hasattr(channel_manager, 'device_registry') and channel_manager.device_registry:
            channel_manager.device_registry.update_configuration(
                device_uuid,
                {
                    'channels': channels,
                    'gains': gains_int,
                    'pans': pans_int,
                    'master_gain': channel_manager.subscriptions[client_id].get('master_gain', 1.0)
                }
            )
            logger.info(f"[WebSocket] 💾 Config guardada: {device_uuid[:12]} - {len(channels)} canales")
        
        emit('subscribed', {
            'channels': channels,
            'gains': gains_int,
            'pans': pans_int,
            'device_uuid': device_uuid
        })
        
        logger.info(f"[WebSocket] 📡 {client_id[:8]} suscrito: {len(channels)} canales")
        
        # Notificar a otros clientes
        broadcast_clients_update()
        
    except Exception as e:
        logger.error(f"[WebSocket] ❌ Error en subscribe: {e}")
        emit('error', {'message': str(e)})
```

---

## 🧪 Testing

### Prueba 1: Native Client Reconnection

```python
# Simular cliente Android
import socket, json, struct

def test_android_reconnection():
    device_uuid = "550e8400-e29b-41d4-a716-446655440000"
    
    # Primera conexión
    sock1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock1.connect(('localhost', 5555))
    
    handshake = {
        'type': 'handshake',
        'device_uuid': device_uuid,
        'device_info': {
            'device_name': 'Samsung Galaxy S21',
            'mac_address': 'AA:BB:CC:DD:EE:FF',
            'hostname': 'Samsung_S21',
            'app_version': '2.0.0'
        }
    }
    
    payload = json.dumps(handshake).encode('utf-8')
    header = struct.pack('!IHHII', 0xDEADBEEF, 1, 0x0001, 0, len(payload))
    sock1.sendall(header + payload)
    sock1.close()
    
    # Segunda conexión (mismo device)
    sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock2.connect(('localhost', 5555))
    sock2.sendall(header + payload)
    sock2.close()
    
    print("✅ Test completado: Mismo device_uuid debería reutilizar config")
```

---

## 📋 Checklist para implementación

- [ ] Implementar cambios en `native_server.py`
- [ ] Implementar cambios en `websocket_server.py`
- [ ] Probar reconexión de Android
- [ ] Probar reconexión de Web (cambio de IP)
- [ ] Verificar que `config/devices.json` se crea correctamente
- [ ] Verificar limpieza automática de dispositivos expirados
- [ ] Testing de persistencia (reinicio de servidor)
- [ ] Testing de múltiples dispositivos simultáneamente

