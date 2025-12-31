# audio_server/scene_manager.py
"""
✅ Sistema de gestión de ESCENAS
- Guarda snapshots completos del estado del servidor
- Valida compatibilidad de interfaz de audio
- Carga/descarga escenas con confirmación
- Exporta/importa escenas
"""

import json
import os
import logging
from datetime import datetime
import shutil
import re
import time  # ✅ AGREGAR: necesario para _save_config_for_reconnect()

logger = logging.getLogger(__name__)

class SceneManager:
    """
    Gestiona escenas (snapshots) de configuración completa
    """
    
    def __init__(self, scenes_dir='scenes'):
        self.scenes_dir = scenes_dir
        self.main_app = None  # Se inyecta después
        
        # Crear carpeta de escenas
        os.makedirs(self.scenes_dir, exist_ok=True)
        
        logger.info(f"[SceneManager] ✅ Inicializado: {self.scenes_dir}")
    
    def set_main_app(self, main_app):
        """Inyectar referencia a la aplicación principal"""
        self.main_app = main_app
        logger.info("[SceneManager] ✅ Referencia a main_app establecida")
    
    def get_current_device_info(self):
        """
        Obtener información de la interfaz de audio ACTUAL
        """
        if not self.main_app or not self.main_app.audio_capture:
            return None
        
        try:
            # Obtener device_id actual
            device_id = self.main_app.audio_capture.selected_device_id if hasattr(self.main_app.audio_capture, 'selected_device_id') else -1
            
            if device_id == -1:
                device_id = self.main_app.selected_device_id if hasattr(self.main_app, 'selected_device_id') else -1
            
            if device_id == -1:
                logger.warning("[SceneManager] No se pudo obtener device_id")
                return None
            
            # Obtener info del dispositivo
            import sounddevice as sd
            device_info = sd.query_devices(device_id)
            
            import config
            
            return {
                'device_id': device_id,
                'name': device_info['name'],
                'channels': self.main_app.channel_manager.num_channels if self.main_app.channel_manager else device_info['max_input_channels'],
                'sample_rate': config.SAMPLE_RATE,
                'blocksize': config.BLOCKSIZE
            }
            
        except Exception as e:
            logger.error(f"[SceneManager] Error obteniendo device info: {e}")
            return None
    
    def capture_current_state(self):
        """
        Captura el estado COMPLETO del servidor
        """
        if not self.main_app:
            raise Exception("main_app no está configurado")
        
        if not self.main_app.server_running:
            raise Exception("Servidor no está corriendo")
        
        # 1. Info de interfaz
        device_info = self.get_current_device_info()
        if not device_info:
            raise Exception("No se pudo obtener información de la interfaz")
        
        # 2. Capturar configuración de TODOS los clientes
        clients_config = {}
        
        if self.main_app.native_server and self.main_app.channel_manager:
            with self.main_app.native_server.client_lock:
                for addr, client_obj in self.main_app.native_server.clients.items():
                    client_id = client_obj.id
                    
                    # Obtener suscripción desde channel_manager
                    subscription = self.main_app.channel_manager.get_client_subscription(client_id)
                    
                    if subscription:
                        # Crear key por IP
                        client_key = f"ip_{addr[0]}"
                        
                        clients_config[client_key] = {
                            'address': f"{addr[0]}:{addr[1]}",
                            'channels': subscription.get('channels', []),
                            'gains': subscription.get('gains', {}),
                            'pans': subscription.get('pans', {}),
                            'mutes': subscription.get('mutes', {}),
                            'solos': list(subscription.get('solos', set())),
                            'pre_listen': subscription.get('pre_listen'),
                            'master_gain': subscription.get('master_gain', 1.0),
                            'client_type': subscription.get('client_type', 'native')
                        }
        
        # 3. Settings del servidor
        import config
        server_settings = {
            'sample_rate': config.SAMPLE_RATE,
            'blocksize': config.BLOCKSIZE,
            'num_channels': device_info['channels']
        }
        
        return {
            'interface_info': device_info,
            'clients': clients_config,
            'server_settings': server_settings
        }
    
    def validate_scene_name(self, name):
        """
        Validar que el nombre de escena sea válido
        """
        # Caracteres no permitidos en nombres de archivo
        invalid_chars = r'[<>:"/\\|?*]'
        
        if not name or len(name.strip()) == 0:
            return False, "El nombre no puede estar vacío"
        
        if re.search(invalid_chars, name):
            return False, "El nombre contiene caracteres inválidos"
        
        if len(name) > 100:
            return False, "El nombre es demasiado largo (máx 100 caracteres)"
        
        return True, "OK"
    
    def save_scene(self, name, description=""):
        """
        Guardar escena actual
        """
        try:
            # Validar nombre
            valid, message = self.validate_scene_name(name)
            if not valid:
                return False, message
            
            logger.info(f"[SceneManager] 💾 Guardando escena: {name}")
            
            # Capturar estado actual
            state = self.capture_current_state()
            
            # Crear estructura de escena
            scene_data = {
                'version': '1.0',
                'scene_name': name,
                'description': description,
                'metadata': {
                    'created_at': datetime.now().isoformat(),
                    'last_loaded': None,
                    'load_count': 0
                },
                'interface_info': state['interface_info'],
                'clients': state['clients'],
                'server_settings': state['server_settings']
            }
            
            # Nombre de archivo
            filename = self._sanitize_filename(name) + '.json'
            filepath = os.path.join(self.scenes_dir, filename)
            
            # Si existe, hacer backup
            if os.path.exists(filepath):
                backup_path = filepath + '.backup'
                shutil.copy2(filepath, backup_path)
                logger.info(f"[SceneManager] 📦 Backup creado: {backup_path}")
            
            # Guardar
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(scene_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"[SceneManager] ✅ Escena guardada: {filepath}")
            logger.info(f"[SceneManager]    Interfaz: {state['interface_info']['name']} ({state['interface_info']['channels']}ch)")
            logger.info(f"[SceneManager]    Clientes: {len(state['clients'])}")
            
            return True, f"Escena guardada: {filename}"
            
        except Exception as e:
            error_msg = f"Error guardando escena: {str(e)}"
            logger.error(f"[SceneManager] ❌ {error_msg}")
            return False, error_msg
    
    def list_scenes(self):
        """
        Listar todas las escenas disponibles
        """
        scenes = []
        
        try:
            # Leer todos los .json en carpeta scenes/
            for filename in os.listdir(self.scenes_dir):
                if not filename.endswith('.json'):
                    continue
                
                if filename.endswith('.backup'):
                    continue
                
                filepath = os.path.join(self.scenes_dir, filename)
                
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        scene_data = json.load(f)
                    
                    # Validar compatibilidad con interfaz actual
                    compatible, compat_message = self.validate_scene_compatibility(scene_data)
                    
                    # Info resumida
                    scene_info = {
                        'filename': filename,
                        'name': scene_data.get('scene_name', filename),
                        'description': scene_data.get('description', ''),
                        'created_at': scene_data.get('metadata', {}).get('created_at', 'Unknown'),
                        'last_loaded': scene_data.get('metadata', {}).get('last_loaded'),
                        'load_count': scene_data.get('metadata', {}).get('load_count', 0),
                        'interface_name': scene_data.get('interface_info', {}).get('name', 'Unknown'),
                        'interface_channels': scene_data.get('interface_info', {}).get('channels', 0),
                        'num_clients': len(scene_data.get('clients', {})),
                        'compatible': compatible,
                        'compatibility_message': compat_message
                    }
                    
                    scenes.append(scene_info)
                    
                except Exception as e:
                    logger.error(f"[SceneManager] Error leyendo {filename}: {e}")
                    continue
            
            # Ordenar por fecha de creación (más reciente primero)
            scenes.sort(key=lambda x: x['created_at'], reverse=True)
            
            logger.info(f"[SceneManager] 📋 {len(scenes)} escenas encontradas")
            
            return scenes
            
        except Exception as e:
            logger.error(f"[SceneManager] Error listando escenas: {e}")
            return []
    
    def validate_scene_compatibility(self, scene_data):
        """
        Validar si una escena es compatible con la interfaz actual
        
        Retorna: (compatible: bool, message: str)
        """
        try:
            # Obtener interfaz actual
            current_device = self.get_current_device_info()
            
            if not current_device:
                return False, "No se pudo obtener información de la interfaz actual"
            
            # Obtener interfaz de la escena
            scene_device = scene_data.get('interface_info', {})
            
            if not scene_device:
                return False, "Escena no tiene información de interfaz"
            
            current_name = current_device.get('name', '')
            current_channels = current_device.get('channels', 0)
            
            scene_name = scene_device.get('name', '')
            scene_channels = scene_device.get('channels', 0)
            
            # Validación ESTRICTA: mismo nombre Y mismos canales
            if current_name == scene_name and current_channels == scene_channels:
                return True, "✅ Interfaz idéntica"
            
            # Validación FLEXIBLE: mismo número de canales (diferente marca)
            if current_channels == scene_channels:
                return True, f"⚠️ Advertencia: interfaz diferente ({current_name}) pero mismo número de canales"
            
            # Interfaz actual tiene MÁS canales que la escena
            if current_channels > scene_channels:
                return True, f"⚠️ Interfaz actual tiene más canales ({current_channels} vs {scene_channels})"
            
            # Interfaz actual tiene MENOS canales que la escena
            if current_channels < scene_channels:
                return False, f"❌ Interfaz incompatible: escena requiere {scene_channels} canales pero actual tiene {current_channels}"
            
            return False, "❌ Interfaz incompatible"
            
        except Exception as e:
            logger.error(f"[SceneManager] Error validando compatibilidad: {e}")
            return False, f"Error: {str(e)}"
    
    def load_scene(self, name):
        """
        Cargar una escena
        """
        try:
            filename = self._sanitize_filename(name) + '.json'
            filepath = os.path.join(self.scenes_dir, filename)
            
            if not os.path.exists(filepath):
                return False, f"Escena no encontrada: {filename}"
            
            logger.info(f"[SceneManager] 📂 Cargando escena: {name}")
            
            # Leer escena
            with open(filepath, 'r', encoding='utf-8') as f:
                scene_data = json.load(f)
            
            # Validar compatibilidad
            compatible, compat_message = self.validate_scene_compatibility(scene_data)
            
            if not compatible:
                logger.error(f"[SceneManager] ❌ {compat_message}")
                return False, compat_message
            
            logger.info(f"[SceneManager] ✅ Compatibilidad verificada: {compat_message}")
            
            # Aplicar configuración a cada cliente
            clients_config = scene_data.get('clients', {})
            applied_count = 0
            pending_count = 0
            
            for client_key, client_config in clients_config.items():
                # Buscar cliente conectado
                client_id = self._find_connected_client_by_key(client_key)
                
                if client_id:
                    # Cliente conectado → aplicar inmediatamente
                    self._apply_config_to_client(client_id, client_config)
                    applied_count += 1
                    logger.info(f"[SceneManager]    ✅ Aplicado a cliente: {client_key}")
                else:
                    # Cliente no conectado → guardar para cuando reconecte
                    self._save_config_for_reconnect(client_key, client_config)
                    pending_count += 1
                    logger.info(f"[SceneManager]    ⏳ Guardado para reconexión: {client_key}")
            
            # Actualizar metadata de escena
            scene_data['metadata']['last_loaded'] = datetime.now().isoformat()
            scene_data['metadata']['load_count'] = scene_data['metadata'].get('load_count', 0) + 1
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(scene_data, f, indent=2, ensure_ascii=False)
            
            result_message = f"Escena cargada: {applied_count} clientes aplicados"
            if pending_count > 0:
                result_message += f", {pending_count} esperando conexión"
            
            logger.info(f"[SceneManager] ✅ {result_message}")
            
            return True, result_message
            
        except Exception as e:
            error_msg = f"Error cargando escena: {str(e)}"
            logger.error(f"[SceneManager] ❌ {error_msg}")
            import traceback
            traceback.print_exc()
            return False, error_msg
    
    def delete_scene(self, name):
        """
        Eliminar una escena (con backup)
        """
        try:
            filename = self._sanitize_filename(name) + '.json'
            filepath = os.path.join(self.scenes_dir, filename)
            
            if not os.path.exists(filepath):
                return False, f"Escena no encontrada: {filename}"
            
            # Crear backup con timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = filepath + f'.deleted.{timestamp}'
            shutil.move(filepath, backup_path)
            
            logger.info(f"[SceneManager] 🗑️ Escena eliminada: {name}")
            logger.info(f"[SceneManager]    Backup: {backup_path}")
            
            return True, f"Escena eliminada (backup: {os.path.basename(backup_path)})"
            
        except Exception as e:
            error_msg = f"Error eliminando escena: {str(e)}"
            logger.error(f"[SceneManager] ❌ {error_msg}")
            return False, error_msg
    
    def export_scene(self, name, destination_path):
        """
        Exportar escena a ubicación externa
        """
        try:
            filename = self._sanitize_filename(name) + '.json'
            filepath = os.path.join(self.scenes_dir, filename)
            
            if not os.path.exists(filepath):
                return False, f"Escena no encontrada: {filename}"
            
            # Copiar archivo
            shutil.copy2(filepath, destination_path)
            
            logger.info(f"[SceneManager] 📤 Escena exportada: {name} → {destination_path}")
            
            return True, f"Escena exportada a: {destination_path}"
            
        except Exception as e:
            error_msg = f"Error exportando escena: {str(e)}"
            logger.error(f"[SceneManager] ❌ {error_msg}")
            return False, error_msg
    
    def import_scene(self, source_path):
        """
        Importar escena desde archivo externo
        """
        try:
            # Validar que sea JSON válido
            with open(source_path, 'r', encoding='utf-8') as f:
                scene_data = json.load(f)
            
            # Validar estructura
            if 'scene_name' not in scene_data:
                return False, "Archivo no tiene formato válido de escena"
            
            scene_name = scene_data['scene_name']
            
            # Nombre de destino
            filename = self._sanitize_filename(scene_name) + '.json'
            filepath = os.path.join(self.scenes_dir, filename)
            
            # Si existe, agregar sufijo
            if os.path.exists(filepath):
                base_filename = self._sanitize_filename(scene_name)
                counter = 1
                while os.path.exists(os.path.join(self.scenes_dir, f"{base_filename}_{counter}.json")):
                    counter += 1
                filename = f"{base_filename}_{counter}.json"
                filepath = os.path.join(self.scenes_dir, filename)
            
            # Copiar archivo
            shutil.copy2(source_path, filepath)
            
            logger.info(f"[SceneManager] 📥 Escena importada: {scene_name} → {filename}")
            
            return True, f"Escena importada: {filename}"
            
        except json.JSONDecodeError:
            return False, "Archivo no es un JSON válido"
        except Exception as e:
            error_msg = f"Error importando escena: {str(e)}"
            logger.error(f"[SceneManager] ❌ {error_msg}")
            return False, error_msg
    
    def get_scene_details(self, name):
        """
        Obtener detalles completos de una escena
        """
        try:
            filename = self._sanitize_filename(name) + '.json'
            filepath = os.path.join(self.scenes_dir, filename)
            
            if not os.path.exists(filepath):
                return None
            
            with open(filepath, 'r', encoding='utf-8') as f:
                scene_data = json.load(f)
            
            return scene_data
            
        except Exception as e:
            logger.error(f"[SceneManager] Error obteniendo detalles: {e}")
            return None
    
    # ========================================================================
    # MÉTODOS AUXILIARES INTERNOS
    # ========================================================================
    
    def _sanitize_filename(self, name):
        """Convertir nombre de escena a nombre de archivo válido"""
        # Reemplazar caracteres inválidos con guión bajo
        sanitized = re.sub(r'[<>:"/\\|?*]', '_', name)
        # Reemplazar espacios con guión bajo
        sanitized = sanitized.replace(' ', '_')
        # Limitar longitud
        sanitized = sanitized[:100]
        return sanitized
    
    def _find_connected_client_by_key(self, client_key):
        """
        Buscar cliente conectado que coincida con la key (IP)
        
        client_key = "ip_192.168.1.100"
        Retorna: client_id si encontrado, None si no
        """
        if not self.main_app or not self.main_app.native_server:
            return None
        
        try:
            # Extraer IP de la key
            ip = client_key.replace('ip_', '')
            
            with self.main_app.native_server.client_lock:
                for addr, client_obj in self.main_app.native_server.clients.items():
                    if addr[0] == ip:
                        return client_obj.id
            
            return None
            
        except Exception as e:
            logger.error(f"[SceneManager] Error buscando cliente: {e}")
            return None
    
    def _apply_config_to_client(self, client_id, config):
        """
        Aplicar configuración a un cliente conectado
        """
        if not self.main_app or not self.main_app.channel_manager:
            return
        
        try:
            # Convertir gains y pans a dict con int keys
            gains = {}
            for k, v in config.get('gains', {}).items():
                gains[int(k)] = float(v)
            
            pans = {}
            for k, v in config.get('pans', {}).items():
                pans[int(k)] = float(v)
            
            mutes = {}
            for k, v in config.get('mutes', {}).items():
                mutes[int(k)] = bool(v)
            
            # Aplicar configuración
            self.main_app.channel_manager.update_client_mix(
                client_id,
                channels=config.get('channels', []),
                gains=gains,
                pans=pans,
                mutes=mutes,
                solos=config.get('solos', []),
                pre_listen=config.get('pre_listen'),
                master_gain=config.get('master_gain', 1.0)
            )
            
        except Exception as e:
            logger.error(f"[SceneManager] Error aplicando config: {e}")
    
    def _save_config_for_reconnect(self, client_key, config):
        """
        Guardar configuración para cuando el cliente reconecte
        """
        try:
            # Guardar en persistent_state del native_server
            if self.main_app and self.main_app.native_server:
                with self.main_app.native_server.persistent_lock:
                    self.main_app.native_server.persistent_state[client_key] = {
                        'channels': config.get('channels', []),
                        'gains': config.get('gains', {}),
                        'pans': config.get('pans', {}),
                        'mutes': config.get('mutes', {}),
                        'solos': config.get('solos', []),
                        'pre_listen': config.get('pre_listen'),
                        'master_gain': config.get('master_gain', 1.0),
                        'last_seen': time.time(),
                        'client_type': config.get('client_type', 'native')
                    }
            
            # También guardar en client_config_persistence si existe
            if self.main_app and hasattr(self.main_app, 'config_persistence'):
                ip = client_key.replace('ip_', '')
                self.main_app.config_persistence.save_client_config(
                    address=ip,
                    channels=config.get('channels', []),
                    gains=config.get('gains', {}),
                    pans=config.get('pans', {})
                )
            
        except Exception as e:
            logger.error(f"[SceneManager] Error guardando para reconexión: {e}")
    
    def get_stats(self):
        """Obtener estadísticas del sistema de escenas"""
        try:
            scenes = self.list_scenes()
            
            compatible_count = sum(1 for s in scenes if s['compatible'])
            incompatible_count = len(scenes) - compatible_count
            
            return {
                'total_scenes': len(scenes),
                'compatible_scenes': compatible_count,
                'incompatible_scenes': incompatible_count,
                'scenes_dir': self.scenes_dir
            }
        except:
            return {
                'total_scenes': 0,
                'compatible_scenes': 0,
                'incompatible_scenes': 0,
                'scenes_dir': self.scenes_dir
            }