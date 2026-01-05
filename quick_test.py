import requests
import socket

print("TEST 1: Web Server")
try:
    r = requests.get('http://localhost:5000', timeout=3)
    print(f"✅ Web: {r.status_code}")
except:
    print("❌ Web: Down")

print("\nTEST 2: RF Port 5101")
try:
    s = socket.socket()
    s.settimeout(1)
    s.connect(('127.0.0.1', 5101))
    s.close()
    print("✅ RF: Listening")
except:
    print("⚠️ RF: No client connected")

print("\nTEST 3: Files")
import os
print(f"✅ config/" if os.path.isdir('config') else "❌ config/")
print(f"✅ frontend/" if os.path.isdir('frontend') else "❌ frontend/")
print(f"✅ audio_server/" if os.path.isdir('audio_server') else "❌ audio_server/")

print("\nTEST 4: Modules")
try:
    import flask, flask_socketio, numpy, sounddevice
    print("✅ All modules OK")
except:
    print("❌ Missing modules")

print("\n✅ Basic tests complete!")
