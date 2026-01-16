# unified_persistence.py
# âœ… SISTEMA UNIFICADO DE PERSISTENCIA
# - Un Ãºnico lugar de verdad para todas las configuraciones
# - Validación de integridad de datos
# - Versionado y rollback
# - Sincronización automÃ¡tica entre native/web

import json
import os
import logging
import time
import threading
from pathlib import Path
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, asdict, field
from enum import Enum
import hashlib

logger = logging.getLogger(__name__)

class ClientType(Enum):
    """Tipos de clientes soportados"""
    NATIVE = "native"      # Android/iOS
    WEB = "web"           # Navegador
    MASTER = "master"     # Control center
    UNKNOWN = "unknown"

@dataclass
class ClientConfiguration:
    """ConfiguraciÃ³n Ãºnica de un cliente (persistente)"""
    device_uuid: str              # ID Ãºnico estable
    client_type: ClientType       # Tipo de cliente
    custom_name: Optional[str]    # Nombre personalizado
    
    # Mezcla de audio
    channels: List[int]           # Canales activos [0, 1, 2, ...]
    gains: Dict[int, float]       # Ganancia por canal {0: 1.0, 1: 0.8}
    pans: Dict[int, float]        # PanorÃ¡mica por canal {0: 0.0, 1: -0.5}
    mutes: Dict[int, bool]        # Mute por canal {0: False, 1: True}
    master_gain: float            # Ganancia maestra (0.0 - 5.0)
    
    # Metadatos
    created_at: float             # Timestamp de creaciÃ³n
    last_modified: float          # Ãœltima modificaciÃ³n
    last_session_duration: float  # DuraciÃ³n de Ãºltima sesiÃ³n
    reconnection_count: int       # NÃºmero de reconexiones
    
    # Nombres de canales (globales, no por cliente)
    channel_names: Dict[int, str] = field(default_factory=dict)  # {0: "Voz", 1: "Guitarra"}
    
    # Integridad
    data_hash: str = ""           # Hash SHA256 para validaciÃ³n
    schema_version: int = 1       # VersiÃ³n del esquema
    
    def to_dict(self) -> dict:
        """Convertir a dict para serializaciÃ³n JSON"""
        data = asdict(self)
        data['client_type'] = self.client_type.value
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ClientConfiguration':
        """Restaurar desde dict JSON"""
        data = dict(data)  # Copia para no modificar original
        
        # Convertir client_type de string a enum
        if isinstance(data.get('client_type'), str):
            try:
                data['client_type'] = ClientType(data['client_type'])
            except ValueError:
                data['client_type'] = ClientType.UNKNOWN
        
        # Normalizar tipos de datos
        if 'channels' in data:
            data['channels'] = [int(ch) for ch in (data['channels'] or [])]
        
        if 'gains' in data and isinstance(data['gains'], dict):
            data['gains'] = {int(k): float(v) for k, v in data['gains'].items()}
        
        if 'pans' in data and isinstance(data['pans'], dict):
            data['pans'] = {int(k): float(v) for k, v in data['pans'].items()}
        
        if 'mutes' in data and isinstance(data['mutes'], dict):
            data['mutes'] = {int(k): bool(v) for k, v in data['mutes'].items()}
        
        data['master_gain'] = float(data.get('master_gain', 1.0))
        data['created_at'] = float(data.get('created_at', time.time()))
        data['last_modified'] = float(data.get('last_modified', time.time()))
        data['last_session_duration'] = float(data.get('last_session_duration', 0.0))
        data['reconnection_count'] = int(data.get('reconnection_count', 0))
        data['schema_version'] = int(data.get('schema_version', 1))
        
        # Remover hash temporal (se recalcularÃ¡)
        data.pop('data_hash', None)
        
        return cls(**data)
    
    def calculate_hash(self) -> str:
        """Calcular hash SHA256 de la configuraciÃ³n (sin incluir hash)"""
        # Crear dict sin el campo data_hash
        data_to_hash = {k: v for k, v in asdict(self).items() if k != 'data_hash'}
        data_to_hash['client_type'] = self.client_type.value
        
        json_str = json.dumps(data_to_hash, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode()).hexdigest()
    
    def validate_integrity(self) -> bool:
        """Validar integridad de los datos"""
        if not self.data_hash:
            return True  # Sin hash, asumir vÃ¡lido
        
        calculated = self.calculate_hash()
        return calculated == self.data_hash


