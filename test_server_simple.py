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
        logger.info("✅ All imports successful")
        return True
    except Exception as e:
        logger.error(f"❌ Import error: {e}")
        return False

def test_channel_manager():
    """Probar ChannelManager"""
    logger.info("Testing ChannelManager...")
    try:
        from audio_server.channel_manager import ChannelManager

        cm = ChannelManager(8)
        logger.info("✅ ChannelManager initialized")

        # Test subscription
        client_id = "test_client"
        success = cm.subscribe_client(client_id, [0, 1, 2], {0: 1.0, 1: 0.8}, {}, "test")
        if success:
            logger.info("✅ Client subscribed")
        else:
            logger.error("❌ Client subscription failed")
            return False

        # Test get subscription
        sub = cm.get_client_subscription(client_id)
        if sub and len(sub['channels']) == 3:
            logger.info("✅ Subscription retrieved")
        else:
            logger.error("❌ Subscription retrieval failed")
            return False

        # Test gain update
        cm.update_client_gain(client_id, 0, 0.7)
        sub = cm.get_client_subscription(client_id)
        if sub['gains'][0] == 0.7:
            logger.info("✅ Gain updated")
        else:
            logger.error("❌ Gain update failed")
            return False

        # Test unsubscribe
        cm.unsubscribe_client(client_id)
        sub = cm.get_client_subscription(client_id)
        if sub is None:
            logger.info("✅ Client unsubscribed")
        else:
            logger.error("❌ Client unsubscribe failed")
            return False

        return True

    except Exception as e:
        logger.error(f"❌ ChannelManager test error: {e}")
        return False

def test_native_protocol():
    """Probar protocolo nativo"""
    logger.info("Testing native protocol...")
    try:
        from audio_server.native_protocol import NativeAndroidProtocol

        protocol = NativeAndroidProtocol()

        # Test message serialization
        msg = {
            'type': 'handshake',
            'persistent_id': 'test_device',
            'channels': [0, 1]
        }

        data = protocol.serialize_message(msg)
        if data:
            logger.info("✅ Message serialized")
        else:
            logger.error("❌ Message serialization failed")
            return False

        # Test deserialization
        parsed = protocol.deserialize_message(data)
        if parsed['type'] == 'handshake':
            logger.info("✅ Message deserialized")
        else:
            logger.error("❌ Message deserialization failed")
            return False

        return True

    except Exception as e:
        logger.error(f"❌ Native protocol test error: {e}")
        return False

def test_persistence():
    """Probar persistencia de estado"""
    logger.info("Testing persistence...")
    try:
        from audio_server.websocket_server import web_persistent_state, web_persistent_lock

        # Simulate saving state
        persistent_id = "test_127.0.0.1_TestBrowser"
        test_state = {
            'channels': [0, 1, 2],
            'gains': {0: 1.0, 1: 0.8, 2: 0.6},
            'pans': {0: 0.0, 1: 0.0, 2: 0.0},
            'saved_at': time.time()
        }

        with web_persistent_lock:
            web_persistent_state[persistent_id] = test_state

        # Verify state saved
        with web_persistent_lock:
            saved = web_persistent_state.get(persistent_id)
            if saved and len(saved['channels']) == 3:
                logger.info("✅ State persisted")
            else:
                logger.error("❌ State persistence failed")
                return False

        # Clean up
        with web_persistent_lock:
            del web_persistent_state[persistent_id]

        return True

    except Exception as e:
        logger.error(f"❌ Persistence test error: {e}")
        return False

def main():
    """Función principal"""
    print("🧪 Fichatech Audio Monitor - Basic Test Suite")
    print("="*50)

    tests = [
        ("Imports", test_imports),
        ("Channel Manager", test_channel_manager),
        ("Native Protocol", test_native_protocol),
        ("Persistence", test_persistence)
    ]

    results = []
    for test_name, test_func in tests:
        logger.info(f"\n--- Running {test_name} ---")
        success = test_func()
        results.append((test_name, success))

    print("\n" + "="*50)
    print("📊 TEST RESULTS")
    print("="*50)

    passed = 0
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {test_name}")
        if success:
            passed += 1

    print("-"*50)
    print(f"📈 Result: {passed}/{len(results)} tests passed")

    if passed == len(results):
        print("🎉 All tests passed!")
        return 0
    else:
        print(f"⚠️ {len(results) - passed} tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())</content>
<parameter name="filePath">c:\audio-monitor\test_server_simple.py