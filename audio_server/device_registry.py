# device_registry.py - Sistema de identificación única de dispositivos

import json
import threading
import time
import os
import logging
import uuid as uuid_module
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

class DeviceRegistry:
    """
    Registro central de dispositivos conectados.
    
    Cada dispositivo (web, Android, iOS) recibe un UUID único que se mantiene
    incluso si cambia IP, red o usuario-agent.
    
    Structure:
    {
        'device_uuid': {
            'uuid': 'str',
            'type': 'web|android|ios',
            'name': 'str',
            'mac_address': 'str | None',
            'primary_ip': 'str',
            'device_info': {
                'os': 'str',
                'hostname': 'str',
                'user_agent': 'str',
                ...
            },
            'first_seen': timestamp,
            'last_seen': timestamp,
            'reconnections': int,
            'configuration': {
                'channels': [...],
                'gains': {...},
                'pans': {...},
                ...
            },
            'tags': ['tag1', 'tag2'],
            'active': True|False
        }
    }
    """
    
    def __init__(self, persistence_file: str = "config/devices.json"):
        self.devices: Dict[str, dict] = {}
        self.device_lock = threading.RLock()
        self.persistence_file = persistence_file
        self.persistence_lock = threading.Lock()
        # ✅ Sesión actual del servidor (cambia en cada arranque)
        self.server_session_id: Optional[str] = None
        self.cleanup_interval = 3600  # Limpiar cada hora
        self.max_devices = 500
        self.device_cache_timeout = 604800  # 7 días
        
        # Crear directorio si no existe
        os.makedirs(os.path.dirname(persistence_file) or '.', exist_ok=True)
        
        # Cargar desde disco
        self.load_from_disk()
        
        # Iniciar thread de limpieza
        self._start_cleanup_thread()

    def set_server_session(self, session_id: str):
        """Fijar session_id del servidor para restauración por sesión."""
        self.server_session_id = session_id
        logger.info(f"[Device Registry] 🧷 Server session: {session_id[:12]}")
    
    # ========================================================================
    # OPERACIONES PRINCIPALES
    # ========================================================================
    
    def register_device(self, device_uuid: str, device_info: dict) -> dict:
        """
        Registrar o actualizar dispositivo.
        
        Args:
            device_uuid: UUID único del dispositivo
            device_info: {
                'type': 'web|android|ios',
                'name': 'nombre del dispositivo',
                'mac_address': 'MAC si está disponible',
                'primary_ip': 'IP actual',
                'os': 'Android|Windows|macOS|iOS|Linux',
                'hostname': 'nombre del host',
                'user_agent': 'user-agent si es web',
                ...
            }
        
        Returns:
            device_record completo
        """
        with self.device_lock:
            current_time = time.time()
            
            if device_uuid in self.devices:
                # Actualizar dispositivo existente
                device = self.devices[device_uuid]
                device['last_seen'] = current_time
                device['reconnections'] = device.get('reconnections', 0) + 1
                device['active'] = True
                
                # Actualizar info si es más nueva
                if device_info.get('mac_address') and not device.get('mac_address'):
                    device['mac_address'] = device_info.get('mac_address')
                
                device['primary_ip'] = device_info.get('primary_ip')
                device['device_info'].update(device_info)
                
                logger.info(f"[Device Registry] 🔄 Dispositivo actualizado: {device_uuid[:12]} "
                           f"(Reconexión #{device['reconnections']})")
            else:
                # Crear nuevo dispositivo
                device = {
                    'uuid': device_uuid,
                    'type': device_info.get('type', 'unknown'),
                    'name': device_info.get('name', f"Device-{device_uuid[:8]}"),
                    'mac_address': device_info.get('mac_address'),
                    'primary_ip': device_info.get('primary_ip'),
                    'device_info': device_info,
                    'first_seen': current_time,
                    'last_seen': current_time,
                    'reconnections': 0,
                    'configuration': {},  # Se rellena después
                    'tags': [],
                    'active': True
                }
                self.devices[device_uuid] = device
                
                logger.info(f"[Device Registry] ✅ Nuevo dispositivo registrado: {device_uuid[:12]} "
                           f"({device['type']}) - {device.get('name')}")
            
            # Guardar a disco
            self.save_to_disk()
            
            return self.devices[device_uuid]
    
    def get_device(self, device_uuid: str) -> Optional[dict]:
        """Obtener información de dispositivo."""
        with self.device_lock:
            if device_uuid in self.devices:
                device = self.devices[device_uuid]
                
                # Verificar si está expirado
                if time.time() - device.get('last_seen', 0) > self.device_cache_timeout:
                    logger.warning(f"[Device Registry] ⚠️ Dispositivo expirado: {device_uuid[:12]}")
                    return None
                
                return device
            
            return None
    
    def find_device_by_mac(self, mac_address: str) -> Optional[dict]:
        """Buscar dispositivo por dirección MAC."""
        if not mac_address:
            return None
        
        with self.device_lock:
            for device in self.devices.values():
                if device.get('mac_address') == mac_address:
                    return device
        
        return None
    
    def find_device_by_ip_and_type(self, ip: str, device_type: str) -> Optional[dict]:
        """Buscar dispositivo por IP y tipo (secundario)."""
        if not ip:
            return None
        
        with self.device_lock:
            candidates = [
                d for d in self.devices.values()
                if d.get('primary_ip') == ip and d.get('type') == device_type
            ]
            
            if candidates:
                return candidates[0]
        
        return None
    
    def update_configuration(self, device_uuid: str, config: dict, session_id: Optional[str] = None) -> bool:
        """
        Guardar/actualizar configuración de dispositivo.
        
        Args:
            device_uuid: UUID del dispositivo
            config: {
                'channels': [0, 1, 2],
                'gains': {0: 1.0, 1: 0.8},
                'pans': {0: 0.0, 1: -0.5},
                'mutes': {0: False},
                'solos': [],
                'master_gain': 1.0,
                ...
            }
        """
        with self.device_lock:
            if device_uuid not in self.devices:
                return False
            
            self.devices[device_uuid]['configuration'] = config
            if session_id is not None:
                self.devices[device_uuid]['configuration_session_id'] = session_id
            self.devices[device_uuid]['last_seen'] = time.time()
            
            self.save_to_disk()
            logger.debug(f"[Device Registry] 💾 Config guardada: {device_uuid[:12]}")
            
            return True
    
    def get_configuration(self, device_uuid: str, session_id: Optional[str] = None) -> dict:
        """Obtener configuración guardada del dispositivo.

        Si session_id se entrega, solo retorna config si coincide con la sesión
        guardada (reinicio del servidor => session distinta => no restaura).
        """
        device = self.get_device(device_uuid)
        if not device:
            return {}

        if session_id is not None:
            saved_session = device.get('configuration_session_id')
            if saved_session and saved_session != session_id:
                return {}

        return device.get('configuration', {})
    
    def mark_inactive(self, device_uuid: str):
        """Marcar dispositivo como inactivo."""
        with self.device_lock:
            if device_uuid in self.devices:
                self.devices[device_uuid]['active'] = False
    
    def add_tag(self, device_uuid: str, tag: str):
        """Agregar etiqueta a dispositivo."""
        with self.device_lock:
            if device_uuid in self.devices:
                tags = self.devices[device_uuid].get('tags', [])
                if tag not in tags:
                    tags.append(tag)
                    self.save_to_disk()
    
    def set_custom_name(self, device_uuid: str, custom_name: str) -> bool:
        """✅ NUEVO: Guardar nombre personalizado de dispositivo."""
        with self.device_lock:
            if device_uuid not in self.devices:
                return False
            
            self.devices[device_uuid]['custom_name'] = custom_name
            self.devices[device_uuid]['last_seen'] = time.time()
            self.save_to_disk()
            
            logger.info(f"[Device Registry] 📝 Nombre personalizado guardado: {device_uuid[:12]} = {custom_name}")
            return True
    
    def get_custom_name(self, device_uuid: str) -> Optional[str]:
        """✅ NUEVO: Obtener nombre personalizado de dispositivo."""
        device = self.get_device(device_uuid)
        if device:
            return device.get('custom_name')
        return None
    
    # ========================================================================
    # LISTADO Y ESTADÍSTICAS
    # ========================================================================
    
    def get_all_devices(self, active_only: bool = False) -> List[dict]:
        """Obtener lista de todos los dispositivos."""
        with self.device_lock:
            devices = list(self.devices.values())
            
            if active_only:
                devices = [d for d in devices if d.get('active', False)]
            
            return devices
    
    def get_devices_by_type(self, device_type: str) -> List[dict]:
        """Obtener dispositivos de un tipo específico."""
        with self.device_lock:
            return [d for d in self.devices.values() if d.get('type') == device_type]
    
    def get_active_devices(self) -> List[dict]:
        """Obtener dispositivos activos."""
        with self.device_lock:
            return [d for d in self.devices.values() if d.get('active', False)]
    
    def get_stats(self) -> dict:
        """Obtener estadísticas del registro."""
        with self.device_lock:
            total = len(self.devices)
            active = sum(1 for d in self.devices.values() if d.get('active', False))
            by_type = {}
            
            for device in self.devices.values():
                dev_type = device.get('type', 'unknown')
                by_type[dev_type] = by_type.get(dev_type, 0) + 1
            
            return {
                'total_devices': total,
                'active_devices': active,
                'by_type': by_type,
                'max_devices': self.max_devices,
                'persistence_file': self.persistence_file
            }
    
    # ========================================================================
    # PERSISTENCIA
    # ========================================================================
    
    def save_to_disk(self):
        """Guardar registro a archivo JSON."""
        with self.persistence_lock:
            try:
                # Crear diccionario serializable
                devices_data = {}
                with self.device_lock:
                    for uuid, device in self.devices.items():
                        devices_data[uuid] = {
                            'uuid': device['uuid'],
                            'type': device['type'],
                            'name': device['name'],
                            'mac_address': device.get('mac_address'),
                            'primary_ip': device.get('primary_ip'),
                            'device_info': device.get('device_info', {}),
                            'first_seen': device.get('first_seen'),
                            'last_seen': device.get('last_seen'),
                            'reconnections': device.get('reconnections', 0),
                            'configuration': device.get('configuration', {}),
                            'configuration_session_id': device.get('configuration_session_id'),
                            'tags': device.get('tags', []),
                            'active': device.get('active', False)
                        }
                
                os.makedirs(os.path.dirname(self.persistence_file) or '.', exist_ok=True)
                
                with open(self.persistence_file, 'w') as f:
                    json.dump(devices_data, f, indent=2)
                
                logger.debug(f"[Device Registry] 💾 Guardado a {self.persistence_file}")
                
            except Exception as e:
                logger.error(f"[Device Registry] ❌ Error guardando a disco: {e}")
    
    def load_from_disk(self):
        """Cargar registro desde archivo JSON."""
        if not os.path.exists(self.persistence_file):
            logger.info(f"[Device Registry] 📄 Archivo no existe: {self.persistence_file}")
            return
        
        with self.persistence_lock:
            try:
                with open(self.persistence_file, 'r') as f:
                    devices_data = json.load(f)
                
                with self.device_lock:
                    self.devices = devices_data
                
                logger.info(f"[Device Registry] ✅ Cargados {len(self.devices)} dispositivos")
                
            except Exception as e:
                logger.error(f"[Device Registry] ❌ Error cargando desde disco: {e}")
    
    # ========================================================================
    # LIMPIEZA Y MANTENIMIENTO
    # ========================================================================
    
    def cleanup_expired(self):
        """Limpiar dispositivos expirados."""
        with self.device_lock:
            current_time = time.time()
            expired = []
            
            for uuid, device in self.devices.items():
                last_seen = device.get('last_seen', 0)
                if current_time - last_seen > self.device_cache_timeout:
                    expired.append(uuid)
            
            for uuid in expired:
                logger.info(f"[Device Registry] 🗑️ Limpiando dispositivo expirado: {uuid[:12]}")
                del self.devices[uuid]
            
            if expired:
                self.save_to_disk()
            
            return len(expired)
    
    def cleanup_excess_devices(self):
        """Limpiar si excede máximo de dispositivos (mantener los más recientes)."""
        with self.device_lock:
            if len(self.devices) > self.max_devices:
                # Ordenar por last_seen
                sorted_devices = sorted(
                    self.devices.items(),
                    key=lambda x: x[1].get('last_seen', 0)
                )
                
                to_remove = len(self.devices) - self.max_devices
                removed = []
                
                for uuid, _ in sorted_devices[:to_remove]:
                    logger.info(f"[Device Registry] 🗑️ Limpiando por exceso: {uuid[:12]}")
                    del self.devices[uuid]
                    removed.append(uuid)
                
                if removed:
                    self.save_to_disk()
                
                return len(removed)
        
        return 0
    
    def _start_cleanup_thread(self):
        """Iniciar thread de limpieza automática."""
        def cleanup_loop():
            while True:
                try:
                    time.sleep(self.cleanup_interval)
                    
                    expired = self.cleanup_expired()
                    excess = self.cleanup_excess_devices()
                    
                    if expired or excess:
                        logger.info(f"[Device Registry] 🧹 Limpieza: {expired} expirados, "
                                  f"{excess} por exceso")
                    
                except Exception as e:
                    logger.error(f"[Device Registry] Error en cleanup: {e}")
        
        thread = threading.Thread(target=cleanup_loop, daemon=True)
        thread.start()


# ============================================================================
# FUNCIÓN HELPER GLOBAL
# ============================================================================

_global_registry: Optional[DeviceRegistry] = None

def get_device_registry() -> DeviceRegistry:
    """Obtener instancia global del registro de dispositivos."""
    global _global_registry
    if _global_registry is None:
        _global_registry = DeviceRegistry()
    return _global_registry

def init_device_registry(persistence_file: str = "config/devices.json") -> DeviceRegistry:
    """Inicializar registro de dispositivos (se llama desde main.py)."""
    global _global_registry
    _global_registry = DeviceRegistry(persistence_file)
    return _global_registry

