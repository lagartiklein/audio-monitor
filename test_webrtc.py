#!/usr/bin/env python3
"""
Script de prueba corregido para WebRTC
"""

import asyncio
import time
import json
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCDataChannel

async def test_latency_corrected():
    """Prueba de latencia WebRTC corregida"""
    print("⏱️  Probando latencia WebRTC (corregido)...")
    
    pc1 = RTCPeerConnection()
    pc2 = RTCPeerConnection()
    
    latencies = []
    dc_ready = asyncio.Event()
    
    # Configurar DataChannel en pc1
    @pc1.on("datachannel")
    def on_datachannel(channel: RTCDataChannel):
        print(f"  DataChannel creado: {channel.label}")
        
        @channel.on("open")
        def on_open():
            print("  DataChannel abierto")
            dc_ready.set()
        
        @channel.on("message")
        def on_message(message):
            if isinstance(message, str):
                try:
                    data = json.loads(message)
                    if data.get('type') == 'ping':
                        # Responder pong
                        channel.send(json.dumps({
                            'type': 'pong',
                            'timestamp': data['timestamp'],
                            'server_time': time.time()
                        }))
                except:
                    # Mensaje directo de timestamp
                    recv_time = time.time()
                    send_time = float(message)
                    latency = (recv_time - send_time) * 1000
                    latencies.append(latency)
                    print(f"  Latencia: {latency:.2f}ms")
    
    # Crear DataChannel antes de la oferta
    dc = pc1.createDataChannel("latency-test")
    
    @dc.on("open")
    def on_dc_open():
        print("  DC local abierto")
    
    # Establecer conexión
    await pc1.setLocalDescription(await pc1.createOffer())
    offer_dict = {
        'sdp': pc1.localDescription.sdp,
        'type': pc1.localDescription.type
    }
    
    await pc2.setRemoteDescription(RTCSessionDescription(**offer_dict))
    await pc2.setLocalDescription(await pc2.createAnswer())
    
    answer_dict = {
        'sdp': pc2.localDescription.sdp,
        'type': pc2.localDescription.type
    }
    await pc1.setRemoteDescription(RTCSessionDescription(**answer_dict))
    
    # Esperar que el DataChannel esté listo
    print("  Esperando conexión DataChannel...")
    try:
        await asyncio.wait_for(dc_ready.wait(), timeout=5.0)
    except asyncio.TimeoutError:
        print("  ⚠️ Timeout esperando DataChannel")
    
    # Esperar un poco más para estabilizar
    await asyncio.sleep(1)
    
    # Enviar 10 mediciones
    print("  Enviando paquetes de prueba...")
    for i in range(10):
        if dc.readyState == "open":
            dc.send(str(time.time()))
        await asyncio.sleep(0.1)
    
    # Esperar respuestas
    await asyncio.sleep(1)
    
    if latencies:
        avg = sum(latencies) / len(latencies)
        min_lat = min(latencies)
        max_lat = max(latencies)
        print(f"\n📊 Resultados latencia:")
        print(f"  Promedio: {avg:.2f}ms")
        print(f"  Mínima: {min_lat:.2f}ms")
        print(f"  Máxima: {max_lat:.2f}ms")
        print(f"  Muestras: {len(latencies)}")
        
        # Evaluar
        if avg < 50:
            print(f"  ✅ Latencia excelente (<50ms)")
        elif avg < 100:
            print(f"  ⚠️  Latencia aceptable (<100ms)")
        else:
            print(f"  ❌ Latencia muy alta (>100ms)")
    else:
        print("❌ No se recibieron mediciones")
        print("   Posibles causas:")
        print("   1. DataChannel no se abrió correctamente")
        print("   2. Problemas de NAT/Firewall")
        print("   3. Timeout en la conexión")
    
    # Limpiar
    await pc1.close()
    await pc2.close()
    return latencies

async def test_audio_transmission():
    """Prueba transmisión de audio simulada"""
    print("\n🎵 Probando transmisión de audio simulada...")
    
    pc1 = RTCPeerConnection()
    pc2 = RTCPeerConnection()
    
    # Simular track de audio
    from aiortc import MediaStreamTrack
    from av import AudioFrame
    import numpy as np
    
    class TestAudioTrack(MediaStreamTrack):
        kind = "audio"
        
        def __init__(self):
            super().__init__()
            self.counter = 0
            
        async def recv(self):
            # Crear frame de audio de prueba
            samples = 960  # 20ms a 48kHz
            data = np.random.randn(samples, 2).astype(np.float32) * 0.01
            frame = AudioFrame.from_ndarray(data.T, format='fltp', layout='stereo')
            frame.sample_rate = 48000
            frame.time_base = "1/48000"
            frame.pts = self.counter * samples
            self.counter += 1
            return frame
    
    # Agregar track a pc1
    audio_track = TestAudioTrack()
    pc1.addTrack(audio_track)
    
    # Configurar pc2 para recibir
    received_frames = []
    
    @pc2.on("track")
    def on_track(track):
        print(f"  Track recibido: {track.kind}")
        
        async def consume_track():
            for _ in range(10):  # Recibir 10 frames
                try:
                    frame = await track.recv()
                    received_frames.append(frame)
                    print(f"    Frame {len(received_frames)} recibido")
                    await asyncio.sleep(0.02)  # Simular tiempo real
                except Exception as e:
                    print(f"    Error recibiendo frame: {e}")
                    break
        
        asyncio.create_task(consume_track())
    
    # Establecer conexión
    await pc1.setLocalDescription(await pc1.createOffer())
    await pc2.setRemoteDescription(pc1.localDescription)
    await pc2.setLocalDescription(await pc2.createAnswer())
    await pc1.setRemoteDescription(pc2.localDescription)
    
    print("  Esperando transmisión de audio...")
    await asyncio.sleep(1)  # Dar tiempo para transmisión
    
    if received_frames:
        print(f"  ✅ {len(received_frames)} frames de audio recibidos")
    else:
        print("  ❌ No se recibieron frames de audio")
    
    # Limpiar
    await pc1.close()
    await pc2.close()

async def main():
    print("=" * 60)
    print("   PRUEBAS WEBRTC - Audio Monitor (Corregido)")
    print("=" * 60)
    print()
    
    try:
        # Prueba básica
        print("🧪 Probando conexión WebRTC básica...")
        pc1 = RTCPeerConnection()
        pc2 = RTCPeerConnection()
        
        await pc1.setLocalDescription(await pc1.createOffer())
        await pc2.setRemoteDescription(pc1.localDescription)
        await pc2.setLocalDescription(await pc2.createAnswer())
        await pc1.setRemoteDescription(pc2.localDescription)
        
        print("✅ Conexión WebRTC establecida")
        await pc1.close()
        await pc2.close()
        
        # Prueba de latencia
        latencies = await test_latency_corrected()
        
        # Prueba de audio
        await test_audio_transmission()
        
        print("\n" + "=" * 60)
        if latencies and len(latencies) > 0:
            avg_latency = sum(latencies) / len(latencies)
            print(f"✅ Pruebas completadas! Latencia promedio: {avg_latency:.2f}ms")
            if avg_latency < 20:
                print("🎉 ¡Excelente! WebRTC funcionando con latencia óptima")
            elif avg_latency < 50:
                print("👍 Bueno! WebRTC funcionando bien")
            else:
                print("⚠️  Latencia alta, revisa configuración de red")
        else:
            print("⚠️  Pruebas completadas pero sin mediciones de latencia")
        
    except Exception as e:
        print(f"\n❌ Error durante las pruebas: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    asyncio.run(main())