import sys, signal, threading, time, socket, argparse, os, webbrowser

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "localhost"

def run_dual_mode():
    print("Starting DUAL mode...")
    from audio_server.audio_capture import AudioCapture
    from audio_server.channel_manager import ChannelManager
    from audio_server.native_server import NativeAudioServer
    from audio_server.audio_broadcaster import AudioBroadcaster
    from audio_server.websocket_server import app, socketio, init_server, start_audio_thread
    
    import config
    import eventlet
    
    audio_capture = None
    native_server = None
    broadcaster = None
    
    def cleanup():
        if broadcaster: broadcaster.stop()
        if native_server: native_server.stop()
        if audio_capture: audio_capture.stop_capture()
    
    signal.signal(signal.SIGINT, lambda sig, frame: (print("Stopping..."), cleanup(), sys.exit(0)))
    
    try:
        audio_capture = AudioCapture()
        devices = audio_capture.list_devices()
        if not devices: return 1
        
        num_channels = audio_capture.start_capture(devices[0]['id'])
        channel_manager = ChannelManager(num_channels)
        
        broadcaster = AudioBroadcaster(audio_capture)
        broadcaster.start()
        
        web_audio_queue = broadcaster.register_consumer("websocket")
        native_audio_queue = broadcaster.register_consumer("native")
        
        native_server = NativeAudioServer(audio_capture, channel_manager)
        native_server.use_broadcaster = True
        native_server.audio_queue = native_audio_queue
        native_server.start()
        
        init_server(audio_capture, channel_manager, web_audio_queue)
        start_audio_thread()
        
        local_ip = get_local_ip()
        print(f"\n{'='*60}\nDUAL MODE READY\nNative: {local_ip}:{config.NATIVE_PORT}\nWeb: http://{local_ip}:{config.WEB_PORT}\nChannels: {num_channels}\n{'='*60}\n")
        
        threading.Thread(target=lambda: (time.sleep(2), webbrowser.open(f"http://localhost:{config.WEB_PORT}")), daemon=True).start()
        if __name__ == '__main__':
            socketio.run(app, host=config.WEB_HOST, port=config.WEB_PORT, debug=False)
        
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

def main():
    parser = argparse.ArgumentParser(description='Audio Server')
    parser.add_argument('--mode', choices=['web', 'native', 'dual'], default='dual')
    parser.add_argument('--verbose', '-v', action='store_true')
    args = parser.parse_args()
    
    if args.verbose:
        import config
        config.VERBOSE = True
    
    return run_dual_mode()

if __name__ == '__main__':
    sys.exit(main() or 0)