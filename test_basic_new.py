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
        logger.error("Import error: {}".format(e))
        return False

def test_channel_manager():
    """Probar ChannelManager"""
    logger.info("Testing ChannelManager...")
    try:
        from audio_server.channel_manager import ChannelManager

        cm = ChannelManager(8)
        logger.info("ChannelManager initialized")

        # Test subscription
        client_id = "test_client"
        success = cm.subscribe_client(client_id, [0, 1, 2], {0: 1.0, 1: 0.8}, {}, "test")
        if success:
            logger.info("Client subscribed")
        else:
            logger.error("Client subscription failed")
            return False

        return True

    except Exception as e:
        logger.error("ChannelManager test error: {}".format(e))
        return False

def main():
    """Funcion principal"""
    print("Fichatech Audio Monitor - Basic Test Suite")
    print("="*50)

    tests = [
        ("Imports", test_imports),
        ("Channel Manager", test_channel_manager)
    ]

    results = []
    for test_name, test_func in tests:
        logger.info("\n--- Running {} ---".format(test_name))
        success = test_func()
        results.append((test_name, success))

    print("\n" + "="*50)
    print("TEST RESULTS")
    print("="*50)

    passed = 0
    for test_name, success in results:
        status = "PASS" if success else "FAIL"
        print("{} - {}".format(status, test_name))
        if success:
            passed += 1

    print("-"*50)
    print("Result: {}/{} tests passed".format(passed, len(results)))

    if passed == len(results):
        print("All tests passed!")
        return 0
    else:
        print("{} tests failed".format(len(results) - passed))
        return 1

if __name__ == "__main__":
    print("Starting main...")
    result = main()
    print("Main returned:", result)
    print("Done")