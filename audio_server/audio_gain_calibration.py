import json
import os
import logging
import numpy as np
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

DEFAULT_GAIN_CONFIG = {
    "headroom_db": -3.0,
    "normalize_by_channel_count": True,
    "soft_clip_threshold": 0.85,
    "soft_clip_enabled": True,
    "max_channel_gain": 0.8,
    "max_master_gain": 0.8,
    "channel_gains": {},
    "rms_target_db": -12.0,
    "rms_warning_db": -3.0,
    "lookahead_samples": 512,
}


class AudioGainCalibration:
    def __init__(self, config_file: str = "audio_gain_config.json"):
        self.config_file = Path(config_file)
        self.lock = Lock()
        self.config = self._load_config()
        self._headroom_linear = None
        self._update_derived_values()
    
    def _load_config(self) -> dict:
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    logger.info(f"[AudioGain] Configuración cargada: {self.config_file}")
                    merged = {**DEFAULT_GAIN_CONFIG, **config}
                    return merged
            except Exception as e:
                logger.error(f"[AudioGain] Error cargando: {e}")
                return DEFAULT_GAIN_CONFIG.copy()
        else:
            logger.info(f"[AudioGain] Creando config default")
            self._save_config(DEFAULT_GAIN_CONFIG)
            return DEFAULT_GAIN_CONFIG.copy()
    
    def _save_config(self, config: dict):
        try:
            os.makedirs(self.config_file.parent, exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            logger.info(f"[AudioGain] Configuración guardada")
        except Exception as e:
            logger.error(f"[AudioGain] Error guardando: {e}")
    
    def _update_derived_values(self):
        headroom_db = self.config.get("headroom_db", -3.0)
        self._headroom_linear = 10.0 ** (headroom_db / 20.0)
        logger.debug(f"[AudioGain] Headroom: {headroom_db}dB = {self._headroom_linear:.3f}")
    
    def get_channel_gain(self, channel_id: int, default: float = 1.0) -> float:
        with self.lock:
            channel_gains = self.config.get("channel_gains", {})
            return float(channel_gains.get(str(channel_id), default))
    
    def set_channel_gain(self, channel_id: int, gain: float):
        with self.lock:
            if "channel_gains" not in self.config:
                self.config["channel_gains"] = {}
            self.config["channel_gains"][str(channel_id)] = gain
            self._save_config(self.config)
            logger.info(f"[AudioGain] Canal {channel_id}: {gain:.3f}")
    
    def get_headroom_factor(self) -> float:
        with self.lock:
            return self._headroom_linear
    
    def get_soft_clip_threshold(self) -> float:
        with self.lock:
            return self.config.get("soft_clip_threshold", 0.85)
    
    def is_soft_clip_enabled(self) -> bool:
        with self.lock:
            return self.config.get("soft_clip_enabled", True)
    
    def should_normalize_by_channel_count(self) -> bool:
        with self.lock:
            return self.config.get("normalize_by_channel_count", True)
    
    def get_max_gain(self, for_master: bool = False) -> float:
        with self.lock:
            if for_master:
                return self.config.get("max_master_gain", 0.8)
            else:
                return self.config.get("max_channel_gain", 0.8)
    
    def validate_rms(self, rms_db: float) -> tuple:
        target = self.config.get("rms_target_db", -12.0)
        warning_threshold = self.config.get("rms_warning_db", -3.0)
        
        if rms_db > warning_threshold:
            return False, f"RMS alto: {rms_db:.1f}dB (máx: {warning_threshold:.1f}dB)"
        return True, None
    
    def reload(self):
        with self.lock:
            self.config = self._load_config()
            self._update_derived_values()
            logger.info("[AudioGain] Recargado")
    
    def to_dict(self) -> dict:
        with self.lock:
            return self.config.copy()


_gain_calibration = None


def init_gain_calibration(config_file: str = "audio_gain_config.json"):
    global _gain_calibration
    _gain_calibration = AudioGainCalibration(config_file)
    return _gain_calibration


def get_gain_calibration() -> AudioGainCalibration:
    global _gain_calibration
    if _gain_calibration is None:
        _gain_calibration = AudioGainCalibration()
    return _gain_calibration