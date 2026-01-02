import customtkinter as ctk
import threading
import time
import sounddevice as sd
import queue
from datetime import datetime
import os
import webbrowser
import sys
from PIL import Image

def get_resource_path(relative_path):
    """ Obtiene la ruta absoluta al recurso, funciona para dev y para PyInstaller """
    try:
        # PyInstaller crea una carpeta temporal y guarda la ruta en _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

DEFAULT_SAMPLE_RATE = 48000  # Tasa de muestreo por defecto
DEFAULT_BLOCKSIZE = 128

# Configurar apariencia de CustomTkinter
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class AudioMonitorGUI:
    def __init__(self, main_app):
        self.main_app = main_app
        self.root = ctk.CTk()
        self.root.title("Fichatech Monitor")
        # Centrar ventana en pantalla
        width, height = 1000, 800
        self.root.geometry(f"{width}x{height}")
        self.root.update_idletasks()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        
        # Establecer icono de la ventana
        try:
            self.root.iconbitmap(get_resource_path("assets/icono.ico"))
        except Exception as e:
            print(f"No se pudo cargar el icono: {e}")
        
        # Variables de estado
        self.running = True
        self.update_thread = None
        self.stats_queue = queue.Queue()
        self.stats_line_count = 4
        self.last_stats_snapshot = {
            'timestamp': time.time(),
            'packets_sent': 0
        }
        
        # Variables de dispositivo
        devices = list(sd.query_devices())
        input_devices = [(i, d) for i, d in enumerate(devices) if isinstance(d, dict) and d.get('max_input_channels', 0) > 0]
        # Ordenar por número de canales y sample rate
        input_devices.sort(key=lambda d: (d[1].get('max_input_channels', 0), d[1].get('default_samplerate', 0)), reverse=True)
        if input_devices:
            best_id, best_device = input_devices[0]
            self.selected_device_id = best_id
            self.selected_device_name = ctk.StringVar(value=best_device.get('name', 'Desconocido'))
            self.device_var = ctk.IntVar(value=best_id)
        else:
            self.selected_device_id = -1
            self.selected_device_name = ctk.StringVar(value="No seleccionado")
            self.device_var = ctk.IntVar(value=-1)
        
        # Configurar colores
        self.setup_colors()
        
        # Inicializar interfaz
        self.setup_ui()
        
        # Configurar cierre
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def setup_colors(self):
        """Configurar paleta de colores moderna"""
        self.success_color = "#2ecc71"
        self.error_color = "#e74c3c"
        self.warning_color = "#f39c12"
        self.info_color = "#3498db"
        self.accent_color = "#9b59b6"
        self.web_color = "#1abc9c"
    
    def setup_ui(self):
        """Configurar elementos de la interfaz"""
        # Frame principal con padding
        main_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Configurar grid
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(2, weight=1)
        
        # Encabezado con logo y título
        self.setup_header(main_frame)
        
        # Frame de estado actual
        self.setup_status_frame(main_frame)
        
        # Frame de logs
        self.setup_logs_frame(main_frame)
        
        # Frame de controles
        self.setup_controls_frame(main_frame)
        
        # Iniciar actualización de estadísticas
        self.start_updates()
    
    def setup_header(self, parent):
        """Configurar encabezado moderno"""
        header_frame = ctk.CTkFrame(parent, corner_radius=15)
        header_frame.grid(row=0, column=0, pady=(0, 15), sticky="ew")
        header_frame.grid_columnconfigure(1, weight=1)
        
        # Logo/Icono
        try:
            logo_image = ctk.CTkImage(
                light_image=Image.open(get_resource_path("assets/icon.png")), 
                dark_image=Image.open(get_resource_path("assets/icon.png")),
                size=(120,120)
            )
            logo_label = ctk.CTkLabel(header_frame,
                                      image=logo_image,
                                      text="",
                                      width=80, height=80)
        except Exception as e:
            print(f"No se pudo cargar el logo: {e}")
            logo_label = ctk.CTkLabel(header_frame, text="📻", font=("Segoe UI Emoji", 48))
            
        logo_label.grid(row=0, column=0, rowspan=2, padx=40, pady=10, sticky="w")
        
        # Título y subtítulo
        title_label = ctk.CTkLabel(header_frame,
                   text="FICHATECH MONITOR",
                   font=ctk.CTkFont(size=38, weight="bold"),
                   anchor="center")
        title_label.grid(row=0, column=1, sticky="ew", pady=(20, 0))

        subtitle_button = ctk.CTkButton(header_frame,
                text="Streaming de audio multicanal en tiempo real - www.cepalabs.cl/fichatech",
                font=ctk.CTkFont(size=13),
                fg_color="transparent",
                hover_color="gray20",
                text_color="gray70",
                command=lambda: webbrowser.open("https://www.cepalabs.cl/fichatech"))
        subtitle_button.grid(row=1, column=1, sticky="ew", pady=(0, 5))
        
        # Estado del servidor
        self.server_status_label = ctk.CTkLabel(header_frame,
                                               text="● Servidor detenido",
                                               font=ctk.CTkFont(size=14, weight="bold"),
                                               text_color=self.error_color)
        self.server_status_label.grid(row=0, column=2, rowspan=2, padx=20, pady=20)
    
    def setup_status_frame(self, parent):
        """Frame de estado actual modernizado"""
        status_frame = ctk.CTkFrame(parent, corner_radius=15)
        status_frame.grid(row=1, column=0, pady=(0, 15), sticky="ew")
        status_frame.grid_columnconfigure((0, 1), weight=1)
        
        # Label de sección
        section_label = ctk.CTkLabel(status_frame,
                                     text="📊 DISPOSITIVO DE AUDIO",
                                     font=ctk.CTkFont(size=12, weight="bold"),
                                     text_color="gray60")
        section_label.grid(row=0, column=0, columnspan=2, pady=(15, 10), padx=20, sticky="w")
        
        # Frame de dispositivo seleccionado
        device_info_frame = ctk.CTkFrame(status_frame, corner_radius=10)
        device_info_frame.grid(row=1, column=0, padx=20, pady=(0, 15), sticky="ew")
        
        # Icono y nombre del dispositivo
        device_icon = ctk.CTkLabel(device_info_frame,
                                   text="🎙️",
                                   font=ctk.CTkFont(size=24))
        device_icon.pack(side="left", padx=15, pady=15)
        
        device_details = ctk.CTkFrame(device_info_frame, fg_color="transparent")
        device_details.pack(side="left", fill="both", expand=True, padx=(0, 15), pady=15)
        
        self.device_name_label = ctk.CTkLabel(device_details,
                                             textvariable=self.selected_device_name,
                                             font=ctk.CTkFont(size=14, weight="bold"),
                                             anchor="w")
        self.device_name_label.pack(anchor="w")
        
        self.device_info_var = ctk.StringVar(value="Canales: -- | Sample Rate: -- Hz")
        device_specs_label = ctk.CTkLabel(device_details,
                                         textvariable=self.device_info_var,
                                         font=ctk.CTkFont(size=12),
                                         text_color="gray70",
                                         anchor="w")
        device_specs_label.pack(anchor="w", pady=(5, 0))
        
        # Botón para cambiar dispositivo
        self.change_device_btn = ctk.CTkButton(status_frame,
                                              text="🔄 Cambiar Dispositivo",
                                              command=self.show_device_selector,
                                              corner_radius=10,
                                              height=40,
                                              font=ctk.CTkFont(size=13, weight="bold"))
        self.change_device_btn.grid(row=1, column=1, padx=20, pady=(0, 15), sticky="ew")
    
    def show_device_selector(self):
        """Mostrar selector de dispositivos en ventana modal"""
        # Crear ventana modal
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Seleccionar Interfaz de Audio")
        dialog.geometry("800x600")
        dialog.transient(self.root)
        dialog.grab_set()

        # Frame principal
        main_container = ctk.CTkFrame(dialog, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=20, pady=20)
        main_container.grid_rowconfigure(1, weight=1)
        main_container.grid_columnconfigure(0, weight=1)

        # Título
        title_label = ctk.CTkLabel(main_container,
                                   text="🎙️ Seleccionar Interfaz de Audio",
                                   font=ctk.CTkFont(size=20, weight="bold"))
        title_label.grid(row=0, column=0, pady=(0, 15), sticky="w")

        # Frame scrollable para dispositivos
        scrollable_frame = ctk.CTkScrollableFrame(main_container, corner_radius=10)
        scrollable_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 15))
        scrollable_frame.grid_columnconfigure(0, weight=1)

        # Cargar dispositivos y ordenarlos por calidad
        devices = list(sd.query_devices())
        input_devices = [
            (i, device) for i, device in enumerate(devices) if isinstance(device, dict) and device.get('max_input_channels', 0) > 0
        ]
        # Ordenar por número de canales y sample rate
        input_devices.sort(key=lambda d: (d[1].get('max_input_channels', 0), d[1].get('default_samplerate', 0)), reverse=True)

        # Crear botones radio para cada dispositivo
        for i, (device_id, device) in enumerate(input_devices):
            device_frame = ctk.CTkFrame(scrollable_frame, corner_radius=10)
            device_frame.grid(row=i, column=0, pady=5, padx=5, sticky="ew")
            device_frame.grid_columnconfigure(1, weight=1)

            # Radio button
            radio = ctk.CTkRadioButton(device_frame,
                                      text="",
                                      variable=self.device_var,
                                      value=device_id)
            radio.grid(row=0, column=0, padx=15, pady=15, sticky="w")

            # Información del dispositivo
            info_frame = ctk.CTkFrame(device_frame, fg_color="transparent")
            info_frame.grid(row=0, column=1, sticky="ew", padx=(0, 15), pady=15)

            # Nombre
            name_label = ctk.CTkLabel(info_frame,
                                     text=device.get('name', 'Desconocido'),
                                     font=ctk.CTkFont(size=13, weight="bold"),
                                     anchor="w")
            name_label.pack(anchor="w")

            # Especificaciones
            channels = device.get('max_input_channels', 0)
            samplerate = int(device.get('default_samplerate', DEFAULT_SAMPLE_RATE))

            specs_text = f"Canales: {channels} | Sample Rate: {samplerate} Hz"
            if channels > 2:
                specs_text += " ⭐"

            specs_label = ctk.CTkLabel(info_frame,
                                      text=specs_text,
                                      font=ctk.CTkFont(size=11),
                                      text_color="gray70",
                                      anchor="w")
            specs_label.pack(anchor="w", pady=(5, 0))

        # Frame de botones
        button_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        button_frame.grid(row=2, column=0, sticky="ew")

        def on_select():
            device_id = self.device_var.get()
            if device_id == -1:
                self.log_message("❌ Por favor selecciona un dispositivo de la lista", 'ERROR')
                return

            self.update_device_display(device_id)
            self.log_message(f"✅ Dispositivo seleccionado: {self.selected_device_name.get()}", 'SUCCESS')
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        def on_refresh():
            dialog.destroy()
            self.show_device_selector()

        select_btn = ctk.CTkButton(button_frame,
                                  text="✅ Seleccionar",
                                  command=on_select,
                                  fg_color=self.success_color,
                                  hover_color="#27ae60",
                                  height=40,
                                  font=ctk.CTkFont(size=13, weight="bold"))
        select_btn.pack(side="left", padx=(0, 10))

        refresh_btn = ctk.CTkButton(button_frame,
                                   text="🔄 Actualizar",
                                   command=on_refresh,
                                   height=40,
                                   font=ctk.CTkFont(size=13, weight="bold"))
        refresh_btn.pack(side="left", padx=(0, 10))

        cancel_btn = ctk.CTkButton(button_frame,
                                  text="❌ Cancelar",
                                  command=on_cancel,
                                  fg_color="gray40",
                                  hover_color="gray30",
                                  height=40,
                                  font=ctk.CTkFont(size=13, weight="bold"))
        cancel_btn.pack(side="right")

        # Centrar ventana
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
    
    def update_device_display(self, device_id):
        """Actualizar display con información del dispositivo"""
        try:
            device_info = sd.query_devices(device_id)
            self.selected_device_id = device_id
            if isinstance(device_info, dict):
                self.selected_device_name.set(device_info.get('name', 'Desconocido'))
                channels = device_info.get('max_input_channels', 0)
                samplerate = int(device_info.get('default_samplerate', DEFAULT_SAMPLE_RATE))
            else:
                self.selected_device_name.set(str(device_info))
                channels = 0
                samplerate = DEFAULT_SAMPLE_RATE
            self.device_info_var.set(f"Canales: {channels} | Sample Rate: {samplerate} Hz")
            
            # Actualizar estadísticas
            if self.main_app.server_running:
                self.log_message(f"⚠️ Dispositivo cambiado. Reinicia el servidor para aplicar cambios.", 'WARNING')
            
        except Exception as e:
            self.log_message(f"❌ Error al obtener información del dispositivo: {e}", 'ERROR')
    
    def setup_logs_frame(self, parent):
        """Frame de logs modernizado"""
        logs_frame = ctk.CTkFrame(parent, corner_radius=15)
        logs_frame.grid(row=2, column=0, pady=(0, 15), sticky="nsew")
        logs_frame.grid_rowconfigure(1, weight=1)
        logs_frame.grid_columnconfigure(0, weight=1)
        
        # Label de sección
        section_label = ctk.CTkLabel(logs_frame,
                                     text="📝 LOGS DEL SISTEMA",
                                     font=ctk.CTkFont(size=12, weight="bold"),
                                     text_color="gray60")
        section_label.grid(row=0, column=0, pady=(15, 10), padx=20, sticky="w")
        
        # Textbox para logs
        self.log_text = ctk.CTkTextbox(logs_frame,
                          corner_radius=10,
                          font=ctk.CTkFont(family="Consolas", size=11),
                          wrap="word")
        self.log_text.grid(row=1, column=0, padx=15, pady=(0, 15), sticky="nsew")
        self.initialize_stats_banner()
    
    def setup_controls_frame(self, parent):
        """Frame de controles modernizado"""
        controls_frame = ctk.CTkFrame(parent, fg_color="transparent")
        controls_frame.grid(row=3, column=0, sticky="ew")
        controls_frame.grid_columnconfigure(1, weight=1)
        
        # Botón de inicio
        self.start_btn = ctk.CTkButton(controls_frame,
                                      text="🚀 Iniciar Servidor",
                                      command=self.start_server,
                                      fg_color=self.success_color,
                                      hover_color="#27ae60",
                                      height=45,
                                      font=ctk.CTkFont(size=14, weight="bold"),
                                      corner_radius=10)
        self.start_btn.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        
        # Botón de detener
        self.stop_btn = ctk.CTkButton(controls_frame,
                                     text="🛑 Detener Servidor",
                                     command=self.stop_server,
                                     fg_color=self.error_color,
                                     hover_color="#c0392b",
                                     height=45,
                                     font=ctk.CTkFont(size=14, weight="bold"),
                                     corner_radius=10,
                                     state="disabled")
        self.stop_btn.grid(row=0, column=1, padx=(0, 10), sticky="ew")
        
        # Botón de salir
        exit_btn = ctk.CTkButton(controls_frame,
                                text="👋 Salir",
                                command=self.on_closing,
                                fg_color="gray40",
                                hover_color="gray30",
                                height=45,
                                font=ctk.CTkFont(size=14, weight="bold"),
                                corner_radius=10)
        exit_btn.grid(row=0, column=2, sticky="ew")
    
    def log_message(self, message, tag='INFO'):
        """Agregar mensaje al log con colores"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Mapear tags a colores
        color_map = {
            'SUCCESS': self.success_color,
            'ERROR': self.error_color,
            'WARNING': self.warning_color,
            'INFO': self.info_color,
            'RF': self.accent_color,
            'WEB': self.web_color
        }
        
        color = color_map.get(tag, "gray70")
        
        # Formatear mensaje con timestamp
        log_entry = f"[{timestamp}] {message}\n"
        
        # Insertar en el textbox
        self.log_text.insert("end", log_entry)
        self.log_text.see("end")
    
    def start_server(self):
        """Iniciar el servidor"""
        if self.selected_device_id == -1:
            self.log_message("❌ Por favor selecciona un dispositivo primero", 'ERROR')
            self.show_device_selector()
            return
        
        device_info = sd.query_devices(self.selected_device_id)
        if isinstance(device_info, dict):
            self.log_message(f"🎙️ Iniciando servidor con: {device_info.get('name', 'Desconocido')}", 'RF')
            self.log_message(f"   Canales: {device_info.get('max_input_channels', 0)}", 'RF')
        else:
            self.log_message(f"🎙️ Iniciando servidor con: {str(device_info)}", 'RF')
            self.log_message(f"   Canales: 0", 'RF')
        
        # Enviar comando al servidor principal
        if hasattr(self.main_app, 'start_server_with_device'):
            self.main_app.start_server_with_device(self.selected_device_id)
        
        # Actualizar estado
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.server_status_label.configure(text="● Servidor ejecutándose", text_color=self.success_color)
        
        self.log_message("✅ Servidor iniciado correctamente", 'SUCCESS')
    
    def stop_server(self):
        """Detener el servidor"""
        # Enviar comando al servidor principal
        if hasattr(self.main_app, 'stop_server'):
            self.main_app.stop_server()
        
        # Actualizar estado
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.server_status_label.configure(text="● Servidor detenido", text_color=self.error_color)
        
        self.log_message("🛑 Servidor detenido", 'WARNING')
    
    def start_updates(self):
        """Iniciar thread de actualización"""
        self.update_thread = threading.Thread(target=self.update_stats_loop, daemon=True)
        self.update_thread.start()
    
    def update_stats_loop(self):
        """Loop de actualización de estadísticas"""
        start_time = time.time()
        
        while self.running:
            try:
                # Obtener estadísticas del servidor principal
                stats = {}
                if hasattr(self.main_app, 'get_current_stats'):
                    stats = self.main_app.get_current_stats()
                
                # Procesar mensajes en cola
                while not self.stats_queue.empty():
                    msg = self.stats_queue.get_nowait()
                    self.root.after(0, self.log_message, msg[0], msg[1])
                
            except Exception as e:
                pass
            
            self.root.after(0, self.update_stats_banner, stats)
            time.sleep(0.5)  # Actualizar cada 500ms
    
    def queue_log_message(self, message, tag='INFO'):
        """Agregar mensaje al log desde otros threads"""
        self.stats_queue.put((message, tag))

    def initialize_stats_banner(self):
        # No hace falta reservar espacio arriba, el banner irá abajo
        self.update_stats_banner({})

    def update_stats_banner(self, stats):
        """Actualizar los parámetros de audio en tiempo real al final del log"""
        now = time.time()
        last = self.last_stats_snapshot
        interval = max(1e-3, now - last.get('timestamp', now))

        packets_sent = stats.get('packets_sent', last.get('packets_sent', 0))
        sent_delta = max(0, packets_sent - last.get('packets_sent', 0))
        clients_rf = max(0, stats.get('clients_rf', 0))
        clients_web = max(0, stats.get('clients_web', 0))
        sample_rate = stats.get('sample_rate', DEFAULT_SAMPLE_RATE)
        blocksize = stats.get('blocksize', DEFAULT_BLOCKSIZE)
        packets_dropped = stats.get('packets_dropped', 0)
        channels = stats.get('channels', 0)
        position = stats.get('position', 0)

        packets_per_second = sample_rate / max(1, blocksize)
        expected_packets = clients_rf * packets_per_second * interval
        load_pct = min(100.0, (sent_delta / expected_packets) * 100) if expected_packets > 0 else 0.0
        total_clients = clients_rf + clients_web
        latency_ms = (blocksize / max(1, sample_rate)) * 1000

        line1 = f"📡 ESTADO AUDIO | Carga: {load_pct:.0f}% | Latencia: {latency_ms:.2f} ms | Clientes totales: {total_clients}"
        line2 = f"   RF: {clients_rf} | Web: {clients_web} | Canales activos: {channels} | Posición: {position:,}"
        line3 = f"   Paquetes RF: {packets_sent:,} sent • {packets_dropped:,} drop | Blocksize: {blocksize} | Sample Rate: {sample_rate} Hz"
        stats_block = f"{line1}\n{line2}\n{line3}\n\n"

        # Eliminar el banner anterior si existe (al final)
        log_content = self.log_text.get("1.0", "end-1c")
        lines = log_content.splitlines()
        # Si el banner ya está al final, lo quitamos
        if len(lines) >= 4 and lines[-4].startswith("📡 ESTADO AUDIO"):
            # Borramos las últimas 4 líneas
            self.log_text.delete(f"end-{self.stats_line_count + 1}l", "end-1c")

        # Insertar el nuevo banner al final
        self.log_text.insert("end", stats_block)
        self.log_text.see("end")

        self.last_stats_snapshot = {
            'timestamp': now,
            'packets_sent': packets_sent
        }
    
    def on_closing(self):
        """Manejar cierre de la ventana"""
        self.running = False
        if hasattr(self.main_app, 'cleanup'):
            self.main_app.cleanup()
        self.root.destroy()
    
    def run(self):
        """Ejecutar la GUI"""
        self.root.mainloop()