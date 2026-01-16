# scene_manager.py
import json
import os
import time
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class SceneManager:
    """Gestor centralizado de escenas"""
    
    def __init__(self, scenes_dir: str = "config/scenes"):
        self.scenes_dir = Path(scenes_dir)
        self.scenes_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"[SceneManager] ✅ Inicializado: {self.scenes_dir}")
    
    def validate_scene(self, scene: dict) -> tuple:
        """
        ✅ Validar estructura de escena
        Returns: (is_valid, error_message)
        """
        if not isinstance(scene, dict):
            return False, "Scene must be a dictionary"
        
        required_keys = ['scene_name', 'channels', 'clients']
        missing_keys = [k for k in required_keys if k not in scene]
        
        if missing_keys:
            return False, f"Missing required keys: {missing_keys}"
        
        if not isinstance(scene['channels'], list):
            return False, "Channels must be a list"
        
        if not isinstance(scene['clients'], list):
            return False, "Clients must be a list"
        
        return True, ""
    
    def export_scene(self, filename: str, scene_data: dict) -> tuple:
        """
        ✅ Guardar escena a archivo JSON
        Returns: (success, message)
        """
        try:
            # Validar antes de guardar
            is_valid, error_msg = self.validate_scene(scene_data)
            if not is_valid:
                return False, f"Invalid scene data: {error_msg}"
            
            # Asegurar extensión
            if not filename.endswith('.json'):
                filename += '.json'
            
            filepath = Path(filename)
            filepath.parent.mkdir(parents=True, exist_ok=True)
            
            # Agregar metadatos
            scene_data['exported_at'] = time.strftime('%Y-%m-%dT%H:%M:%S')
            scene_data['schema_version'] = 1
            
            # Guardar archivo
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(scene_data, f, indent=2, ensure_ascii=False)
            
            msg = f"✅ Scene saved: {filepath.name} ({len(scene_data.get('clients', []))} clients)"
            logger.info(f"[SceneManager] {msg}")
            return True, msg
        
        except Exception as e:
            msg = f"❌ Error saving scene: {str(e)}"
            logger.error(f"[SceneManager] {msg}")
            return False, msg
    
    def import_scene(self, filename: str) -> tuple:
        """
        ✅ Cargar escena desde archivo JSON
        Returns: (success, scene_data, message)
        """
        try:
            filepath = Path(filename)
            
            if not filepath.exists():
                return False, {}, f"❌ File not found: {filename}"
            
            if not filepath.suffix == '.json':
                return False, {}, "❌ File must be .json format"
            
            # Cargar archivo
            with open(filepath, 'r', encoding='utf-8') as f:
                scene_data = json.load(f)
            
            # Validar estructura
            is_valid, error_msg = self.validate_scene(scene_data)
            if not is_valid:
                return False, {}, f"❌ Invalid scene format: {error_msg}"
            
            msg = f"✅ Scene loaded: {filepath.name} ({len(scene_data.get('clients', []))} clients)"
            logger.info(f"[SceneManager] {msg}")
            return True, scene_data, msg
        
        except json.JSONDecodeError as e:
            msg = f"❌ Invalid JSON: {str(e)}"
            logger.error(f"[SceneManager] {msg}")
            return False, {}, msg
        except Exception as e:
            msg = f"❌ Error loading scene: {str(e)}"
            logger.error(f"[SceneManager] {msg}")
            return False, {}, msg