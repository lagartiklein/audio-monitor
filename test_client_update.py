import socketio
import time

def test_client_update():
    """
    Script de prueba para verificar que los clientes conectados (nativos y web) 
    se actualizan correctamente en el servidor y se reflejan en la interfaz web.
    """
    sio = socketio.Client()

    def on_clients_update(data):
        print("\n[TEST] Lista de clientes actualizada:")
        for client in data['clients']:
            print(f"- ID: {client['id']}, Última actividad: {client['last_activity']}")

    def on_connect():
        print("[TEST] Conectado al servidor WebSocket.")
        sio.emit('get_clients')

    def on_disconnect():
        print("[TEST] Desconectado del servidor WebSocket.")

    def on_clients_list(data):
        print("\n[TEST] Lista inicial de clientes:")
        for client in data['clients']:
            print(f"- ID: {client['id']}, Última actividad: {client['last_activity']}")

    # Configurar eventos
    sio.on('clients_update', on_clients_update)
    sio.on('connect', on_connect)
    sio.on('disconnect', on_disconnect)
    sio.on('clients_list', on_clients_list)

    try:
        # Conectar al servidor WebSocket
        sio.connect('http://localhost:5100')

        # Esperar actualizaciones de clientes
        print("[TEST] Esperando actualizaciones de clientes...")
        time.sleep(10)  # Esperar 10 segundos para recibir eventos

    except Exception as e:
        print(f"[TEST] Error: {e}")

    finally:
        sio.disconnect()

if __name__ == "__main__":
    test_client_update()