#!/usr/bin/env python3
"""
TEST SCRIPT - Fichatech Audio Monitor Server
Pruebas básicas de funcionalidad
"""

import sys
import os
import time
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO, format='[TEST] %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Agregar path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Probar importaciones"""
    logger.info("Testing imports...")
    try:
        from audio_server.channel_manager import ChannelManager
        from audio_server.native_server import NativeAudioServer
        from audio_server.websocket_server import app, socketio
        import config
        logger.info("All imports successful")
        return True
    except Exception as e:
        logger.error(f"Import error: {e}")
        return False

def main():
    """Funcion principal"""
    print("Fichatech Audio Monitor - Basic Test Suite")
    print("="*50)

    tests = [
        ("Imports", test_imports),
    ]

    results = []
    for test_name, test_func in tests:
        logger.info(f"\n--- Running {test_name} ---")
        success = test_func()
        results.append((test_name, success))

    print("\n" + "="*50)
    print("TEST RESULTS")
    print("="*50)

    passed = 0
    for test_name, success in results:
        status = "PASS" if success else "FAIL"
        print(f"{status} - {test_name}")
        if success:
            passed += 1

    print("-"*50)
    print(f"Result: {passed}/{len(results)} tests passed")

    if passed == len(results):
        print("All tests passed!")
        return 0
    else:
        print(f"{len(results) - passed} tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())