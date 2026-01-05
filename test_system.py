#!/usr/bin/env python
"""
✅ SCRIPT DE TEST - Audio Monitor System
Verifica todos los componentes principales
"""

import requests
import json
import time
import socket
from urllib.error import URLError

print("=" * 60)
print("🧪 TEST SUITE - Audio Monitor System")
print("=" * 60)

# Test 1: ✅ Server Web
print("\n[TEST 1] 🌐 Web Server Status")
try:
    r = requests.get('http://localhost:5000', timeout=5)
    if r.status_code == 200:
        print("✅ Web Server: OK (200)")
        print(f"   Content-Type: {r.headers.get('Content-Type', 'N/A')}")
    else:
        print(f"❌ Web Server: Status {r.status_code}")
except Exception as e:
    print(f"❌ Web Server: {e}")

# Test 2: ✅ WebSocket Server
print("\n[TEST 2] 🔌 WebSocket Server Status")
try:
    r = requests.get('http://localhost:5000/socket.io/', timeout=5)
    if r.status_code in [200, 400, 500]:  # Socket.IO puede responder con varios códigos
        print("✅ WebSocket Server: OK")
    else:
        print(f"⚠️ WebSocket Server: Status {r.status_code}")
except Exception as e:
    print(f"❌ WebSocket Server: {e}")

# Test 3: ✅ RF Native Server Port
print("\n[TEST 3] 📡 Native RF Server Port (5101)")
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    result = sock.connect_ex(('127.0.0.1', 5101))
    sock.close()
    if result == 0:
        print("✅ RF Server: Listening on port 5101")
    else:
        print("⚠️ RF Server: Port 5101 not listening (expected if no client)")
except Exception as e:
    print(f"⚠️ RF Server: {e}")

# Test 4: ✅ Audio Capture
print("\n[TEST 4] 🎙️ Audio Capture Status")
try:
    # Intentar obtener info del servidor (si está disponible)
    r = requests.get('http://localhost:5000/api/status', timeout=5)
    if r.status_code == 200:
        data = r.json()
        print(f"✅ Audio System: OK")
        print(f"   Channels: {data.get('channels', 'N/A')}")
        print(f"   Sample Rate: {data.get('sample_rate', 'N/A')} Hz")
    else:
        print(f"⚠️ Status endpoint: {r.status_code}")
except Exception as e:
    print(f"⚠️ Audio Status: {e}")

# Test 5: ✅ File System
print("\n[TEST 5] 📁 File System Check")
import os
try:
    config_dir = 'config'
    frontend_dir = 'frontend'
    audio_dir = 'audio_server'
    
    checks = {
        'config/': os.path.isdir(config_dir),
        'frontend/': os.path.isdir(frontend_dir),
        'audio_server/': os.path.isdir(audio_dir),
        'config/devices.json': os.path.isfile('config/devices.json'),
        'frontend/index.html': os.path.isfile('frontend/index.html'),
    }
    
    for path, exists in checks.items():
        status = "✅" if exists else "❌"
        print(f"   {status} {path}")
        
except Exception as e:
    print(f"❌ File System: {e}")

# Test 6: ✅ Python Modules
print("\n[TEST 6] 📦 Python Dependencies")
required_modules = [
    'flask',
    'flask_socketio',
    'numpy',
    'sounddevice',
    'config',
]

for module in required_modules:
    try:
        __import__(module)
        print(f"   ✅ {module}")
    except ImportError:
        print(f"   ❌ {module} (missing)")

print("\n" + "=" * 60)
print("🧪 TEST SUITE COMPLETED")
print("=" * 60)
print("\n📋 NEXT STEPS:")
print("   1. Open http://localhost:5000 in browser")
print("   2. Select '🎧 Monitor Sonidista' for Master Audio")
print("   3. Click '▶️ Escuchar' to start streaming")
print("   4. Connect Android client to RF server (5101)")
print("   5. Test channel changes on both Web and Android")
print("\n")
