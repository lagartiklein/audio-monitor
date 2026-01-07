import customtkinter as ctk
import threading
import time
import sounddevice as sd
import queue
from datetime import datetime
import os
import psutil
import webbrowser
import sys
from PIL import Image
import math
import socket

def get_resource_path(relative_path):
    """ Obtiene la ruta absoluta al recurso, funciona para dev y para PyInstaller """
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        # No se está ejecutando con PyInstaller
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

DEFAULT_SAMPLE_RATE = 48000
DEFAULT_BLOCKSIZE = 128

# Configurar apariencia de CustomTkinter
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class AudioMonitorGUI:
    def __init__(self, main_app):
        self.main_app = main_app
        self.root = ctk.CTk()
        self.root.title("Fichatech Retro")
        
        # Ventana más pequeña al iniciar
        self.root.update_idletasks()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        # Calcular dimensiones un poco más grandes (65% de la pantalla, min 850x600)
        window_width = max(int(screen_width * 0.65), 850)
        window_height = max(int(screen_height * 0.65), 600)

        # Limitar a pantalla completa como máximo
        window_width = min(window_width, screen_width)
        window_height = min(window_height, screen_height)

        # Centrar en pantalla
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.root.minsize(700, 500)  # Tamaño mínimo más grande
        
        # Establecer icono
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
        
        # Animación
        self.animation_frame = 0
        self.pulse_alpha = 0
        self.pulse_direction = 1
        
        # Variables de dispositivo
        devices = list(sd.query_devices())
        self.all_devices = devices  # Guardar lista completa para el selector
        input_devices = [(i, d) for i, d in enumerate(devices) if isinstance(d, dict) and d.get('max_input_channels', 0) > 0]
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
        
        # Iniciar animación
        self.animate()
    
    def setup_colors(self):
        """Paleta de colores revolucionaria"""
        # Fondo ultra oscuro
        self.bg_dark = "#0a0a0f"
        self.bg_card = "#12121a"
        self.bg_card_hover = "#1a1a28"
        
        # Acentos vibrantes
        self.accent_primary = "#00d9ff"    # Cyan eléctrico
        self.accent_secondary = "#ff006e"  # Magenta brillante
        self.accent_success = "#00ff87"    # Verde neón
        self.accent_warning = "#ffbd00"    # Amarillo oro
        self.accent_error = "#ff3838"      # Rojo intenso
        
        # Gradientes
        self.gradient_start = "#667eea"
        self.gradient_end = "#764ba2"
        
        # Textos
        self.text_primary = "#ffffff"
        self.text_secondary = "#a0aec0"
        self.text_muted = "#4a5568"
    
    def setup_ui(self):
        """Configurar interfaz revolucionaria y responsiva"""
        # Frame principal con fondo oscuro
        main_frame = ctk.CTkFrame(self.root, fg_color=self.bg_dark, corner_radius=0)
        main_frame.pack(fill="both", expand=True)
        
        # Grid layout responsivo
        main_frame.grid_columnconfigure(0, weight=0, minsize=420)  # Sidebar más ancho (antes 300)
        main_frame.grid_columnconfigure(1, weight=1)  # Panel principal expandible
        main_frame.grid_rowconfigure(0, weight=1)
        
        # Panel lateral izquierdo - responsivo
        self.setup_sidebar(main_frame)
        
        # Panel principal derecho
        self.setup_main_panel(main_frame)
    
    def setup_sidebar(self, parent):
        """Panel lateral con controles principales - Responsivo"""
        sidebar = ctk.CTkFrame(parent, fg_color=self.bg_card, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        sidebar.grid_propagate(True)  # Permitir que se ajuste al contenido
        
        # Frame scrollable para dispositivos pequeños
        scroll_frame = ctk.CTkScrollableFrame(sidebar, fg_color=self.bg_card)
        scroll_frame.pack(fill="both", expand=True)
        scroll_frame.grid_columnconfigure(0, weight=1)
        
        # Logo y título con efecto glow (tamaño responsivo)
        logo_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
        logo_frame.pack(pady=(20, 20), padx=20)
        
        # Título principal (tamaño escalable)
        title_label = ctk.CTkLabel(
            logo_frame,
            text="FICHATECH RETRO",
            font=ctk.CTkFont(size=36, weight="bold"),  # Reducido de 52 para mejor escalabilidad
            text_color="#ffe066"
        )
        title_label.pack()
        
        subtitle_label = ctk.CTkLabel(
            logo_frame,
            text="Sistema de monitoreo de audio profesional",
            font=ctk.CTkFont(size=11, weight="bold"),  # Más pequeño y responsivo
            text_color=self.text_secondary
        )
        subtitle_label.pack(pady=(5, 0))
        
        # Separador con gradiente visual
        separator = ctk.CTkFrame(scroll_frame, height=3, fg_color=self.accent_primary)
        separator.pack(fill="x", padx=20, pady=(18, 28))
        
        # Estado del servidor con indicador
        self.setup_server_status(scroll_frame)
        
        # Información del dispositivo
        self.setup_device_info(scroll_frame)
        
        # Botones de control (responsivos)
        self.setup_control_buttons(scroll_frame)
        
        # Footer con link
        footer_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
        footer_frame.pack(pady=20, padx=20)
        
        footer_btn = ctk.CTkButton(
            footer_frame,
            text="🌐 www.cepalabs.cl/fichatech",
            font=ctk.CTkFont(size=10),
            fg_color="transparent",
            hover_color=self.bg_card_hover,
            text_color=self.text_secondary,
            command=lambda: webbrowser.open("https://www.cepalabs.cl/fichatech"),
            height=35
        )
        footer_btn.pack(fill="x")
    
    def setup_server_status(self, parent):
        """Estado del servidor con animación - Responsivo"""
        status_frame = ctk.CTkFrame(parent, fg_color=self.bg_card_hover, corner_radius=15, height=120)
        status_frame.pack(fill="x", padx=20, pady=(0, 15))
        status_frame.pack_propagate(False)
        
        # Contenedor centrado
        content = ctk.CTkFrame(status_frame, fg_color="transparent")
        content.place(relx=0.5, rely=0.5, anchor="center")
        
        # Indicador circular (tamaño responsivo)
        self.status_indicator = ctk.CTkLabel(
            content,
            text="●",
            font=ctk.CTkFont(size=48),  # Reducido de 60 para mejor escala
            text_color=self.text_muted
        )
        self.status_indicator.pack()
        
        # Texto de estado
        self.status_text = ctk.CTkLabel(
            content,
            text="SERVIDOR INACTIVO",
            font=ctk.CTkFont(size=14, weight="bold"),  # Responsivo
            text_color=self.text_muted
        )
        self.status_text.pack(pady=(8, 0))
    
    def setup_device_info(self, parent):
        """Información del dispositivo de audio - Responsivo"""
        device_frame = ctk.CTkFrame(parent, fg_color=self.bg_card_hover, corner_radius=15)
        device_frame.pack(fill="x", padx=20, pady=(0, 15))
        
        # Header
        header = ctk.CTkFrame(device_frame, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(15, 10))
        
        ctk.CTkLabel(
            header,
            text="DISPOSITIVO DE AUDIO",
            font=ctk.CTkFont(size=11, weight="bold"),  # Responsivo
            text_color=self.text_secondary
        ).pack(anchor="w")
        
        # Device name (más compacto)
        self.device_name_label = ctk.CTkLabel(
            device_frame,
            textvariable=self.selected_device_name,
            font=ctk.CTkFont(size=14, weight="bold"),  # Reducido
            text_color=self.text_primary,
            anchor="w"
        )
        self.device_name_label.pack(fill="x", padx=15, pady=(0, 8))
        
        # Specs
        self.device_info_var = ctk.StringVar(value="Canales: -- | Sample Rate: -- Hz")
        device_specs_label = ctk.CTkLabel(
            device_frame,
            textvariable=self.device_info_var,
            font=ctk.CTkFont(size=11),  # Responsivo
            text_color=self.text_secondary,
            anchor="w"
        )
        device_specs_label.pack(fill="x", padx=15, pady=(0, 15))
        
        # Botón para cambiar dispositivo (más compacto)
        self.change_device_btn = ctk.CTkButton(
            device_frame,
            text="CAMBIAR DISPOSITIVO",
            command=self.show_device_selector,
            fg_color=self.bg_dark,
            hover_color="#1a1a28",
            text_color=self.text_primary,
            corner_radius=10,
            height=40,  # Reducido de 45
            font=ctk.CTkFont(size=11, weight="bold"),  # Responsivo
            border_width=2,
            border_color=self.accent_primary
        )
        self.change_device_btn.pack(fill="x", padx=15, pady=(0, 15))
    
    def setup_control_buttons(self, parent):
        """Botones de control principales - Responsivos"""
        buttons_frame = ctk.CTkFrame(parent, fg_color="transparent")
        buttons_frame.pack(fill="x", padx=20, pady=(0, 15))
        
        # Botón de inicio (escalable)
        self.start_btn = ctk.CTkButton(
            buttons_frame,
            text="INICIAR SERVIDOR",
            command=self.start_server,
            fg_color=self.accent_success,
            hover_color="#00cc70",
            text_color="#000000",
            height=50,  # Reducido de 60
            font=ctk.CTkFont(size=14, weight="bold"),  # Responsivo
            corner_radius=15
        )
        self.start_btn.pack(fill="x", pady=(0, 10))
        
        # Botón de detener
        self.stop_btn = ctk.CTkButton(
            buttons_frame,
            text="DETENER SERVIDOR",
            command=self.stop_server,
            fg_color=self.accent_error,
            hover_color="#cc0000",
            text_color=self.text_primary,
            height=50,  # Reducido de 60
            font=ctk.CTkFont(size=14, weight="bold"),  # Responsivo
            corner_radius=15,
            state="disabled"
        )
        self.stop_btn.pack(fill="x", pady=(0, 10))
        
        # Botón de salir (más compacto)
        exit_btn = ctk.CTkButton(
            buttons_frame,
            text="SALIR",
            command=self.on_closing,
            fg_color=self.bg_dark,
            hover_color=self.bg_card_hover,
            text_color=self.text_secondary,
            height=40,  # Reducido de 50
            font=ctk.CTkFont(size=12, weight="bold"),  # Responsivo
            corner_radius=15,
            border_width=2,
            border_color=self.text_muted
        )
        exit_btn.pack(fill="x")
    
    def setup_main_panel(self, parent):
        """Panel principal con estadísticas y logs - Responsivo"""
        main_panel = ctk.CTkFrame(parent, fg_color="transparent")
        main_panel.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        main_panel.grid_rowconfigure(1, weight=1)
        main_panel.grid_columnconfigure(0, weight=1)
        
        # Tarjetas de estadísticas
        self.setup_stats_cards(main_panel)
        
        # Panel de logs
        self.setup_logs_panel(main_panel)
    
    def setup_stats_cards(self, parent):
        """Tarjetas de estadísticas en tiempo real - Responsivas"""
        stats_container = ctk.CTkFrame(parent, fg_color="transparent", height=180)
        stats_container.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        stats_container.grid_columnconfigure((0, 1, 2), weight=1)
        stats_container.grid_propagate(False)
        
        # Tarjeta 1: Clientes RF
        self.rf_card = self.create_stat_card(
            stats_container,
            "CLIENTES RF",
            "0",
            self.accent_primary
        )
        self.rf_card.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        
        # Tarjeta 2: Clientes Web
        self.web_card = self.create_stat_card(
            stats_container,
            "CLIENTES WEB",
            "0",
            self.accent_secondary
        )
        self.web_card.grid(row=0, column=1, sticky="nsew", padx=7)
        
        # Tarjeta 3: Latencia del Servidor
        self.latency_card = self.create_stat_card(
            stats_container,
            "LATENCIA",
            "-- ms",
            self.accent_success
        )
        self.latency_card.grid(row=0, column=2, sticky="nsew", padx=(7, 0))
    
    def create_stat_card(self, parent, title, value, color):
        """Crear tarjeta de estadística - Responsiva"""
        card = ctk.CTkFrame(parent, fg_color=self.bg_card, corner_radius=20)
        
        # Container
        container = ctk.CTkFrame(card, fg_color="transparent")
        container.place(relx=0.5, rely=0.5, anchor="center")
        
        # Título (más compacto)
        title_label = ctk.CTkLabel(
            container,
            text=title,
            font=ctk.CTkFont(size=11, weight="bold"),  # Responsivo
            text_color=self.text_secondary
        )
        title_label.pack(pady=(0, 8))
        
        # Valor grande (escalable)
        value_label = ctk.CTkLabel(
            container,
            text=value,
            font=ctk.CTkFont(size=32, weight="bold"),  # Reducido de 42 para escalabilidad
            text_color=color
        )
        value_label.pack()
        
                # Guardar referencias en diccionario
        if not hasattr(self, 'stat_card_refs'):
            self.stat_card_refs = {}
        self.stat_card_refs[title] = {'value_label': value_label, 'accent_color': color}
        
        return card
    
    def setup_logs_panel(self, parent):
        """Panel de logs mejorado: solo información relevante para el cliente"""
        logs_frame = ctk.CTkFrame(parent, fg_color=self.bg_card, corner_radius=20)
        logs_frame.grid(row=1, column=0, sticky="nsew")
        logs_frame.grid_rowconfigure(1, weight=1)
        logs_frame.grid_columnconfigure(0, weight=1)

        # Header
        header = ctk.CTkFrame(logs_frame, fg_color="transparent", height=60)
        header.grid(row=0, column=0, sticky="ew", padx=30, pady=(25, 0))
        header.grid_propagate(False)

        ctk.CTkLabel(
            header,
            text="ESTADO DEL SERVIDOR",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=self.text_primary
        ).pack(side="left")

        # Indicador de actividad
        self.activity_indicator = ctk.CTkLabel(
            header,
            text="●",
            font=ctk.CTkFont(size=20),
            text_color=self.text_muted
        )
        self.activity_indicator.pack(side="right")

        # Textbox para logs con diseño mejorado
        self.log_text = ctk.CTkTextbox(
            logs_frame,
            corner_radius=15,
            font=ctk.CTkFont(family="Consolas", size=13),
            wrap="word",
            fg_color=self.bg_dark,
            text_color=self.text_primary,
            border_width=0,
            state="disabled"
        )
        self.log_text.grid(row=1, column=0, sticky="nsew", padx=25, pady=(15, 25))
        self.update_logs_panel()

    def update_logs_panel(self):
        """Actualizar la consola de logs con datos relevantes: estabilidad, CPU, RAM, carga, parámetros clave, audio y clientes"""
        import platform
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")

        # Info de sistema
        cpu_percent = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory()
        ram_percent = ram.percent
        ram_used = ram.used // (1024 * 1024)
        ram_total = ram.total // (1024 * 1024)
        getloadavg = getattr(os, "getloadavg", None)
        if getloadavg is not None:
            try:
                load = getloadavg()[0]
            except Exception:
                load = "N/A"
        else:
            load = "N/A"
        uptime = int(time.time() - psutil.boot_time())
        uptime_h = uptime // 3600
        uptime_m = (uptime % 3600) // 60
        uptime_s = uptime % 60
        platform_info = platform.platform()

        # Parámetros clave del servidor
        server_status = "Activo" if getattr(self.main_app, "server_running", False) else "Inactivo"

        # Audio stats
        audio_stats = getattr(self.main_app, "audio_capture", None)
        audio_info = audio_stats.get_stats() if audio_stats and hasattr(audio_stats, "get_stats") else {}

        # Client stats
        channel_manager = getattr(self.main_app, "channel_manager", None)
        client_info = channel_manager.get_stats() if channel_manager and hasattr(channel_manager, "get_stats") else {}

        # Server stats
        native_server = getattr(self.main_app, "native_server", None)
        server_info = native_server.get_stats() if native_server and hasattr(native_server, "get_stats") else {}

        # Obtener IP local
        import socket
        def get_local_ip():
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
            except Exception:
                ip = "127.0.0.1"
            finally:
                s.close()
            return ip

        ip_local = get_local_ip()

        # Compose log
        log_lines = [
            f"IP local del servidor: {ip_local}",
            "Para conectarse desde otro dispositivo, ingrese esta IP en el cliente web o nativo, asegurándose de estar en la misma red local.",
            f"Ejemplo: http://{ip_local}:PUERTO (reemplace PUERTO por el puerto configurado)",
            "",
            f"Servidor: {server_status}",
            f"Sistema: {platform_info}",
            f"Uptime: {uptime_h:02d}:{uptime_m:02d}:{uptime_s:02d}",
            f"CPU: {cpu_percent:.1f}%",
            f"RAM: {ram_used}MB / {ram_total}MB ({ram_percent:.1f}%)",
            f"Carga: {load}",
            "",
            "--- AUDIO ---",
            f"Canales: {audio_info.get('channels', '-')}  SR: {audio_info.get('sample_rate', '-')} Hz  Blocksize: {audio_info.get('blocksize', '-')}  Latencia: {audio_info.get('latency_ms', '-')} ms",
            f"Callbacks: {audio_info.get('callbacks', '-')}  RT Priority: {audio_info.get('rt_priority', '-')}  VU: {'Sí' if audio_info.get('vu_enabled', False) else 'No'}  VU Interval: {audio_info.get('vu_update_interval', '-')} ms",
            f"Running: {'Sí' if audio_info.get('running', False) else 'No'}",
            "",
            "--- CLIENTES ---",
            f"Total: {client_info.get('total_clients', '-')}  Nativos: {client_info.get('native_clients', '-')}  Web: {client_info.get('web_clients', '-')}  Canales suscritos: {client_info.get('total_channels_subscribed', '-')}  Canales disponibles: {client_info.get('available_channels', '-')} ",
            "",
            "--- PROCESAMIENTO ---",
            f"Paquetes enviados: {server_info.get('packets_sent', '-')}  Paquetes perdidos: {server_info.get('packets_dropped', '-')}  Bytes enviados: {server_info.get('bytes_sent', '-')}  Uptime servidor: {server_info.get('uptime', '-')} s",
            f"Clientes conectados: {server_info.get('active_clients', '-')}  Estados cacheados: {server_info.get('cached_states', '-')}"
        ]
        self.log_text.insert("end", "\n".join(log_lines))
        self.log_text.configure(state="disabled")

        # Refrescar cada 2 segundos
        self.root.after(2000, self.update_logs_panel)
    
    def animate(self):
        """Animación continua de elementos"""
        if not self.running:
            return

        # Animar indicador de actividad si el servidor está activo
        if self.main_app.server_running:
            self.animation_frame += 1
            # Blink effect: smoothly fade between green and transparent
            blink_speed = 0.15
            alpha = (math.sin(self.animation_frame * blink_speed) + 1) / 2  # 0..1
            # Interpolate color between bg and green
            def blend(c1, c2, t):
                c1 = c1.lstrip('#'); c2 = c2.lstrip('#')
                r1, g1, b1 = int(c1[0:2],16), int(c1[2:4],16), int(c1[4:6],16)
                r2, g2, b2 = int(c2[0:2],16), int(c2[2:4],16), int(c2[4:6],16)
                r = int(r1 + (r2 - r1) * t)
                g = int(g1 + (g2 - g1) * t)
                b = int(b1 + (b2 - b1) * t)
                return f'#{r:02x}{g:02x}{b:02x}'
            color = blend(self.bg_card, self.accent_success, alpha)
            self.activity_indicator.configure(text_color=color)
        else:
            self.activity_indicator.configure(text_color=self.text_muted)

        # Continuar animación
        self.root.after(50, self.animate)
    
    def show_device_selector(self):
        """Mostrar selector de dispositivos mejorado"""
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Seleccionar Interfaz de Audio")
        # Ventana de selección de dispositivo más pequeña
        dialog.geometry("600x400")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(fg_color=self.bg_dark)
        
        # Frame principal
        main_container = ctk.CTkFrame(
            dialog,
            fg_color=self.bg_card,
            corner_radius=20,
            border_width=2,
            border_color=self.accent_primary
        )
        main_container.pack(fill="both", expand=True, padx=20, pady=20)
        main_container.grid_rowconfigure(1, weight=1)
        main_container.grid_columnconfigure(0, weight=1)
        
        # Header
        header = ctk.CTkFrame(main_container, fg_color="transparent", height=80)
        header.grid(row=0, column=0, sticky="ew", padx=30, pady=(30, 20))
        header.grid_propagate(False)
        
        ctk.CTkLabel(
            header,
            text="🎙️ SELECCIONAR INTERFAZ DE AUDIO",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=self.text_primary
        ).pack(side="left")
        
        # Scrollable frame
        scrollable_frame = ctk.CTkScrollableFrame(
            main_container,
            corner_radius=15,
            fg_color=self.bg_dark
        )
        scrollable_frame.grid(row=1, column=0, sticky="nsew", padx=30, pady=(0, 20))
        scrollable_frame.grid_columnconfigure(0, weight=1)
        
        # Cargar dispositivos
        try:
            input_devices = [
                (i, device) for i, device in enumerate(self.all_devices)
                if isinstance(device, dict) and device.get('max_input_channels', 0) > 0
            ]
            input_devices.sort(
                key=lambda d: (
                    d[1].get('max_input_channels', 0),
                    d[1].get('default_samplerate', 0)
                ),
                reverse=True
            )
            
            if not input_devices:
                # Mostrar mensaje si no hay dispositivos
                no_devices_label = ctk.CTkLabel(
                    scrollable_frame,
                    text="⚠️ No se encontraron interfaces de audio de entrada",
                    font=ctk.CTkFont(size=16),
                    text_color=self.accent_warning
                )
                no_devices_label.pack(pady=40)
        except Exception as e:
            # Mostrar error si falla la detección
            error_label = ctk.CTkLabel(
                scrollable_frame,
                text=f"❌ Error al detectar dispositivos: {str(e)}",
                font=ctk.CTkFont(size=16),
                text_color=self.accent_error
            )
            error_label.pack(pady=40)
            input_devices = []
        
        # Crear botones para cada dispositivo
        for i, (device_id, device) in enumerate(input_devices):
            device_frame = ctk.CTkFrame(
                scrollable_frame,
                corner_radius=15,
                fg_color=self.bg_card,
                border_width=2,
                border_color=None
            )
            device_frame.grid(row=i, column=0, pady=10, padx=10, sticky="ew")
            device_frame.grid_columnconfigure(1, weight=1)
            
            # Radio button
            radio = ctk.CTkRadioButton(
                device_frame,
                text="",
                variable=self.device_var,
                value=device_id,
                fg_color=self.accent_primary,
                hover_color=self.accent_secondary
            )
            radio.grid(row=0, column=0, padx=20, pady=20)
            
            # Info frame
            info_frame = ctk.CTkFrame(device_frame, fg_color="transparent")
            info_frame.grid(row=0, column=1, sticky="ew", padx=(0, 20), pady=20)
            
            # Nombre
            name_label = ctk.CTkLabel(
                info_frame,
                text=device.get('name', 'Desconocido'),
                font=ctk.CTkFont(size=15, weight="bold"),
                text_color=self.text_primary,
                anchor="w"
            )
            name_label.pack(anchor="w")
            
            # Specs
            in_channels = device.get('max_input_channels', 0)
            samplerate = int(device.get('default_samplerate', DEFAULT_SAMPLE_RATE))
            specs_text = f"🎵 {in_channels} canales  •  📊 {samplerate} Hz"
            if in_channels > 2:
                specs_text += "  •  ⭐ RECOMENDADO"
            
            specs_label = ctk.CTkLabel(
                info_frame,
                text=specs_text,
                font=ctk.CTkFont(size=12),
                text_color=self.text_secondary,
                anchor="w"
            )
            specs_label.pack(anchor="w", pady=(8, 0))
        
        # Botones de acción
        button_frame = ctk.CTkFrame(main_container, fg_color="transparent", height=80)
        button_frame.grid(row=2, column=0, sticky="ew", padx=30, pady=(0, 30))
        button_frame.grid_columnconfigure((0, 1), weight=1)
        button_frame.grid_propagate(False)
        
        def on_select():
            device_id = self.device_var.get()
            if device_id == -1:
                self.log_message("❌ Por favor selecciona un dispositivo", 'ERROR')
                return
            self.update_device_display(device_id)
            self.log_message(f"✅ Dispositivo seleccionado: {self.selected_device_name.get()}", 'SUCCESS')
            dialog.destroy()
        
        def on_cancel():
            dialog.destroy()
        
        select_btn = ctk.CTkButton(
            button_frame,
            text="✅ SELECCIONAR",
            command=on_select,
            fg_color=self.accent_success,
            hover_color="#00cc70",
            text_color="#000000",
            height=50,
            font=ctk.CTkFont(size=16, weight="bold"),
            corner_radius=12
        )
        select_btn.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        
        cancel_btn = ctk.CTkButton(
            button_frame,
            text="❌ CANCELAR",
            command=on_cancel,
            fg_color=self.bg_dark,
            hover_color=self.bg_card_hover,
            text_color=self.text_primary,
            height=50,
            font=ctk.CTkFont(size=16, weight="bold"),
            corner_radius=12,
            border_width=2,
            border_color=self.text_muted
        )
        cancel_btn.grid(row=0, column=1, sticky="ew", padx=(10, 0))
        
        # Centrar ventana
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
    
    def update_device_display(self, device_id):
        """Actualizar display del dispositivo"""
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
            self.device_info_var.set(f"🎵 {channels} canales  •  📊 {samplerate} Hz")
            
            if self.main_app.server_running:
                self.log_message(f"⚠️ Dispositivo cambiado. Reinicia el servidor.", 'WARNING')
        except Exception as e:
            self.log_message(f"❌ Error al obtener información: {e}", 'ERROR')
    
    def log_message(self, message, tag='INFO'):
        """Agregar mensaje al log con colores"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        color_map = {
            'SUCCESS': self.accent_success,
            'ERROR': self.accent_error,
            'WARNING': self.accent_warning,
            'INFO': self.accent_primary,
            'RF': self.accent_primary,
            'WEB': self.accent_secondary
        }
        
        color = color_map.get(tag, self.text_primary)
        log_entry = f"[{timestamp}] {message}\n"
        
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
        
        if hasattr(self.main_app, 'start_server_with_device'):
            self.main_app.start_server_with_device(self.selected_device_id)
        
        # Actualizar UI
        self.start_btn.configure(state="disabled", fg_color=self.text_muted)
        self.stop_btn.configure(state="normal", fg_color=self.accent_error)
        self.status_indicator.configure(text_color=self.accent_success)
        self.status_text.configure(
            text="SERVIDOR ACTIVO",
            text_color=self.accent_success
        )
        
        self.log_message("✅ Servidor iniciado correctamente", 'SUCCESS')
        
        # Mostrar IP local y explicación en la consola de logs de la GUI
        import socket
        def get_local_ip():
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
            except Exception:
                ip = "127.0.0.1"
            finally:
                s.close()
            return ip

        ip_local = get_local_ip()
        self.log_message(f"[INFO] Dirección IP local del servidor: {ip_local}", 'INFO')
        self.log_message("[INFO] Para conectarse desde otro dispositivo, ingrese esta IP en el cliente web o nativo, asegurándose de estar en la misma red local.", 'INFO')
        self.log_message(f"[INFO] Ejemplo: http://{ip_local}:PUERTO (reemplace PUERTO por el puerto configurado)", 'INFO')
    
    def stop_server(self):
        """Detener el servidor"""
        if hasattr(self.main_app, 'stop_server'):
            self.main_app.stop_server()
        
        # Actualizar UI
        self.start_btn.configure(state="normal", fg_color=self.accent_success)
        self.stop_btn.configure(state="disabled", fg_color=self.text_muted)
        self.status_indicator.configure(text_color=self.text_muted)
        self.status_text.configure(
            text="SERVIDOR INACTIVO",
            text_color=self.text_muted
        )
        
        self.log_message("🛑 Servidor detenido", 'WARNING')
    
    def start_updates(self):
        """Iniciar thread de actualización"""
        self.update_thread = threading.Thread(target=self.update_stats_loop, daemon=True)
        self.update_thread.start()
    
    def update_stats_loop(self):
        """Loop de actualización de estadísticas"""
        while self.running:
            try:
                stats = {}
                if hasattr(self.main_app, 'get_current_stats'):
                    stats = self.main_app.get_current_stats()
                
                while not self.stats_queue.empty():
                    msg = self.stats_queue.get_nowait()
                    self.root.after(0, self.log_message, msg[0], msg[1])
                
                # Actualizar tarjetas
                self.root.after(0, self.update_stat_cards, stats)
            except Exception:
                pass
            
            time.sleep(0.1)
    
    def update_stat_cards(self, stats):
        """Actualizar tarjetas de estadísticas"""
        try:
            # Actualizar valores
            clients_rf = stats.get('clients_rf', 0)
            clients_web = stats.get('clients_web', 0)
            latency_ms = stats.get('latency_ms', 0.0)
            
            self.stat_card_refs['CLIENTES RF']['value_label'].configure(text=str(clients_rf))
            self.stat_card_refs['CLIENTES WEB']['value_label'].configure(text=str(clients_web))
            self.stat_card_refs['LATENCIA']['value_label'].configure(text=f"{latency_ms:.1f} ms")
        except Exception:
            pass
    
    def queue_log_message(self, message, tag='INFO'):
        """Agregar mensaje al log desde otros threads"""
        self.stats_queue.put((message, tag))
    
    def initialize_stats_banner(self):
        """Inicializar banner de estadísticas"""
        pass
    
    def on_closing(self):
        """Manejar cierre de la ventana"""
        self.running = False
        if hasattr(self.main_app, 'cleanup'):
            self.main_app.cleanup()
        self.root.destroy()
    
    def run(self):
        """Ejecutar la GUI"""
        self.start_updates()
        self.root.mainloop()