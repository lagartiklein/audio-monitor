import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import time
import sounddevice as sd
import queue
from datetime import datetime
import os

DEFAULT_SAMPLE_RATE = 48000

class AudioMonitorGUI:
    def __init__(self, main_app):
        self.main_app = main_app
        self.root = tk.Tk()
        self.root.title("Fichatech Monitor - Audio RF Server")
        self.root.geometry("1400x900")
        self.root.configure(bg='#0d1117')
        
        # ✅ Establecer ícono de la aplicación
        try:
            icon = tk.PhotoImage(file='frontend/favicon.png')
            self.root.iconphoto(True, icon)
        except Exception as e:
            print(f"⚠️ No se pudo cargar el ícono: {e}")
        
        # Variables de estado
        self.running = True
        self.update_thread = None
        self.stats_queue = queue.Queue()
        
        # Variables de dispositivo
        self.selected_device_id = -1
        self.selected_device_name = tk.StringVar(value="No seleccionado")
        
        # Variables de estadísticas
        self.rf_clients_var = tk.StringVar(value="0")
        self.web_clients_var = tk.StringVar(value="0")
        self.server_status_var = tk.StringVar(value="🔴 Servidor detenido")
        self.packets_sent_var = tk.StringVar(value="0")
        self.packets_dropped_var = tk.StringVar(value="0")
        self.sample_position_var = tk.StringVar(value="0")
        self.uptime_var = tk.StringVar(value="00:00:00")
        
        # Tiempo de inicio del servidor
        self.server_start_time = None
        
        # Variables del mixer
        self.selected_client_index = -1
        self.channel_gain_scales = {}
        self.channel_mute_vars = {}
        
        # Configurar estilo
        self.setup_styles()
        
        # Inicializar interfaz
        self.setup_ui()
        
        # Configurar cierre
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def setup_styles(self):
        """Configurar estilos tkinter con paleta coherente"""
        style = ttk.Style()
        
        # Paleta de colores coherente - GitHub Dark theme
        self.bg_dark = '#0d1117'
        self.bg_medium = '#161b22'
        self.bg_light = '#21262d'
        self.border_color = '#30363d'
        self.text_primary = '#c9d1d9'
        self.text_secondary = '#8b949e'
        self.accent_blue = '#58a6ff'
        self.accent_green = '#3fb950'
        self.accent_red = '#f85149'
        self.accent_yellow = '#d29922'
        self.accent_purple = '#bc8cff'
        self.accent_cyan = '#39c5cf'
        
        style.theme_use('clam')
        
        # Configurar fondo general
        style.configure('.', background=self.bg_medium, foreground=self.text_primary)
        
        # Frame principal
        style.configure('TFrame', background=self.bg_dark)
        
        # Título principal
        style.configure('Title.TLabel', 
                       background=self.accent_blue,
                       foreground='#ffffff',
                       font=('Segoe UI', 20, 'bold'),
                       padding=12)
        
        # LabelFrames
        style.configure('TLabelframe',
                       background=self.bg_medium,
                       bordercolor=self.border_color,
                       borderwidth=1,
                       relief='solid')
        
        style.configure('TLabelframe.Label',
                       background=self.bg_medium,
                       foreground=self.accent_blue,
                       font=('Segoe UI', 9, 'bold'))
        
        # Labels normales
        style.configure('TLabel',
                       background=self.bg_medium,
                       foreground=self.text_secondary,
                       font=('Segoe UI', 9))
        
        # Labels de valores
        style.configure('StatValue.TLabel',
                       background=self.bg_medium,
                       foreground=self.text_primary,
                       font=('Segoe UI', 16, 'bold'))
        
        style.configure('SmallValue.TLabel',
                       background=self.bg_medium,
                       foreground=self.text_primary,
                       font=('Segoe UI', 11, 'bold'))
        
        # Radiobuttons
        style.configure('TRadiobutton',
                       background=self.bg_light,
                       foreground=self.text_primary,
                       font=('Segoe UI', 9))
        
        # Checkbuttons
        style.configure('TCheckbutton',
                       background=self.bg_medium,
                       foreground=self.text_primary,
                       font=('Segoe UI', 9))
        
        # Botones
        style.configure('Green.TButton',
                       background=self.accent_green,
                       foreground='#ffffff',
                       font=('Segoe UI', 10, 'bold'),
                       borderwidth=0,
                       padding=10)
        
        style.map('Green.TButton',
                 background=[('active', '#2ea043')])
        
        style.configure('Red.TButton',
                       background=self.accent_red,
                       foreground='#ffffff',
                       font=('Segoe UI', 10, 'bold'),
                       borderwidth=0,
                       padding=10)
        
        style.map('Red.TButton',
                 background=[('active', '#da3633')])
        
        style.configure('Blue.TButton',
                       background=self.accent_blue,
                       foreground='#ffffff',
                       font=('Segoe UI', 9, 'bold'),
                       borderwidth=0,
                       padding=8)
        
        style.map('Blue.TButton',
                 background=[('active', '#1f6feb')])
        
        style.configure('TButton',
                       background=self.bg_light,
                       foreground=self.text_primary,
                       font=('Segoe UI', 9),
                       borderwidth=1,
                       bordercolor=self.border_color,
                       padding=8)
        
        style.map('TButton',
                 background=[('active', self.border_color)])
    
    def setup_ui(self):
        """Configurar elementos de la interfaz con pestañas"""
        # Crear notebook (pestañas)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))

        # Frame principal (dashboard)
        main_frame = ttk.Frame(self.notebook, padding="12")
        self.notebook.add(main_frame, text="📊 Dashboard")

        # Frame de mixer profesional
        self.mixer_frame = ttk.Frame(self.notebook, padding="0")
        self.notebook.add(self.mixer_frame, text="🎛️ Mixer")

        # ✅ NUEVO: Pestaña de Escenas
        self.scenes_frame = ttk.Frame(self.notebook, padding="12")
        self.notebook.add(self.scenes_frame, text="💾 Escenas")

        # Configurar expansión
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=2)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(2, weight=1)

        # --- Dashboard (principal) ---
        self.setup_header(main_frame)
        self.setup_general_stats(main_frame)

        left_panel = ttk.Frame(main_frame)
        left_panel.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 8))
        left_panel.columnconfigure(0, weight=1)
        left_panel.rowconfigure(1, weight=1)
        self.setup_device_panel(left_panel)
        self.setup_logs_frame(left_panel)

        right_panel = ttk.Frame(main_frame)
        right_panel.grid(row=2, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        right_panel.columnconfigure(0, weight=1)
        right_panel.rowconfigure(0, weight=1)
        self.setup_clients_frame(right_panel)
        self.setup_controls_frame(right_panel)

        # --- Pestaña de mixer profesional ---
        self.setup_professional_mixer_tab(self.mixer_frame)

        # ✅ NUEVO: Setup de pestaña de escenas
        self.setup_scenes_tab(self.scenes_frame)

        # Iniciar actualizaciones
        self.start_updates()

    def setup_professional_mixer_tab(self, parent):
        """✨ Mixer profesional moderno y optimizado"""
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=3)
        parent.rowconfigure(0, weight=1)

        # ============================================================
        # PANEL IZQUIERDO: Lista de clientes
        # ============================================================
        left_panel = ttk.Frame(parent, padding="12")
        left_panel.grid(row=0, column=0, sticky="nsew")
        left_panel.columnconfigure(0, weight=1)
        left_panel.rowconfigure(1, weight=1)

        # Header del panel
        header_frame = tk.Frame(left_panel, bg=self.accent_purple, height=60)
        header_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 12))
        header_frame.grid_propagate(False)

        tk.Label(header_frame, text="🎛️", font=('Segoe UI', 24), 
                bg=self.accent_purple, fg='#ffffff').pack(side=tk.LEFT, padx=(12, 8))
        
        title_frame = tk.Frame(header_frame, bg=self.accent_purple)
        title_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        tk.Label(title_frame, text="AUDIO MIXER", 
                font=('Segoe UI', 16, 'bold'),
                bg=self.accent_purple, fg='#ffffff').pack(anchor=tk.W)
        
        self.mixer_status_var = tk.StringVar(value="0 clientes conectados")
        tk.Label(title_frame, textvariable=self.mixer_status_var,
                font=('Segoe UI', 9),
                bg=self.accent_purple, fg='#e0e0e0').pack(anchor=tk.W)

        # Lista de clientes estilizada
        clients_container = ttk.LabelFrame(left_panel, text="📡 Clientes Conectados", padding="8")
        clients_container.grid(row=1, column=0, sticky="nsew")
        clients_container.columnconfigure(0, weight=1)
        clients_container.rowconfigure(0, weight=1)

        # Canvas con scrollbar para lista personalizada
        canvas_frame = tk.Frame(clients_container, bg=self.bg_medium)
        canvas_frame.grid(row=0, column=0, sticky="nsew")
        canvas_frame.columnconfigure(0, weight=1)
        canvas_frame.rowconfigure(0, weight=1)

        self.clients_canvas = tk.Canvas(canvas_frame, bg=self.bg_light, 
                                       highlightthickness=0, width=280)
        clients_scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", 
                                         command=self.clients_canvas.yview)
        
        self.clients_list_frame = tk.Frame(self.clients_canvas, bg=self.bg_light)
        
        self.clients_canvas.create_window((0, 0), window=self.clients_list_frame, anchor="nw")
        self.clients_canvas.configure(yscrollcommand=clients_scrollbar.set)
        
        self.clients_canvas.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        clients_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

        # Botón de refresh
        ttk.Button(clients_container, text="🔄 Actualizar", 
                  command=self.refresh_mixer_clients,
                  style='Blue.TButton').grid(row=1, column=0, pady=(8, 0), sticky=(tk.W, tk.E))

        # ============================================================
        # PANEL DERECHO: Controles del mixer
        # ============================================================
        right_panel = ttk.Frame(parent, padding="12")
        right_panel.grid(row=0, column=1, sticky="nsew")
        right_panel.columnconfigure(0, weight=1)
        right_panel.rowconfigure(1, weight=1)

        # Info del cliente seleccionado
        info_frame = tk.Frame(right_panel, bg=self.bg_medium, height=80)
        info_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 12))
        info_frame.grid_propagate(False)
        info_frame.columnconfigure(1, weight=1)

        tk.Label(info_frame, text="👤", font=('Segoe UI', 28),
                bg=self.bg_medium, fg=self.accent_blue).grid(row=0, column=0, rowspan=2, 
                                                              padx=(12, 12), pady=12)

        self.selected_client_name_var = tk.StringVar(value="Ningún cliente seleccionado")
        tk.Label(info_frame, textvariable=self.selected_client_name_var,
                font=('Segoe UI', 14, 'bold'),
                bg=self.bg_medium, fg=self.text_primary,
                anchor=tk.W).grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 12), pady=(12, 0))

        self.selected_client_info_var = tk.StringVar(value="Selecciona un cliente para gestionar sus canales")
        tk.Label(info_frame, textvariable=self.selected_client_info_var,
                font=('Segoe UI', 9),
                bg=self.bg_medium, fg=self.text_secondary,
                anchor=tk.W).grid(row=1, column=1, sticky=(tk.W, tk.E), padx=(0, 12), pady=(0, 12))

        # Área de controles con scroll
        controls_container = ttk.LabelFrame(right_panel, text="🎚️ Controles de Canales", padding="8")
        controls_container.grid(row=1, column=0, sticky="nsew")
        controls_container.columnconfigure(0, weight=1)
        controls_container.rowconfigure(0, weight=1)

        # Canvas para scroll
        controls_canvas = tk.Canvas(controls_container, bg=self.bg_medium, 
                                   highlightthickness=0)
        controls_scrollbar = ttk.Scrollbar(controls_container, orient="vertical",
                                          command=controls_canvas.yview)
        
        self.controls_frame = tk.Frame(controls_canvas, bg=self.bg_medium)
        
        controls_canvas.create_window((0, 0), window=self.controls_frame, anchor="nw")
        controls_canvas.configure(yscrollcommand=controls_scrollbar.set)
        
        controls_canvas.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        controls_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

        # Bind para scroll
        self.controls_frame.bind("<Configure>",
            lambda e: controls_canvas.configure(scrollregion=controls_canvas.bbox("all")))

        # Botones de acción rápida
        actions_frame = ttk.Frame(right_panel)
        actions_frame.grid(row=2, column=0, pady=(12, 0), sticky=(tk.W, tk.E))
        actions_frame.columnconfigure(0, weight=1)
        actions_frame.columnconfigure(1, weight=1)
        actions_frame.columnconfigure(2, weight=1)

        ttk.Button(actions_frame, text="✅ Activar Todos", 
                  command=self.mixer_activate_all,
                  style='Green.TButton').grid(row=0, column=0, padx=(0, 4), sticky=(tk.W, tk.E))
        
        ttk.Button(actions_frame, text="❌ Desactivar Todos",
                  command=self.mixer_deactivate_all,
                  style='Red.TButton').grid(row=0, column=1, padx=(4, 4), sticky=(tk.W, tk.E))
        
        ttk.Button(actions_frame, text="🔄 Reset Ganancias",
                  command=self.mixer_reset_gains,
                  style='Blue.TButton').grid(row=0, column=2, padx=(4, 0), sticky=(tk.W, tk.E))

        # Inicializar
        self.refresh_mixer_clients()

    def setup_scenes_tab(self, parent):
        """✨ Pestaña de gestión de escenas"""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        
        # ============================================================
        # PANEL SUPERIOR: Escena actual
        # ============================================================
        current_frame = ttk.LabelFrame(parent, text="📸 Escena Actual", padding="12")
        current_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 12))
        current_frame.columnconfigure(1, weight=1)
        
        # Info de interfaz actual
        tk.Label(current_frame, text="Interfaz:", 
                font=('Segoe UI', 9, 'bold'),
                bg=self.bg_medium, fg=self.text_secondary).grid(row=0, column=0, sticky=tk.W, padx=(0, 8))
        
        self.current_interface_var = tk.StringVar(value="No detectada")
        tk.Label(current_frame, textvariable=self.current_interface_var,
                font=('Segoe UI', 10),
                bg=self.bg_medium, fg=self.text_primary).grid(row=0, column=1, sticky=tk.W)
        
        # Clientes conectados
        tk.Label(current_frame, text="Clientes:", 
                font=('Segoe UI', 9, 'bold'),
                bg=self.bg_medium, fg=self.text_secondary).grid(row=1, column=0, sticky=tk.W, padx=(0, 8), pady=(8, 0))
        
        self.current_clients_var = tk.StringVar(value="0 conectados")
        tk.Label(current_frame, textvariable=self.current_clients_var,
                font=('Segoe UI', 10),
                bg=self.bg_medium, fg=self.text_primary).grid(row=1, column=1, sticky=tk.W, pady=(8, 0))
        
        # Botón guardar nueva escena
        ttk.Button(current_frame, text="💾 Guardar como nueva escena",
                  command=self.show_save_scene_dialog,
                  style='Green.TButton').grid(row=2, column=0, columnspan=2, pady=(12, 0), sticky=(tk.W, tk.E))
        
        # ============================================================
        # PANEL CENTRAL: Lista de escenas
        # ============================================================
        list_frame = ttk.LabelFrame(parent, text="📋 Escenas Guardadas", padding="12")
        list_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(1, weight=1)
        
        # Barra de herramientas
        toolbar = ttk.Frame(list_frame)
        toolbar.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 12))
        toolbar.columnconfigure(0, weight=1)
        
        # Campo de búsqueda
        search_frame = ttk.Frame(toolbar)
        search_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 8))
        
        tk.Label(search_frame, text="🔍",
                bg=self.bg_medium, fg=self.text_secondary).pack(side=tk.LEFT, padx=(0, 4))
        
        self.scene_search_var = tk.StringVar()
        self.scene_search_var.trace('w', lambda *args: self.filter_scenes())
        
        search_entry = ttk.Entry(search_frame, textvariable=self.scene_search_var, width=30)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Botón refrescar
        ttk.Button(toolbar, text="🔄 Refrescar",
                  command=self.refresh_scenes_list,
                  style='Blue.TButton').grid(row=0, column=1)
        
        # Canvas con scroll para lista de escenas
        canvas_frame = ttk.Frame(list_frame)
        canvas_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        canvas_frame.columnconfigure(0, weight=1)
        canvas_frame.rowconfigure(0, weight=1)
        
        self.scenes_canvas = tk.Canvas(canvas_frame, bg=self.bg_light,
                                       highlightthickness=0)
        scenes_scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical",
                                        command=self.scenes_canvas.yview)
        
        self.scenes_list_frame = tk.Frame(self.scenes_canvas, bg=self.bg_light)
        
        self.scenes_canvas.create_window((0, 0), window=self.scenes_list_frame, anchor="nw")
        self.scenes_canvas.configure(yscrollcommand=scenes_scrollbar.set)
        
        self.scenes_canvas.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        scenes_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # Bind para scroll
        self.scenes_list_frame.bind("<Configure>",
            lambda e: self.scenes_canvas.configure(scrollregion=self.scenes_canvas.bbox("all")))
        
        # ============================================================
        # PANEL INFERIOR: Acciones
        # ============================================================
        actions_frame = ttk.LabelFrame(parent, text="⚙️ Acciones", padding="12")
        actions_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(12, 0))
        actions_frame.columnconfigure(0, weight=1)
        actions_frame.columnconfigure(1, weight=1)
        
        ttk.Button(actions_frame, text="📥 Importar escena",
                  command=self.import_scene_dialog).grid(row=0, column=0, padx=(0, 4), sticky=(tk.W, tk.E))
        
        ttk.Button(actions_frame, text="📤 Exportar seleccionada",
                  command=self.export_scene_dialog).grid(row=0, column=1, padx=(4, 0), sticky=(tk.W, tk.E))
        
        # Inicializar lista de escenas
        self.refresh_scenes_list()
        self.update_current_scene_info()

    def refresh_mixer_clients(self):
        """Actualizar lista de clientes en el mixer"""
        # Limpiar lista actual
        for widget in self.clients_list_frame.winfo_children():
            widget.destroy()

        clients = []
        if self.main_app.native_server:
            clients = self.main_app.native_server.get_connected_clients()

        self.mixer_status_var.set(f"{len(clients)} cliente{'s' if len(clients) != 1 else ''} conectado{'s' if len(clients) != 1 else ''}")

        if not clients:
            # Mensaje de no hay clientes
            empty_frame = tk.Frame(self.clients_list_frame, bg=self.bg_light)
            empty_frame.pack(fill=tk.BOTH, expand=True, pady=40)
            
            tk.Label(empty_frame, text="📭", font=('Segoe UI', 48),
                    bg=self.bg_light, fg=self.text_secondary).pack()
            tk.Label(empty_frame, text="No hay clientes conectados",
                    font=('Segoe UI', 11),
                    bg=self.bg_light, fg=self.text_secondary).pack(pady=(8, 0))
            tk.Label(empty_frame, text="Inicia el servidor para ver clientes",
                    font=('Segoe UI', 9),
                    bg=self.bg_light, fg=self.text_secondary).pack(pady=(4, 0))
        else:
            # Crear items de clientes
            for idx, client in enumerate(clients):
                self.create_client_item(idx, client)

        # Actualizar scroll region
        self.clients_list_frame.update_idletasks()
        self.clients_canvas.configure(scrollregion=self.clients_canvas.bbox("all"))

    def create_client_item(self, idx, client):
        """Crear item visual para cliente en la lista"""
        addr = client.get('address', 'Unknown')
        channels = client.get('channels', [])
        packets_sent = client.get('packets_sent', 0)
        
        # Frame del cliente
        is_selected = (idx == self.selected_client_index)
        bg_color = self.accent_blue if is_selected else self.bg_medium
        
        client_frame = tk.Frame(self.clients_list_frame, 
                               bg=bg_color,
                               cursor='hand2',
                               relief=tk.RAISED if is_selected else tk.FLAT,
                               borderwidth=2 if is_selected else 1)
        client_frame.pack(fill=tk.X, padx=4, pady=2)
        
        # Hacer clickeable
        def select_client(event=None):
            self.select_mixer_client(idx, client)
        
        client_frame.bind('<Button-1>', select_client)
        
        # Contenido interno con padding
        inner_frame = tk.Frame(client_frame, bg=bg_color)
        inner_frame.pack(fill=tk.BOTH, padx=8, pady=8)
        
        # Cabecera: IP y estado
        header = tk.Frame(inner_frame, bg=bg_color)
        header.pack(fill=tk.X)
        
        tk.Label(header, text="🔌" if is_selected else "📡",
                font=('Segoe UI', 16),
                bg=bg_color, fg='#ffffff' if is_selected else self.accent_purple).pack(side=tk.LEFT, padx=(0, 8))
        
        info_frame = tk.Frame(header, bg=bg_color)
        info_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        tk.Label(info_frame, text=addr,
                font=('Segoe UI', 10, 'bold'),
                bg=bg_color, fg='#ffffff' if is_selected else self.text_primary,
                anchor=tk.W).pack(fill=tk.X)
        
        tk.Label(info_frame, text=f"{len(channels)} canales • {packets_sent:,} paquetes",
                font=('Segoe UI', 8),
                bg=bg_color, fg='#ffffff' if is_selected else self.text_secondary,
                anchor=tk.W).pack(fill=tk.X)
        
        # Bind a todos los widgets
        for widget in [client_frame, inner_frame, header, info_frame]:
            widget.bind('<Button-1>', select_client)
        for child in info_frame.winfo_children():
            child.bind('<Button-1>', select_client)

    def select_mixer_client(self, idx, client):
        """Seleccionar cliente en el mixer"""
        self.selected_client_index = idx
        addr = client.get('address', 'Unknown')
        channels = client.get('channels', [])
        
        self.selected_client_name_var.set(addr)
        self.selected_client_info_var.set(f"Gestiona los {len(channels)} canales activos de este cliente")
        
        # Actualizar lista visual
        self.refresh_mixer_clients()
        
        # Mostrar controles de canales
        self.show_mixer_channel_controls(client)

    def show_mixer_channel_controls(self, client):
        """Mostrar controles de canales para el cliente seleccionado"""
        # Limpiar controles anteriores
        for widget in self.controls_frame.winfo_children():
            widget.destroy()
        
        self.channel_gain_scales = {}
        self.channel_mute_vars = {}
        
        max_channels = self.main_app.channel_manager.num_channels if self.main_app.channel_manager else 0
        
        if max_channels == 0:
            tk.Label(self.controls_frame, text="⚠️ No hay canales disponibles",
                    font=('Segoe UI', 11),
                    bg=self.bg_medium, fg=self.text_secondary).pack(pady=40)
            return
        
        channels = client.get('channels', [])
        addr = client.get('address', '')
        
        # Crear un canal por fila
        for ch in range(max_channels):
            self.create_channel_strip(ch, ch in channels, addr)

    def create_channel_strip(self, channel, is_active, client_addr):
        """Crear strip de control para un canal individual"""
        # Frame del canal
        strip_frame = tk.Frame(self.controls_frame, 
                              bg=self.bg_light,
                              relief=tk.RAISED,
                              borderwidth=1)
        strip_frame.pack(fill=tk.X, padx=4, pady=4)
        
        # Layout interno
        strip_frame.columnconfigure(1, weight=1)
        
        # Checkbox de activación
        var = tk.BooleanVar(value=is_active)
        self.channel_mute_vars[channel] = var
        
        cb = ttk.Checkbutton(strip_frame, 
                            text=f"CH {channel + 1}",
                            variable=var,
                            command=lambda: self.toggle_mixer_channel(channel, var, client_addr))
        cb.grid(row=0, column=0, padx=(8, 12), pady=8, sticky=tk.W)
        
        # Frame de ganancia
        gain_frame = tk.Frame(strip_frame, bg=self.bg_light)
        gain_frame.grid(row=0, column=1, padx=(0, 8), pady=8, sticky=(tk.W, tk.E))
        gain_frame.columnconfigure(1, weight=1)
        
        # Label de ganancia
        gain_label_var = tk.StringVar(value="1.0x")
        tk.Label(gain_frame, textvariable=gain_label_var,
                font=('Consolas', 9, 'bold'),
                bg=self.bg_light, fg=self.accent_green,
                width=5).grid(row=0, column=0, padx=(0, 8))
        
        # Slider de ganancia
        gain_scale = tk.Scale(gain_frame,
                             from_=0.0, to=2.0,
                             resolution=0.1,
                             orient=tk.HORIZONTAL,
                             bg=self.bg_light,
                             fg=self.text_primary,
                             troughcolor=self.bg_dark,
                             activebackground=self.accent_blue,
                             highlightthickness=0,
                             showvalue=0,
                             length=200)
        gain_scale.set(1.0)
        gain_scale.grid(row=0, column=1, sticky=(tk.W, tk.E))
        
        # Actualizar label cuando cambia
        def update_gain(value):
            gain_label_var.set(f"{float(value):.1f}x")
            self.apply_mixer_gain(channel, float(value), client_addr)
        
        gain_scale.configure(command=update_gain)
        self.channel_gain_scales[channel] = (gain_scale, gain_label_var)
        
        # Indicador visual de nivel (opcional - estático por ahora)
        level_canvas = tk.Canvas(strip_frame, width=40, height=24, 
                                bg=self.bg_dark, highlightthickness=0)
        level_canvas.grid(row=0, column=2, padx=(8, 8))
        
        # Dibujar "medidor" estático
        if is_active:
            level_canvas.create_rectangle(2, 2, 38, 22, fill=self.accent_green, outline='')
        else:
            level_canvas.create_rectangle(2, 2, 38, 22, fill=self.bg_medium, outline='')

    def toggle_mixer_channel(self, channel, var, client_addr):
        """Activar/desactivar canal"""
        if not self.main_app.native_server:
            return
        
        with self.main_app.native_server.client_lock:
            for addr, client_obj in self.main_app.native_server.clients.items():
                addr_str = f"{addr[0]}:{addr[1]}"
                if addr_str == client_addr:
                    if var.get():
                        client_obj.subscribed_channels.add(channel)
                    else:
                        client_obj.subscribed_channels.discard(channel)
                    # Actualizar channel_manager
                    self.main_app.channel_manager.update_client_mix(
                        client_obj.persistent_id, 
                        channels=list(client_obj.subscribed_channels)
                    )
                    break

    def apply_mixer_gain(self, channel, gain, client_addr):
        """Aplicar ganancia a un canal"""
        if not self.main_app.channel_manager or not self.main_app.native_server:
            return
        
        # Encontrar el persistent_id del cliente
        client_id = None
        with self.main_app.native_server.client_lock:
            for addr, client_obj in self.main_app.native_server.clients.items():
                addr_str = f"{addr[0]}:{addr[1]}"
                if addr_str == client_addr:
                    client_id = client_obj.persistent_id
                    break
        
        if client_id:
            # Actualizar channel_manager
            self.main_app.channel_manager.update_client_mix(
                client_id, 
                gains={channel: gain}
            )

    def mixer_activate_all(self):
        """Activar todos los canales del cliente seleccionado"""
        if self.selected_client_index < 0:
            return
        
        clients = self.main_app.native_server.get_connected_clients() if self.main_app.native_server else []
        if self.selected_client_index >= len(clients):
            return
        
        client = clients[self.selected_client_index]
        client_addr = client['address']
        max_channels = self.main_app.channel_manager.num_channels if self.main_app.channel_manager else 0
        
        if self.main_app.native_server:
            with self.main_app.native_server.client_lock:
                for addr, client_obj in self.main_app.native_server.clients.items():
                    addr_str = f"{addr[0]}:{addr[1]}"
                    if addr_str == client_addr:
                        client_obj.subscribed_channels = set(range(max_channels))
                        # Actualizar channel_manager
                        self.main_app.channel_manager.update_client_mix(
                            client_obj.persistent_id, 
                            channels=list(client_obj.subscribed_channels)
                        )
                        break
        
        # Actualizar UI
        for ch, var in self.channel_mute_vars.items():
            var.set(True)

    def mixer_deactivate_all(self):
        """Desactivar todos los canales del cliente seleccionado"""
        if self.selected_client_index < 0:
            return
        
        clients = self.main_app.native_server.get_connected_clients() if self.main_app.native_server else []
        if self.selected_client_index >= len(clients):
            return
        
        client = clients[self.selected_client_index]
        client_addr = client['address']
        
        if self.main_app.native_server:
            with self.main_app.native_server.client_lock:
                for addr, client_obj in self.main_app.native_server.clients.items():
                    addr_str = f"{addr[0]}:{addr[1]}"
                    if addr_str == client_addr:
                        client_obj.subscribed_channels = set()
                        # Actualizar channel_manager
                        self.main_app.channel_manager.update_client_mix(
                            client_obj.persistent_id, 
                            channels=list(client_obj.subscribed_channels)
                        )
                        break
        
        # Actualizar UI
        for ch, var in self.channel_mute_vars.items():
            var.set(False)

    def mixer_reset_gains(self):
        """Resetear todas las ganancias a 1.0"""
        if self.selected_client_index < 0:
            return
        
        clients = self.main_app.native_server.get_connected_clients() if self.main_app.native_server else []
        if self.selected_client_index >= len(clients):
            return
        
        client = clients[self.selected_client_index]
        client_addr = client['address']
        
        # Resetear ganancias en UI
        for ch, (scale, label_var) in self.channel_gain_scales.items():
            scale.set(1.0)
            label_var.set("1.0x")
        
        # Actualizar channel_manager
        max_channels = self.main_app.channel_manager.num_channels if self.main_app.channel_manager else 0
        gains = {ch: 1.0 for ch in range(max_channels)}
        
        # Encontrar el persistent_id
        client_id = None
        if self.main_app.native_server:
            with self.main_app.native_server.client_lock:
                for addr, client_obj in self.main_app.native_server.clients.items():
                    addr_str = f"{addr[0]}:{addr[1]}"
                    if addr_str == client_addr:
                        client_id = client_obj.persistent_id
                        break
        
        if client_id:
            self.main_app.channel_manager.update_client_mix(
                client_id, 
                gains=gains
            )
    
    def setup_header(self, parent):
        """Configurar encabezado"""
        header_frame = ttk.Frame(parent)
        header_frame.grid(row=0, column=0, columnspan=2, pady=(0, 12), sticky=(tk.W, tk.E))
        header_frame.columnconfigure(0, weight=1)
        
        # Logo
        logo_path = os.path.join(os.getcwd(), 'icono.ico')
        if os.path.exists(logo_path):
            self.root.iconbitmap(logo_path)
        
        # Título
        title = ttk.Label(header_frame, text="FICHATECH SERVER", style='Title.TLabel')
        title.grid(row=0, column=0, sticky=(tk.W, tk.E))
    
    def setup_general_stats(self, parent):
        """Panel de estadísticas generales"""
        stats_container = ttk.Frame(parent)
        stats_container.grid(row=1, column=0, columnspan=2, pady=(0, 8), sticky=(tk.W, tk.E))
        stats_container.columnconfigure(0, weight=1)
        stats_container.columnconfigure(1, weight=1)
        stats_container.columnconfigure(2, weight=1)
        stats_container.columnconfigure(3, weight=1)
        
        # Estado del servidor
        status_frame = ttk.LabelFrame(stats_container, text="Estado del Servidor", padding="12")
        status_frame.grid(row=0, column=0, padx=4, sticky=(tk.W, tk.E, tk.N, tk.S))
        ttk.Label(status_frame, textvariable=self.server_status_var, 
                 style='StatValue.TLabel', foreground=self.accent_blue).pack()
        ttk.Label(status_frame, textvariable=self.uptime_var, 
                 foreground=self.text_secondary, font=('Segoe UI', 9)).pack(pady=(5, 0))
        
        # Clientes RF
        rf_frame = ttk.LabelFrame(stats_container, text="Clientes RF", padding="12")
        rf_frame.grid(row=0, column=1, padx=4, sticky=(tk.W, tk.E, tk.N, tk.S))
        ttk.Label(rf_frame, textvariable=self.rf_clients_var, 
                 style='StatValue.TLabel', foreground=self.accent_purple).pack()
        ttk.Label(rf_frame, text="conectados", 
                 foreground=self.text_secondary, font=('Segoe UI', 9)).pack(pady=(5, 0))
        
        # Clientes Web
        web_frame = ttk.LabelFrame(stats_container, text="Clientes Web", padding="12")
        web_frame.grid(row=0, column=2, padx=4, sticky=(tk.W, tk.E, tk.N, tk.S))
        ttk.Label(web_frame, textvariable=self.web_clients_var, 
                 style='StatValue.TLabel', foreground=self.accent_cyan).pack()
        ttk.Label(web_frame, text="conectados", 
                 foreground=self.text_secondary, font=('Segoe UI', 9)).pack(pady=(5, 0))
        
        # Paquetes
        packets_frame = ttk.LabelFrame(stats_container, text="Paquetes", padding="12")
        packets_frame.grid(row=0, column=3, padx=4, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        packets_info = ttk.Frame(packets_frame)
        packets_info.pack()
        
        ttk.Label(packets_info, text="Enviados: ", 
                 foreground=self.text_secondary, font=('Segoe UI', 9)).grid(row=0, column=0, sticky=tk.E)
        ttk.Label(packets_info, textvariable=self.packets_sent_var, 
                 style='SmallValue.TLabel', foreground=self.accent_green).grid(row=0, column=1, sticky=tk.W)
        
        ttk.Label(packets_info, text="Perdidos: ", 
                 foreground=self.text_secondary, font=('Segoe UI', 9)).grid(row=1, column=0, sticky=tk.E, pady=(4, 0))
        ttk.Label(packets_info, textvariable=self.packets_dropped_var, 
                 style='SmallValue.TLabel', foreground=self.accent_red).grid(row=1, column=1, sticky=tk.W, pady=(4, 0))
    
    def setup_device_panel(self, parent):
        """Panel de dispositivo"""
        device_frame = ttk.LabelFrame(parent, text="Dispositivo de Audio", padding="12")
        device_frame.grid(row=0, column=0, pady=(0, 8), sticky=(tk.W, tk.E))
        device_frame.columnconfigure(0, weight=1)
        
        # Nombre del dispositivo
        name_frame = ttk.Frame(device_frame)
        name_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 8))
        
        ttk.Label(name_frame, text="Seleccionado:", 
                 foreground=self.text_secondary, font=('Segoe UI', 9)).pack(anchor=tk.W)
        ttk.Label(name_frame, textvariable=self.selected_device_name, 
                 foreground=self.text_primary, font=('Segoe UI', 10, 'bold'),
                 wraplength=450).pack(anchor=tk.W, pady=(4, 0))
        
        # Información del dispositivo
        self.device_info_var = tk.StringVar(value="Canales: -- | Sample Rate: -- Hz")
        ttk.Label(device_frame, textvariable=self.device_info_var, 
                 foreground=self.text_secondary, font=('Segoe UI', 9)).grid(row=1, column=0, sticky=tk.W, pady=(0, 12))
        
        # Botón cambiar
        ttk.Button(device_frame, text="🔄 Cambiar Dispositivo", 
                  command=self.show_device_selector, 
                  style='Blue.TButton').grid(row=2, column=0, sticky=(tk.W, tk.E))
        
        # Frame de selector (oculto inicialmente)
        self.setup_device_selector(parent)
    
    def setup_device_selector(self, parent):
        """Frame de selección de dispositivo"""
        self.device_selector_frame = ttk.LabelFrame(parent, text="Seleccionar Interfaz de Audio", padding="12")
        self.device_selector_frame.grid(row=0, column=0, pady=(0, 8), sticky=(tk.W, tk.E, tk.N, tk.S))
        self.device_selector_frame.grid_remove()
        
        self.device_var = tk.IntVar(value=-1)
        
        # Lista con scroll
        list_container = ttk.Frame(self.device_selector_frame)
        list_container.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        list_container.columnconfigure(0, weight=1)
        list_container.rowconfigure(0, weight=1)
        
        self.device_canvas = tk.Canvas(list_container, bg=self.bg_light, 
                                       highlightthickness=0, height=250)
        scrollbar = ttk.Scrollbar(list_container, orient="vertical", 
                                 command=self.device_canvas.yview)
        self.scrollable_frame = ttk.Frame(self.device_canvas)
        
        self.scrollable_frame.bind("<Configure>",
            lambda e: self.device_canvas.configure(scrollregion=self.device_canvas.bbox("all")))
        
        self.device_canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.device_canvas.configure(yscrollcommand=scrollbar.set)
        
        self.device_canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # Botones
        button_frame = ttk.Frame(self.device_selector_frame)
        button_frame.grid(row=1, column=0, pady=(12, 0), sticky=(tk.W, tk.E))
        
        ttk.Button(button_frame, text="✅ Seleccionar", 
                  command=self.select_device, 
                  style='Green.TButton').pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(button_frame, text="❌ Cancelar", 
                  command=self.hide_device_selector).pack(side=tk.LEFT)
        ttk.Button(button_frame, text="🔄 Actualizar", 
                  command=self.refresh_devices).pack(side=tk.RIGHT)
    
    def setup_clients_frame(self, parent):
        """Frame de lista de clientes conectados"""
        clients_frame = ttk.LabelFrame(parent, text="Clientes Conectados", padding="12")
        clients_frame.grid(row=0, column=0, pady=(0, 8), sticky=(tk.W, tk.E, tk.N, tk.S))
        clients_frame.columnconfigure(0, weight=1)
        clients_frame.rowconfigure(0, weight=1)
        
        # Área de texto para clientes
        self.clients_text = scrolledtext.ScrolledText(clients_frame,
                                                     height=20,
                                                     bg=self.bg_light,
                                                     fg=self.text_primary,
                                                     font=('Consolas', 9),
                                                     insertbackground=self.accent_blue,
                                                     state='disabled',
                                                     borderwidth=0,
                                                     highlightthickness=0)
        self.clients_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Tags para colores coherentes
        self.clients_text.tag_config('HEADER', foreground=self.accent_blue, font=('Consolas', 10, 'bold'))
        self.clients_text.tag_config('RF_TITLE', foreground=self.accent_purple, font=('Consolas', 10, 'bold'))
        self.clients_text.tag_config('WEB_TITLE', foreground=self.accent_cyan, font=('Consolas', 10, 'bold'))
        self.clients_text.tag_config('IP', foreground=self.accent_blue, font=('Consolas', 9, 'bold'))
        self.clients_text.tag_config('LABEL', foreground=self.text_secondary)
        self.clients_text.tag_config('VALUE', foreground=self.text_primary, font=('Consolas', 9, 'bold'))
        self.clients_text.tag_config('CHANNEL', foreground=self.accent_green)
        self.clients_text.tag_config('TIME', foreground=self.accent_yellow)
        self.clients_text.tag_config('SEPARATOR', foreground=self.border_color)
        self.clients_text.tag_config('WARNING', foreground=self.accent_yellow)
        # Aquí debe ir el resto del método update_clients_display, no dentro de setup_clients_frame
    
    def show_device_selector(self):
        """Mostrar selector de dispositivos"""
        if not hasattr(self, 'device_widgets'):
            self.load_devices()
        
        self.device_selector_frame.grid()
        
        if self.selected_device_id != -1:
            self.device_var.set(self.selected_device_id)
    
    def hide_device_selector(self):
        """Ocultar selector de dispositivos"""
        self.device_selector_frame.grid_remove()
    
    def load_devices(self):
        """Cargar lista de dispositivos"""
        self.device_widgets = []
        
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        devices = sd.query_devices()
        input_devices = [(i, d) for i, d in enumerate(devices) if d['max_input_channels'] > 0]
        input_devices.sort(key=lambda x: (x[1]['max_input_channels'], x[1]['default_samplerate']), reverse=True)
        
        for device_id, device in input_devices:
            device_item = ttk.Frame(self.scrollable_frame, padding="8")
            device_item.pack(fill=tk.X, pady=2)
            
            rb = ttk.Radiobutton(device_item,
                                text=f"{device['name']}",
                                variable=self.device_var,
                                value=device_id)
            rb.pack(anchor=tk.W)
            
            channels = device['max_input_channels']
            samplerate = int(device['default_samplerate']) if device['default_samplerate'] else DEFAULT_SAMPLE_RATE
            
            info_text = f"  Canales: {channels} | Sample Rate: {samplerate} Hz"
            if channels > 2:
                info_text += " ⭐"
            
            info_label = ttk.Label(device_item, text=info_text)
            info_label.configure(foreground=self.text_secondary)
            info_label.pack(anchor=tk.W, padx=(20, 0))
            
            self.device_widgets.append((device_id, device_item))
    
    def select_device(self):
        """Seleccionar dispositivo"""
        device_id = self.device_var.get()
        
        if device_id == -1:
            self.log_message("❌ Por favor selecciona un dispositivo", 'ERROR')
            return
        
        self.update_device_display(device_id)
        self.hide_device_selector()
        self.log_message(f"✅ Dispositivo seleccionado: {self.selected_device_name.get()}", 'SUCCESS')
    
    def update_device_display(self, device_id):
        """Actualizar display del dispositivo"""
        try:
            device_info = sd.query_devices(device_id)
            self.selected_device_id = device_id
            self.selected_device_name.set(device_info['name'])
            
            channels = device_info['max_input_channels']
            samplerate = int(device_info['default_samplerate']) if device_info['default_samplerate'] else DEFAULT_SAMPLE_RATE
            self.device_info_var.set(f"Canales: {channels} | Sample Rate: {samplerate} Hz")
            
            if self.main_app.server_running:
                self.log_message("⚠️ Dispositivo cambiado. Reinicia el servidor.", 'WARNING')
        except Exception as e:
            self.log_message(f"❌ Error al obtener info del dispositivo: {e}", 'ERROR')
    
    def refresh_devices(self):
        """Actualizar lista de dispositivos"""
        self.load_devices()
        self.log_message("🔄 Lista de dispositivos actualizada", 'INFO')
    
    def log_message(self, message, tag='INFO'):
        """Agregar mensaje al log"""
        if not self.root.winfo_exists():
            return
            
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        self.log_text.insert(tk.END, log_entry, tag)
        self.log_text.see(tk.END)
        self.log_text.update()
    
    def start_server(self):
        """Iniciar servidor"""
        if self.selected_device_id == -1:
            self.log_message("❌ Selecciona un dispositivo primero", 'ERROR')
            self.show_device_selector()
            return
        
        device_info = sd.query_devices(self.selected_device_id)
        self.log_message(f"🎙️ Iniciando servidor con: {device_info['name']}", 'RF')
        
        if hasattr(self.main_app, 'start_server_with_device'):
            self.main_app.start_server_with_device(self.selected_device_id)
        
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.server_status_var.set("🟢 Ejecutándose")
        self.server_start_time = time.time()
        
        self.log_message("✅ Servidor iniciado correctamente", 'SUCCESS')
    
    def stop_server(self):
        """Detener servidor"""
        if hasattr(self.main_app, 'stop_server'):
            self.main_app.stop_server()
        
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.server_status_var.set("🔴 Detenido")
        self.server_start_time = None
        self.uptime_var.set("00:00:00")
        
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

                # Actualizar contadores
                self.rf_clients_var.set(str(stats.get('clients_rf', 0)))
                self.web_clients_var.set(str(stats.get('clients_web', 0)))
                self.packets_sent_var.set(str(stats.get('packets_sent', 0)))
                self.packets_dropped_var.set(str(stats.get('packets_dropped', 0)))

                # Actualizar uptime
                if self.server_start_time:
                    uptime_seconds = int(time.time() - self.server_start_time)
                    hours = uptime_seconds // 3600
                    minutes = (uptime_seconds % 3600) // 60
                    seconds = uptime_seconds % 60
                    self.uptime_var.set(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

                # Actualizar lista de clientes
                if self.root.winfo_exists():
                    self.root.after(0, self.update_clients_display)

                # Procesar mensajes en cola
                while not self.stats_queue.empty():
                    msg = self.stats_queue.get_nowait()
                    if self.root.winfo_exists():
                        self.root.after(0, self.log_message, msg[0], msg[1])

            except Exception as e:
                pass

            time.sleep(0.5)
    
    def queue_log_message(self, message, tag='INFO'):
        """Agregar mensaje al log desde otros threads"""
        self.stats_queue.put((message, tag))
    
    def on_closing(self):
        """Manejar cierre de ventana"""
        self.running = False
        if hasattr(self.main_app, 'cleanup'):
            self.main_app.cleanup()
        self.root.destroy()

    def update_current_scene_info(self):
        """Actualizar información de escena actual"""
        if not self.main_app or not self.main_app.server_running:
            self.current_interface_var.set("Servidor detenido")
            self.current_clients_var.set("0 conectados")
            return
        
        try:
            # Obtener info de interfaz
            if self.main_app.scene_manager:
                device_info = self.main_app.scene_manager.get_current_device_info()
                if device_info:
                    self.current_interface_var.set(f"{device_info['name']} ({device_info['channels']} canales)")
                else:
                    self.current_interface_var.set("No detectada")
            
            # Obtener clientes conectados
            stats = self.main_app.get_current_stats()
            total_clients = stats.get('clients_rf', 0) + stats.get('clients_web', 0)
            self.current_clients_var.set(f"{total_clients} conectado{'s' if total_clients != 1 else ''}")
            
        except Exception as e:
            if hasattr(self, 'log_message'):
                self.log_message(f"Error actualizando info de escena: {e}", 'ERROR')

    def refresh_scenes_list(self):
        """Refrescar lista de escenas"""
        # Limpiar lista actual
        for widget in self.scenes_list_frame.winfo_children():
            widget.destroy()
        
        if not self.main_app:
            return
        
        try:
            # Obtener escenas
            scenes = self.main_app.get_available_scenes()
            
            if not scenes:
                # Mensaje de no hay escenas
                empty_frame = tk.Frame(self.scenes_list_frame, bg=self.bg_light)
                empty_frame.pack(fill=tk.BOTH, expand=True, pady=60)
                
                tk.Label(empty_frame, text="📭", font=('Segoe UI', 48),
                        bg=self.bg_light, fg=self.text_secondary).pack()
                tk.Label(empty_frame, text="No hay escenas guardadas",
                        font=('Segoe UI', 12),
                        bg=self.bg_light, fg=self.text_secondary).pack(pady=(12, 0))
                tk.Label(empty_frame, text="Guarda la configuración actual para crear una escena",
                        font=('Segoe UI', 9),
                        bg=self.bg_light, fg=self.text_secondary).pack(pady=(4, 0))
            else:
                # Crear items de escenas
                for scene in scenes:
                    self.create_scene_item(scene)
            
            # Actualizar scroll region
            self.scenes_list_frame.update_idletasks()
            self.scenes_canvas.configure(scrollregion=self.scenes_canvas.bbox("all"))
            
            # Actualizar info actual
            self.update_current_scene_info()
            
        except Exception as e:
            self.log_message(f"Error refrescando escenas: {e}", 'ERROR')

    def create_scene_item(self, scene):
        """Crear item visual para una escena"""
        compatible = scene.get('compatible', False)
        
        # Frame de la escena
        scene_frame = tk.Frame(self.scenes_list_frame,
                              bg=self.bg_medium,
                              relief=tk.RAISED,
                              borderwidth=1)
        scene_frame.pack(fill=tk.X, padx=8, pady=4)
        
        # Padding interno
        inner_frame = tk.Frame(scene_frame, bg=self.bg_medium)
        inner_frame.pack(fill=tk.BOTH, padx=12, pady=12)
        inner_frame.columnconfigure(1, weight=1)
        
        # Icono y título
        header_frame = tk.Frame(inner_frame, bg=self.bg_medium)
        header_frame.grid(row=0, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 8))
        
        # Icono según compatibilidad
        icon = "✅" if compatible else "⚠️"
        tk.Label(header_frame, text=icon, font=('Segoe UI', 20),
                bg=self.bg_medium, fg=self.accent_green if compatible else self.accent_yellow).pack(side=tk.LEFT, padx=(0, 8))
        
        # Info de la escena
        info_frame = tk.Frame(header_frame, bg=self.bg_medium)
        info_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Nombre de la escena
        tk.Label(info_frame, text=scene['name'],
                font=('Segoe UI', 12, 'bold'),
                bg=self.bg_medium, fg=self.text_primary,
                anchor=tk.W).pack(fill=tk.X)
        
        # Descripción (si existe)
        if scene.get('description'):
            tk.Label(info_frame, text=scene['description'],
                    font=('Segoe UI', 9),
                    bg=self.bg_medium, fg=self.text_secondary,
                    anchor=tk.W).pack(fill=tk.X, pady=(2, 0))
        
        # Detalles
        details_frame = tk.Frame(inner_frame, bg=self.bg_medium)
        details_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 8))
        
        # Interfaz requerida
        tk.Label(details_frame, text="🎛️",
                bg=self.bg_medium, fg=self.text_secondary).pack(side=tk.LEFT, padx=(0, 4))
        tk.Label(details_frame, text=f"{scene['interface_name']} ({scene['interface_channels']}ch)",
                font=('Consolas', 9),
                bg=self.bg_medium, fg=self.text_primary).pack(side=tk.LEFT, padx=(0, 16))
        
        # Clientes
        tk.Label(details_frame, text="👥",
                bg=self.bg_medium, fg=self.text_secondary).pack(side=tk.LEFT, padx=(0, 4))
        tk.Label(details_frame, text=f"{scene['num_clients']} clientes",
                font=('Consolas', 9),
                bg=self.bg_medium, fg=self.text_primary).pack(side=tk.LEFT, padx=(0, 16))
        
        # Fecha
        try:
            created_date = datetime.fromisoformat(scene['created_at']).strftime("%d/%m/%Y %H:%M")
        except:
            created_date = "Fecha desconocida"
        
        tk.Label(details_frame, text="📅",
                bg=self.bg_medium, fg=self.text_secondary).pack(side=tk.LEFT, padx=(0, 4))
        tk.Label(details_frame, text=created_date,
                font=('Consolas', 9),
                bg=self.bg_medium, fg=self.text_primary).pack(side=tk.LEFT)
        
        # Mensaje de compatibilidad
        compat_msg = scene.get('compatibility_message', '')
        if compat_msg:
            compat_label = tk.Label(inner_frame, text=compat_msg,
                                   font=('Segoe UI', 8),
                                   bg=self.bg_medium,
                                   fg=self.accent_green if compatible else self.accent_yellow,
                                   anchor=tk.W)
            compat_label.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 8))
        
        # Botones de acción
        buttons_frame = tk.Frame(inner_frame, bg=self.bg_medium)
        buttons_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E))
        
        if compatible:
            # Botón Cargar (solo si es compatible)
            load_btn = tk.Button(buttons_frame, text="▶️ Cargar",
                                font=('Segoe UI', 9, 'bold'),
                                bg=self.accent_green, fg='#ffffff',
                                relief=tk.FLAT, padx=16, pady=6,
                                cursor='hand2',
                                command=lambda: self.load_scene_with_confirmation(scene['name']))
            load_btn.pack(side=tk.LEFT, padx=(0, 8))
        else:
            # Botón deshabilitado si incompatible
            disabled_btn = tk.Button(buttons_frame, text="🚫 Incompatible",
                                    font=('Segoe UI', 9),
                                    bg=self.bg_dark, fg=self.text_secondary,
                                    relief=tk.FLAT, padx=16, pady=6,
                                    state='disabled')
            disabled_btn.pack(side=tk.LEFT, padx=(0, 8))
        
        # Botón Ver detalles
        details_btn = tk.Button(buttons_frame, text="👁️ Ver",
                               font=('Segoe UI', 9),
                               bg=self.accent_blue, fg='#ffffff',
                               relief=tk.FLAT, padx=16, pady=6,
                               cursor='hand2',
                               command=lambda: self.show_scene_details(scene['name']))
        details_btn.pack(side=tk.LEFT, padx=(0, 8))
        
        # Botón Exportar
        export_btn = tk.Button(buttons_frame, text="📤",
                              font=('Segoe UI', 9),
                              bg=self.bg_light, fg=self.text_primary,
                              relief=tk.FLAT, padx=12, pady=6,
                              cursor='hand2',
                              command=lambda: self.export_scene_specific(scene['name']))
        export_btn.pack(side=tk.LEFT, padx=(0, 8))
        
        # Botón Eliminar
        delete_btn = tk.Button(buttons_frame, text="🗑️",
                              font=('Segoe UI', 9),
                              bg=self.accent_red, fg='#ffffff',
                              relief=tk.FLAT, padx=12, pady=6,
                              cursor='hand2',
                              command=lambda: self.delete_scene_with_confirmation(scene['name']))
        delete_btn.pack(side=tk.LEFT)

    def show_save_scene_dialog(self):
        """Mostrar diálogo para guardar nueva escena"""
        if not self.main_app or not self.main_app.server_running:
            self.log_message("❌ El servidor debe estar corriendo para guardar escenas", 'ERROR')
            return
        
        # Crear ventana modal
        dialog = tk.Toplevel(self.root)
        dialog.title("Guardar Escena")
        dialog.geometry("500x400")
        dialog.configure(bg=self.bg_medium)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Centrar ventana
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Frame principal
        main_frame = tk.Frame(dialog, bg=self.bg_medium, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.columnconfigure(0, weight=1)
        
        # Título
        tk.Label(main_frame, text="💾 Guardar Escena",
                font=('Segoe UI', 16, 'bold'),
                bg=self.bg_medium, fg=self.text_primary).grid(row=0, column=0, sticky=tk.W, pady=(0, 20))
        
        # Nombre de escena
        tk.Label(main_frame, text="Nombre de la escena:",
                font=('Segoe UI', 10),
                bg=self.bg_medium, fg=self.text_secondary).grid(row=1, column=0, sticky=tk.W, pady=(0, 4))
        
        name_var = tk.StringVar()
        name_entry = tk.Entry(main_frame, textvariable=name_var,
                             font=('Segoe UI', 11),
                             bg=self.bg_light, fg=self.text_primary,
                             relief=tk.FLAT, insertbackground=self.accent_blue)
        name_entry.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 12), ipady=6)
        name_entry.focus()
        
        # Descripción
        tk.Label(main_frame, text="Descripción (opcional):",
                font=('Segoe UI', 10),
                bg=self.bg_medium, fg=self.text_secondary).grid(row=3, column=0, sticky=tk.W, pady=(0, 4))
        
        desc_text = tk.Text(main_frame, height=4,
                           font=('Segoe UI', 10),
                           bg=self.bg_light, fg=self.text_primary,
                           relief=tk.FLAT, insertbackground=self.accent_blue)
        desc_text.grid(row=4, column=0, sticky=(tk.W, tk.E), pady=(0, 12))
        
        # Info de interfaz detectada
        info_frame = tk.Frame(main_frame, bg=self.bg_light, relief=tk.RAISED, borderwidth=1)
        info_frame.grid(row=5, column=0, sticky=(tk.W, tk.E), pady=(0, 12))
        info_inner = tk.Frame(info_frame, bg=self.bg_light, padx=12, pady=12)
        info_inner.pack(fill=tk.BOTH)
        
        tk.Label(info_inner, text="Interfaz detectada:",
                font=('Segoe UI', 9, 'bold'),
                bg=self.bg_light, fg=self.text_secondary).pack(anchor=tk.W)
        
        if self.main_app.scene_manager:
            device_info = self.main_app.scene_manager.get_current_device_info()
            if device_info:
                device_text = f"🎛️ {device_info['name']} ({device_info['channels']} canales)"
            else:
                device_text = "⚠️ No se pudo detectar"
        else:
            device_text = "⚠️ Scene manager no disponible"
        
        tk.Label(info_inner, text=device_text,
                font=('Segoe UI', 10),
                bg=self.bg_light, fg=self.text_primary).pack(anchor=tk.W, pady=(4, 0))
        
        # Clientes a guardar
        tk.Label(info_inner, text="Clientes a guardar:",
                font=('Segoe UI', 9, 'bold'),
                bg=self.bg_light, fg=self.text_secondary).pack(anchor=tk.W, pady=(8, 0))
        
        stats = self.main_app.get_current_stats()
        total_clients = stats.get('clients_rf', 0) + stats.get('clients_web', 0)
        
        clients_text = f"👥 {total_clients} cliente{'s' if total_clients != 1 else ''}"
        tk.Label(info_inner, text=clients_text,
                font=('Segoe UI', 10),
                bg=self.bg_light, fg=self.text_primary).pack(anchor=tk.W, pady=(4, 0))
        
        # Botones
        button_frame = tk.Frame(main_frame, bg=self.bg_medium)
        button_frame.grid(row=6, column=0, sticky=(tk.W, tk.E), pady=(12, 0))
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)
        
        def on_save():
            name = name_var.get().strip()
            description = desc_text.get("1.0", tk.END).strip()
            
            if not name:
                messagebox.showerror("Error", "Debes ingresar un nombre para la escena", parent=dialog)
                return
            
            # Guardar escena
            success, message = self.main_app.save_current_scene(name, description)
            
            if success:
                self.log_message(f"✅ {message}", 'SUCCESS')
                dialog.destroy()
                self.refresh_scenes_list()
            else:
                messagebox.showerror("Error", message, parent=dialog)
        
        cancel_btn = tk.Button(button_frame, text="❌ Cancelar",
                              font=('Segoe UI', 10),
                              bg=self.bg_light, fg=self.text_primary,
                              relief=tk.FLAT, padx=20, pady=8,
                              cursor='hand2',
                              command=dialog.destroy)
        cancel_btn.grid(row=0, column=0, padx=(0, 8), sticky=(tk.W, tk.E))
        
        save_btn = tk.Button(button_frame, text="💾 Guardar",
                            font=('Segoe UI', 10, 'bold'),
                            bg=self.accent_green, fg='#ffffff',
                            relief=tk.FLAT, padx=20, pady=8,
                            cursor='hand2',
                            command=on_save)
        save_btn.grid(row=0, column=1, padx=(8, 0), sticky=(tk.W, tk.E))
        
        # Bind Enter para guardar
        dialog.bind('<Return>', lambda e: on_save())
        dialog.bind('<Escape>', lambda e: dialog.destroy())

    def load_scene_with_confirmation(self, scene_name):
        """Cargar escena con confirmación"""
        if not self.main_app:
            return
        
        # Validar compatibilidad primero
        compatible, message = self.main_app.validate_scene_compatibility(scene_name)
        
        if not compatible:
            messagebox.showerror("Interfaz incompatible", message, parent=self.root)
            return
        
        # Confirmar con usuario
        result = messagebox.askyesno(
            "Cargar Escena",
            f"⚠️ Esto SOBRESCRIBIRÁ la configuración actual de todos los clientes conectados.\n\n"
            f"Escena: {scene_name}\n\n"
            f"¿Continuar?",
            parent=self.root
        )
        
        if result:
            success, message = self.main_app.load_scene(scene_name)
            
            if success:
                self.log_message(f"✅ Escena cargada: {scene_name}", 'SUCCESS')
                # Refrescar mixer si está visible
                if hasattr(self, 'refresh_mixer_clients'):
                    self.refresh_mixer_clients()
            else:
                self.log_message(f"❌ Error cargando escena: {message}", 'ERROR')
                messagebox.showerror("Error", message, parent=self.root)

    def delete_scene_with_confirmation(self, scene_name):
        """Eliminar escena con confirmación"""
        if not self.main_app:
            return
        
        result = messagebox.askyesno(
            "Eliminar Escena",
            f"¿Eliminar la escena '{scene_name}'?\n\n"
            f"Se creará un backup antes de eliminar.\n"
            f"Esta acción no se puede deshacer.",
            parent=self.root
        )
        
        if result:
            success, message = self.main_app.delete_scene(scene_name)
            
            if success:
                self.log_message(f"🗑️ {message}", 'WARNING')
                self.refresh_scenes_list()
            else:
                messagebox.showerror("Error", message, parent=self.root)

    def show_scene_details(self, scene_name):
        """Mostrar detalles completos de una escena"""
        scene_data = self.main_app.get_scene_details(scene_name)
        
        if not scene_data:
            messagebox.showerror("Error", "No se pudo cargar la escena", parent=self.root)
            return
        
        # Crear ventana modal
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Detalles: {scene_name}")
        dialog.geometry("700x600")
        dialog.configure(bg=self.bg_medium)
        dialog.transient(self.root)
        
        # Frame principal con scroll
        main_frame = tk.Frame(dialog, bg=self.bg_medium)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # Título
        tk.Label(main_frame, text=f"📄 {scene_name}",
                font=('Segoe UI', 16, 'bold'),
                bg=self.bg_medium, fg=self.text_primary).grid(row=0, column=0, sticky=tk.W, pady=(0, 12))
        
        # Área de detalles con scroll
        canvas = tk.Canvas(main_frame, bg=self.bg_light, highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=self.bg_light)
        
        scrollable_frame.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.grid(row=1, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        scrollbar.grid(row=1, column=1, sticky=(tk.N, tk.S))
        
        # Contenido
        content_frame = tk.Frame(scrollable_frame, bg=self.bg_light, padx=20, pady=20)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Descripción
        if scene_data.get('description'):
            tk.Label(content_frame, text="Descripción:",
                    font=('Segoe UI', 10, 'bold'),
                    bg=self.bg_light, fg=self.text_secondary).pack(anchor=tk.W, pady=(0, 4))
            tk.Label(content_frame, text=scene_data['description'],
                    font=('Segoe UI', 10),
                    bg=self.bg_light, fg=self.text_primary,
                    wraplength=600, justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 16))
        
        # Metadata
        metadata = scene_data.get('metadata', {})
        
        tk.Label(content_frame, text="📅 Información:",
                font=('Segoe UI', 10, 'bold'),
                bg=self.bg_light, fg=self.text_secondary).pack(anchor=tk.W, pady=(0, 8))
        
        info_frame = tk.Frame(content_frame, bg=self.bg_medium, relief=tk.RAISED, borderwidth=1)
        info_frame.pack(fill=tk.X, pady=(0, 16))
        info_inner = tk.Frame(info_frame, bg=self.bg_medium, padx=12, pady=12)
        info_inner.pack(fill=tk.BOTH)
        
        created_at = metadata.get('created_at', 'Desconocido')
        last_loaded = metadata.get('last_loaded', 'Nunca')
        load_count = metadata.get('load_count', 0)
        
        tk.Label(info_inner, text=f"Creada: {created_at}",
                font=('Consolas', 9),
                bg=self.bg_medium, fg=self.text_primary).pack(anchor=tk.W)
        tk.Label(info_inner, text=f"Última carga: {last_loaded}",
                font=('Consolas', 9),
                bg=self.bg_medium, fg=self.text_primary).pack(anchor=tk.W, pady=(4, 0))
        tk.Label(info_inner, text=f"Veces cargada: {load_count}",
                font=('Consolas', 9),
                bg=self.bg_medium, fg=self.text_primary).pack(anchor=tk.W, pady=(4, 0))
        
        # Interfaz requerida
        interface_info = scene_data.get('interface_info', {})
        
        tk.Label(content_frame, text="🎛️ Interfaz requerida:",
                font=('Segoe UI', 10, 'bold'),
                bg=self.bg_light, fg=self.text_secondary).pack(anchor=tk.W, pady=(0, 8))
        
        interface_frame = tk.Frame(content_frame, bg=self.bg_medium, relief=tk.RAISED, borderwidth=1)
        interface_frame.pack(fill=tk.X, pady=(0, 16))
        interface_inner = tk.Frame(interface_frame, bg=self.bg_medium, padx=12, pady=12)
        interface_inner.pack(fill=tk.BOTH)
        
        tk.Label(interface_inner, text=f"Nombre: {interface_info.get('name', 'Desconocido')}",
                font=('Consolas', 9),
                bg=self.bg_medium, fg=self.text_primary).pack(anchor=tk.W)
        tk.Label(interface_inner, text=f"Canales: {interface_info.get('channels', 0)}",
                font=('Consolas', 9),
                bg=self.bg_medium, fg=self.text_primary).pack(anchor=tk.W, pady=(4, 0))
        tk.Label(interface_inner, text=f"Sample Rate: {interface_info.get('sample_rate', 0)} Hz",
                font=('Consolas', 9),
                bg=self.bg_medium, fg=self.text_primary).pack(anchor=tk.W, pady=(4, 0))
        
        # Clientes configurados
        clients = scene_data.get('clients', {})
        
        tk.Label(content_frame, text=f"👥 Clientes configurados ({len(clients)}):",
                font=('Segoe UI', 10, 'bold'),
                bg=self.bg_light, fg=self.text_secondary).pack(anchor=tk.W, pady=(0, 8))
        
        for client_key, client_config in clients.items():
            client_frame = tk.Frame(content_frame, bg=self.bg_medium, relief=tk.RAISED, borderwidth=1)
            client_frame.pack(fill=tk.X, pady=(0, 8))
            client_inner = tk.Frame(client_frame, bg=self.bg_medium, padx=12, pady=12)
            client_inner.pack(fill=tk.BOTH)
            
            tk.Label(client_inner, text=f"📡 {client_key}",
                    font=('Segoe UI', 10, 'bold'),
                    bg=self.bg_medium, fg=self.accent_blue).pack(anchor=tk.W)
            
            channels = client_config.get('channels', [])
            tk.Label(client_inner, text=f"Canales: {channels}",
                    font=('Consolas', 8),
                    bg=self.bg_medium, fg=self.text_primary).pack(anchor=tk.W, pady=(4, 0))
            
            if client_config.get('description'):
                tk.Label(client_inner, text=f"Descripción: {client_config['description']}",
                        font=('Consolas', 8),
                        bg=self.bg_medium, fg=self.text_secondary).pack(anchor=tk.W, pady=(4, 0))
        
        # Botón cerrar
        close_btn = tk.Button(main_frame, text="Cerrar",
                             font=('Segoe UI', 10),
                             bg=self.accent_blue, fg='#ffffff',
                             relief=tk.FLAT, padx=30, pady=10,
                             cursor='hand2',
                             command=dialog.destroy)
        close_btn.grid(row=2, column=0, pady=(12, 0))
        
        dialog.bind('<Escape>', lambda e: dialog.destroy())

    def export_scene_specific(self, scene_name):
        """Exportar una escena específica"""
        from tkinter import filedialog
        
        destination = filedialog.asksaveasfilename(
            title="Exportar Escena",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=f"{scene_name}.json",
            parent=self.root
        )
        
        if destination:
            success, message = self.main_app.export_scene(scene_name, destination)
            
            if success:
                self.log_message(f"📤 {message}", 'SUCCESS')
                messagebox.showinfo("Éxito", message, parent=self.root)
            else:
                messagebox.showerror("Error", message, parent=self.root)

    def export_scene_dialog(self):
        """Diálogo para exportar escena seleccionada"""
        # Por ahora, pedir que seleccionen una escena
        messagebox.showinfo(
            "Exportar Escena",
            "Usa el botón 📤 en cada escena para exportarla individualmente.",
            parent=self.root
        )

    def import_scene_dialog(self):
        """Importar escena desde archivo"""
        from tkinter import filedialog
        
        source = filedialog.askopenfilename(
            title="Importar Escena",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            parent=self.root
        )
        
        if source:
            success, message = self.main_app.import_scene(source)
            
            if success:
                self.log_message(f"📥 {message}", 'SUCCESS')
                self.refresh_scenes_list()
                messagebox.showinfo("Éxito", message, parent=self.root)
            else:
                messagebox.showerror("Error", message, parent=self.root)

    def filter_scenes(self):
        """Filtrar escenas por búsqueda"""
        search_text = self.scene_search_var.get().lower()
        
        # Limpiar lista
        for widget in self.scenes_list_frame.winfo_children():
            widget.destroy()
        
        if not self.main_app:
            return
        
        try:
            scenes = self.main_app.get_available_scenes()
            
            # Filtrar por nombre o descripción
            if search_text:
                scenes = [s for s in scenes 
                         if search_text in s['name'].lower() 
                         or search_text in s.get('description', '').lower()]
            
            if not scenes:
                tk.Label(self.scenes_list_frame, text="🔍 No se encontraron escenas",
                        font=('Segoe UI', 11),
                        bg=self.bg_light, fg=self.text_secondary).pack(pady=40)
            else:
                for scene in scenes:
                    self.create_scene_item(scene)
            
            self.scenes_list_frame.update_idletasks()
            self.scenes_canvas.configure(scrollregion=self.scenes_canvas.bbox("all"))
            
        except Exception as e:
            self.log_message(f"Error filtrando escenas: {e}", 'ERROR')

    def run(self):
        """Ejecutar la GUI"""
        self.root.mainloop()
        
        # Tags para colores coherentes
        self.clients_text.tag_config('HEADER', foreground=self.accent_blue, font=('Consolas', 10, 'bold'))
        self.clients_text.tag_config('RF_TITLE', foreground=self.accent_purple, font=('Consolas', 10, 'bold'))
        self.clients_text.tag_config('WEB_TITLE', foreground=self.accent_cyan, font=('Consolas', 10, 'bold'))
        self.clients_text.tag_config('IP', foreground=self.accent_blue, font=('Consolas', 9, 'bold'))
        self.clients_text.tag_config('LABEL', foreground=self.text_secondary)
        self.clients_text.tag_config('VALUE', foreground=self.text_primary, font=('Consolas', 9, 'bold'))
        self.clients_text.tag_config('CHANNEL', foreground=self.accent_green)
        self.clients_text.tag_config('TIME', foreground=self.accent_yellow)
        self.clients_text.tag_config('SEPARATOR', foreground=self.border_color)
        self.clients_text.tag_config('WARNING', foreground=self.accent_yellow)
    
    def setup_logs_frame(self, parent):
        """Frame de logs del sistema"""
        logs_frame = ttk.LabelFrame(parent, text="Logs del Sistema", padding="12")
        logs_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        logs_frame.columnconfigure(0, weight=1)
        logs_frame.rowconfigure(0, weight=1)
        
        # Área de texto para logs
        self.log_text = scrolledtext.ScrolledText(logs_frame,
                                                 height=12,
                                                 bg=self.bg_light,
                                                 fg=self.text_primary,
                                                 font=('Consolas', 9),
                                                 insertbackground=self.accent_blue,
                                                 borderwidth=0,
                                                 highlightthickness=0)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Tags para colores coherentes
        self.log_text.tag_config('INFO', foreground=self.text_primary)
        self.log_text.tag_config('SUCCESS', foreground=self.accent_green)
        self.log_text.tag_config('WARNING', foreground=self.accent_yellow)
        self.log_text.tag_config('ERROR', foreground=self.accent_red)
        self.log_text.tag_config('RF', foreground=self.accent_purple)
        self.log_text.tag_config('WEB', foreground=self.accent_cyan)
    
    def setup_controls_frame(self, parent):
        """Frame de controles"""
        controls_frame = ttk.Frame(parent)
        controls_frame.grid(row=1, column=0, pady=(0, 0), sticky=(tk.W, tk.E))
        controls_frame.columnconfigure(0, weight=1)
        
        # Botón de inicio
        self.start_btn = ttk.Button(controls_frame,
                                   text="🚀 Iniciar Servidor",
                                   style='Green.TButton',
                                   command=self.start_server)
        self.start_btn.grid(row=0, column=0, pady=(0, 8), sticky=(tk.W, tk.E))
        
        # Botón de detener
        self.stop_btn = ttk.Button(controls_frame,
                                  text="🛑 Detener Servidor",
                                  style='Red.TButton',
                                  command=self.stop_server,
                                  state='disabled')
        self.stop_btn.grid(row=1, column=0, pady=(0, 8), sticky=(tk.W, tk.E))
        
        # Botón de salir
        ttk.Button(controls_frame, text="👋 Salir", 
                  command=self.on_closing).grid(row=2, column=0, sticky=(tk.W, tk.E))
    
    def update_clients_display(self):
        """Actualizar display de clientes conectados con información detallada"""
        if not self.root.winfo_exists():
            return
            
        self.clients_text.config(state='normal')
        self.clients_text.delete(1.0, tk.END)
        
        if not self.main_app.server_running:
            self.clients_text.insert(tk.END, "⚠️  Servidor detenido\n\n", 'WARNING')
            self.clients_text.insert(tk.END, "No hay clientes conectados.", 'LABEL')
        else:
            # Header
            self.clients_text.insert(tk.END, "╔═══════════════════════════════════\n", 'SEPARATOR')
            self.clients_text.insert(tk.END, "     CLIENTES CONECTADOS\n", 'HEADER')
            self.clients_text.insert(tk.END, "╚═══════════════════════════════════\n\n", 'SEPARATOR')
            
            # Clientes RF
            rf_count = int(self.rf_clients_var.get())
            self.clients_text.insert(tk.END, f"🎛️  RF CLIENTS: ", 'RF_TITLE')
            self.clients_text.insert(tk.END, f"{rf_count}\n", 'VALUE')
            self.clients_text.insert(tk.END, "───────────────────────────────────\n", 'SEPARATOR')
            
            if self.main_app.native_server:
                clients = self.main_app.native_server.get_connected_clients()
                if clients:
                    for idx, client_info in enumerate(clients, 1):
                        addr = client_info.get('address', 'Unknown')
                        channels = client_info.get('channels', [])
                        connected_time = client_info.get('connected_time', 0)
                        last_activity = client_info.get('last_activity', 0)
                        packets_sent = client_info.get('packets_sent', 0)
                        
                        conn_duration = int(time.time() - connected_time) if connected_time > 0 else 0
                        conn_min = conn_duration // 60
                        conn_sec = conn_duration % 60
                        activity_delta = int(time.time() - last_activity) if last_activity > 0 else 0
                        
                        self.clients_text.insert(tk.END, f"\n #{idx}  ", 'LABEL')
                        self.clients_text.insert(tk.END, f"{addr}\n", 'IP')
                        self.clients_text.insert(tk.END, f" │ Canales: ", 'LABEL')
                        self.clients_text.insert(tk.END, f"{channels}\n", 'CHANNEL')
                        self.clients_text.insert(tk.END, f" │ Conectado: ", 'LABEL')
                        self.clients_text.insert(tk.END, f"{conn_min}m {conn_sec}s\n", 'TIME')
                        self.clients_text.insert(tk.END, f" │ Actividad: ", 'LABEL')
                        self.clients_text.insert(tk.END, f"{activity_delta}s ago\n", 'VALUE')
                        self.clients_text.insert(tk.END, f" └ Paquetes: ", 'LABEL')
                        self.clients_text.insert(tk.END, f"{packets_sent}\n", 'VALUE')
                else:
                    self.clients_text.insert(tk.END, "\n  (ningún cliente conectado)\n", 'LABEL')
            else:
                self.clients_text.insert(tk.END, "\n  (servidor no inicializado)\n", 'LABEL')
            