class UnifiedPersistence:
    """
    âœ… NUEVO: Sistema Ãºnico de persistencia
    - Un Ãºnico archivo de verdad: config/client_configs.json
    - Sincronizado automÃ¡ticamente
    - ValidaciÃ³n de integridad
    - Rollback automÃ¡tico en caso de corrupciÃ³n
    """
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self.main_config_file = self.config_dir / "client_configs.json"
        self.channel_names_file = self.config_dir / "channel_names.json"
        self.backup_dir = self.config_dir / "backups"
        self.backup_dir.mkdir(exist_ok=True)
        
        self.configs: Dict[str, ClientConfiguration] = {}
        self.channel_names: Dict[int, str] = {}
        self.lock = threading.RLock()
        
        # Cargar configuraciones existentes
        self._load_from_disk()
        self._load_channel_names()
        
        # Thread de guardado automÃ¡tico (cada 5 segundos)
        self.auto_save_running = True
        self.auto_save_thread = threading.Thread(target=self._auto_save_loop, daemon=True)
        self.auto_save_thread.start()
        
        logger.info(f"[UnifiedPersistence] âœ… Inicializado: {len(self.configs)} configuraciones cargadas")
    
    def _load_from_disk(self):
        """Cargar todas las configuraciones desde disco"""
        try:
            if not self.main_config_file.exists():
                logger.debug(f"[UnifiedPersistence] Archivo de configuraciones no existe")
                return
            with open(self.main_config_file, 'r', encoding='utf-8') as f:
                data = json.load(f) or {}
            loaded = 0
            for device_uuid, config_data in data.items():
                try:
                    config = ClientConfiguration.from_dict(config_data)
                    # Validar integridad
                    if not config.validate_integrity():
                        logger.warning(f"[UnifiedPersistence] Integridad fallida para {device_uuid[:12]}, ignorando")
                        continue
                    self.configs[device_uuid] = config
                    loaded += 1
                except Exception as e:
                    logger.warning(f"[UnifiedPersistence] Error cargando {device_uuid[:12]}: {e}")
            logger.info(f"[UnifiedPersistence] {loaded} configuraciones cargadas desde {self.main_config_file}")
        except Exception as e:
            logger.error(f"[UnifiedPersistence] Error cargando desde disco: {e}")
            self._restore_from_backup()
    
    def _save_to_disk(self, atomic=True):
        """Guardar todas las configuraciones a disco (atÃ³mico)"""
        try:
            with self.lock:
                # Calcular hashes y preparar datos
                data_to_save = {}
                for uuid, config in self.configs.items():
                    config.data_hash = config.calculate_hash()
                    data_to_save[uuid] = config.to_dict()
            
            if atomic:
                # Escritura atÃ³mica: escribir a temp, luego renombrar
                tmp_path = self.main_config_file.with_suffix('.tmp')
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    json.dump(data_to_save, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, self.main_config_file)
            else:
                with open(self.main_config_file, 'w', encoding='utf-8') as f:
                    json.dump(data_to_save, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"[UnifiedPersistence] ðŸ'¾ {len(data_to_save)} configuraciones guardadas")
        
        except Exception as e:
            logger.error(f"[UnifiedPersistence] âŒ Error guardando a disco: {e}")
    
    def _auto_save_loop(self):
        """Thread de guardado automÃ¡tico"""
        while self.auto_save_running:
            time.sleep(5)  # Cada 5 segundos
            try:
                self._save_to_disk()
            except Exception as e:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"[UnifiedPersistence] Auto-save error: {e}")
    
    def _backup_current(self):
        """Crear backup de la configuraciÃ³n actual"""
        try:
            if self.main_config_file.exists():
                timestamp = int(time.time())
                backup_path = self.backup_dir / f"client_configs_{timestamp}.json"
                import shutil
                shutil.copy(self.main_config_file, backup_path)
                logger.debug(f"[UnifiedPersistence] ðŸ'¾ Backup creado: {backup_path.name}")
        except Exception as e:
            logger.warning(f"[UnifiedPersistence] Error creando backup: {e}")
    
    def _restore_from_backup(self):
        """Intentar restaurar desde el Ãºltimo backup vÃ¡lido"""
        try:
            backups = sorted(self.backup_dir.glob("client_configs_*.json"), reverse=True)
            for backup_path in backups:
                try:
                    with open(backup_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    logger.info(f"[UnifiedPersistence] Restaurando desde backup: {backup_path.name}")
                    
                    with self.lock:
                        self.configs.clear()
                        for uuid, config_data in data.items():
                            config = ClientConfiguration.from_dict(config_data)
                            self.configs[uuid] = config
                    
                    # Guardar como configuraciÃ³n actual
                    self._save_to_disk()
                    logger.info(f"[UnifiedPersistence] âœ… Restaurados {len(self.configs)} dispositivos desde backup")
                    return
                except Exception as e:
                    logger.warning(f"[UnifiedPersistence] Backup {backup_path.name} no vÃ¡lido: {e}")
        
        except Exception as e:
            logger.error(f"[UnifiedPersistence] Error restaurando backups: {e}")
    
    def _load_channel_names(self):
        """Cargar nombres de canales desde disco"""
        try:
            if self.channel_names_file.exists():
                with open(self.channel_names_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        # Convertir claves string a int
                        self.channel_names = {int(k): v for k, v in data.items()}
                        logger.info(f"[UnifiedPersistence] ðŸ“ Cargados {len(self.channel_names)} nombres de canales")
        except Exception as e:
            logger.warning(f"[UnifiedPersistence] Error cargando nombres de canales: {e}")
            self.channel_names = {}
    
    def _save_channel_names(self):
        """Guardar nombres de canales a disco"""
        try:
            with self.lock:
                with open(self.channel_names_file, 'w', encoding='utf-8') as f:
                    json.dump(self.channel_names, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[UnifiedPersistence] Error guardando nombres de canales: {e}")
    
    def update_channel_name(self, channel: int, name: str):
        """Actualizar nombre de canal global"""
        with self.lock:
            self.channel_names[channel] = name.strip()
            self._save_channel_names()
            logger.debug(f"[UnifiedPersistence] ðŸ“‚ Nombre canal {channel}: '{name.strip()}'")
    
    def get_channel_names(self) -> Dict[int, str]:
        """Obtener todos los nombres de canales"""
        with self.lock:
            return self.channel_names.copy()
    
    # =========================================================================
    # API PÃŒBLICA
    # =========================================================================
    
    def save_or_update_config(self, device_uuid: str, config: ClientConfiguration) -> bool:
        """Guardar o actualizar configuraciÃ³n de un cliente"""
        try:
            with self.lock:
                config.last_modified = time.time()
                
                if device_uuid in self.configs:
                    # Actualizar: preservar created_at
                    config.created_at = self.configs[device_uuid].created_at
                    config.reconnection_count = self.configs[device_uuid].reconnection_count + 1
                
                self.configs[device_uuid] = config
            
            logger.debug(f"[UnifiedPersistence] ðŸ'¾ Config guardada: {device_uuid[:12]}")
            return True
        
        except Exception as e:
            logger.error(f"[UnifiedPersistence] Error guardando config: {e}")
            return False
    
    def get_config(self, device_uuid: str, validate=True) -> Optional[ClientConfiguration]:
        """Obtener configuraciÃ³n de un cliente"""
        with self.lock:
            config = self.configs.get(device_uuid)
        
        if config and validate and not config.validate_integrity():
            logger.warning(f"[UnifiedPersistence] âš ï¸ Config corrompida: {device_uuid[:12]}")
            return None
        
        return config
    
    def get_all_configs(self, client_type: Optional[ClientType] = None) -> Dict[str, ClientConfiguration]:
        """Obtener todas las configuraciones (opcionalmente filtradas por tipo)"""
        with self.lock:
            if client_type:
                return {
                    uuid: config for uuid, config in self.configs.items()
                    if config.client_type == client_type
                }
            return dict(self.configs)
    
    def delete_config(self, device_uuid: str) -> bool:
        """Eliminar configuraciÃ³n de un cliente"""
        with self.lock:
            if device_uuid in self.configs:
                del self.configs[device_uuid]
                logger.info(f"[UnifiedPersistence] ðŸ—'ï¸ Config eliminada: {device_uuid[:12]}")
                return True
        return False
    
    def update_channels(self, device_uuid: str, channels: List[int],
                       gains: Optional[Dict[int, float]] = None,
                       pans: Optional[Dict[int, float]] = None,
                       mutes: Optional[Dict[int, bool]] = None,
                       master_gain: Optional[float] = None) -> bool:
        """Actualizar canales y parÃ¡metros de un cliente"""
        with self.lock:
            config = self.configs.get(device_uuid)
            if not config:
                return False
            
            # Validar canales (asegurar que sean int)
            config.channels = [int(ch) for ch in (channels or config.channels)]
            
            if gains:
                config.gains.update({int(k): float(v) for k, v in gains.items()})
            
            if pans:
                config.pans.update({int(k): float(v) for k, v in pans.items()})
            
            if mutes:
                config.mutes.update({int(k): bool(v) for k, v in mutes.items()})
            
            if master_gain is not None:
                config.master_gain = float(master_gain)
            
            config.last_modified = time.time()
        
        return True
    
    def get_stats(self) -> dict:
        """Obtener estadÃ­sticas de persistencia"""
        with self.lock:
            by_type = {}
            for config in self.configs.values():
                t = config.client_type.value
                by_type[t] = by_type.get(t, 0) + 1
            
            return {
                'total_configs': len(self.configs),
                'by_type': by_type,
                'file_path': str(self.main_config_file),
                'file_size_kb': self.main_config_file.stat().st_size / 1024 if self.main_config_file.exists() else 0
            }
    
    def shutdown(self):
        """Detener y limpiar recursos"""
        self.auto_save_running = False
        self._save_to_disk()
        self._save_channel_names()
        logger.info("[UnifiedPersistence] âœ… Guardado final completado")


# Instancia global
_unified_persistence: Optional[UnifiedPersistence] = None

def init_unified_persistence(config_dir: str = "config") -> UnifiedPersistence:
    """Inicializar sistema global de persistencia"""
    global _unified_persistence
    _unified_persistence = UnifiedPersistence(config_dir)
    return _unified_persistence

def get_unified_persistence() -> UnifiedPersistence:
    """Obtener instancia global"""
    global _unified_persistence
    if _unified_persistence is None:
        _unified_persistence = UnifiedPersistence()
    return _unified_persistence