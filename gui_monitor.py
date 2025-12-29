import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import time
import sounddevice as sd
import queue
from datetime import datetime
import os

DEFAULT_SAMPLE_RATE = 48000  # Tasa de muestreo por defecto

class AudioMonitorGUI:
    def __init__(self, main_app):
        self.main_app = main_app
        self.root = tk.Tk()
        self.root.title("Fichatech Monitor - Audio RF Server")
        self.root.geometry("900x750")
        self.root.configure(bg='#1e1e2e')
        
        # Variables de estado
        self.running = True
        self.update_thread = None
        self.stats_queue = queue.Queue()
        
        # Variables de dispositivo
        self.selected_device_id = -1
        self.selected_device_name = tk.StringVar(value="No seleccionado")
        
        # Configurar estilo
        self.setup_styles()
        
        # Inicializar interfaz
        self.setup_ui()
        
        # Configurar cierre
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def setup_styles(self):
        """Configurar estilos tkinter"""
        style = ttk.Style()
        
        # Colores
        self.bg_color = '#1e1e2e'
        self.fg_color = '#cdd6f4'
        self.accent_color = '#89b4fa'
        self.success_color = '#a6e3a1'
        self.warning_color = '#f9e2af'
        self.error_color = '#f38ba8'
        self.panel_color = '#313244'
        self.highlight_color = '#74c7ec'
        
        # Configurar temas
        style.theme_use('clam')
        
        # Configurar colores
        style.configure('Title.TLabel', 
                       background=self.bg_color,
                       foreground=self.accent_color,
                       font=('Segoe UI', 18, 'bold'))
        
        style.configure('Subtitle.TLabel',
                       background=self.bg_color,
                       foreground=self.fg_color,
                       font=('Segoe UI', 11))
        
        style.configure('Panel.TFrame',
                       background=self.panel_color,
                       relief='flat')
        
        style.configure('Stat.TLabel',
                       background=self.panel_color,
                       foreground=self.fg_color,
                       font=('Segoe UI', 10))
        
        style.configure('Value.TLabel',
                       background=self.panel_color,
                       foreground=self.highlight_color,
                       font=('Segoe UI', 10, 'bold'))
        
        style.configure('Device.TRadiobutton',
                       background=self.panel_color,
                       foreground=self.fg_color,
                       font=('Segoe UI', 9))
        
        style.configure('Green.TButton',
                       background=self.success_color,
                       foreground='black',
                       font=('Segoe UI', 10, 'bold'))
        
        style.configure('Red.TButton',
                       background=self.error_color,
                       foreground='black',
                       font=('Segoe UI', 10, 'bold'))
        
        style.configure('Blue.TButton',
                       background=self.accent_color,
                       foreground='black',
                       font=('Segoe UI', 10, 'bold'))
        
        # Estilo para dispositivo seleccionado
        style.configure('Selected.TFrame',
                       background='#45475a',
                       relief='sunken')
    
    def setup_ui(self):
        """Configurar elementos de la interfaz"""
        # Frame principal
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configurar expansión
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=0)
        main_frame.rowconfigure(3, weight=1)
        
        # Encabezado con logo y título
        self.setup_header(main_frame)
        
        # Frame de estado actual
        self.setup_status_frame(main_frame)
        
        # Frame de selección de dispositivo
        self.setup_device_frame(main_frame)
        
        # Frame de logs
        self.setup_logs_frame(main_frame)
        
        # Frame de controles
        self.setup_controls_frame(main_frame)
        
        # Iniciar actualización de estadísticas
        self.start_updates()
    
    def setup_header(self, parent):
        """Configurar encabezado con logo"""
        header_frame = ttk.Frame(parent, style='Panel.TFrame')
        header_frame.grid(row=0, column=0, pady=(0, 20), sticky=(tk.W, tk.E))
        header_frame.columnconfigure(1, weight=1)
        
        # Logo/Icono (usando emoji como placeholder)
        logo_label = ttk.Label(header_frame,
                              text="🎛️",
                              font=('Segoe UI', 24),
                              background=self.panel_color)
        logo_label.grid(row=0, column=0, padx=(10, 15), pady=10, sticky=tk.W)
        
        # Título
        title_frame = ttk.Frame(header_frame, style='Panel.TFrame')
        title_frame.grid(row=0, column=1, sticky=tk.W)
        
        title_label = ttk.Label(title_frame,
                               text="Fichatech Monitor",
                               style='Title.TLabel')
        title_label.pack(anchor=tk.W)
        
        subtitle_label = ttk.Label(title_frame,
                                  text="Streaming de audio multicanal en tiempo real",
                                  style='Subtitle.TLabel')
        subtitle_label.pack(anchor=tk.W, pady=(0, 5))
        
        # Estado del servidor
        self.server_status_var = tk.StringVar(value="🔴 Servidor detenido")
        status_label = ttk.Label(title_frame,
                                textvariable=self.server_status_var,
                                font=('Segoe UI', 10, 'bold'),
                                foreground=self.error_color,
                                background=self.panel_color)
        status_label.pack(anchor=tk.W)
    
    def setup_status_frame(self, parent):
        """Frame de estado actual"""
        status_frame = ttk.LabelFrame(parent,
                                     text="📊 Estado Actual",
                                     padding="15")
        status_frame.grid(row=1, column=0, pady=(0, 15), sticky=(tk.W, tk.E))
        
        # Grid para estado
        status_frame.columnconfigure(0, weight=1)
        status_frame.columnconfigure(1, weight=1)
        status_frame.columnconfigure(2, weight=1)
        
        # Dispositivo seleccionado
        device_status_frame = ttk.Frame(status_frame, style='Panel.TFrame', padding="10")
        device_status_frame.grid(row=0, column=0, padx=5, pady=5, sticky=(tk.W, tk.E))
        
        device_label = ttk.Label(device_status_frame,
                                text="🎙️ Dispositivo:",
                                style='Stat.TLabel')
        device_label.pack(anchor=tk.W)
        
        self.device_name_label = ttk.Label(device_status_frame,
                                          textvariable=self.selected_device_name,
                                          style='Value.TLabel')
        self.device_name_label.pack(anchor=tk.W, pady=(5, 0))
        
        # Información del dispositivo
        self.device_info_var = tk.StringVar(value="Canales: -- | Sample Rate: -- Hz")
        device_info_label = ttk.Label(device_status_frame,
                                     textvariable=self.device_info_var,
                                     style='Stat.TLabel')
        device_info_label.pack(anchor=tk.W)
        
        # Botón para cambiar dispositivo
        change_btn = ttk.Button(device_status_frame,
                               text="🔄 Cambiar",
                               command=self.show_device_selector,
                               style='Blue.TButton')
        change_btn.pack(anchor=tk.W, pady=(10, 0))
    
    def setup_device_frame(self, parent):
        """Frame de selección de dispositivo (oculto inicialmente)"""
        self.device_selector_frame = ttk.LabelFrame(parent,
                                                   text="🎙️ Seleccionar Interfaz de Audio",
                                                   padding="15")
        self.device_selector_frame.grid(row=2, column=0, pady=(0, 15), sticky=(tk.W, tk.E, tk.N, tk.S))
        self.device_selector_frame.grid_remove()  # Ocultar inicialmente
        
        # Variable para dispositivo seleccionado
        self.device_var = tk.IntVar(value=-1)
        
        # Frame para lista de dispositivos con scrollbar
        list_container = ttk.Frame(self.device_selector_frame)
        list_container.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        list_container.columnconfigure(0, weight=1)
        list_container.rowconfigure(0, weight=1)
        
        # Canvas y scrollbar
        self.device_canvas = tk.Canvas(list_container, bg=self.panel_color, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=self.device_canvas.yview)
        self.scrollable_frame = ttk.Frame(self.device_canvas, style='Panel.TFrame')
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.device_canvas.configure(scrollregion=self.device_canvas.bbox("all"))
        )
        
        self.device_canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.device_canvas.configure(yscrollcommand=scrollbar.set)
        
        # Empaquetar canvas y scrollbar
        self.device_canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # Botones de control
        button_frame = ttk.Frame(self.device_selector_frame)
        button_frame.grid(row=1, column=0, pady=(15, 0), sticky=(tk.W, tk.E))
        
        select_btn = ttk.Button(button_frame,
                               text="✅ Seleccionar",
                               command=self.select_device,
                               style='Green.TButton')
        select_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        cancel_btn = ttk.Button(button_frame,
                               text="❌ Cancelar",
                               command=self.hide_device_selector)
        cancel_btn.pack(side=tk.LEFT)
        
        refresh_btn = ttk.Button(button_frame,
                                text="🔄 Actualizar Lista",
                                command=self.refresh_devices)
        refresh_btn.pack(side=tk.RIGHT)
    
    def show_device_selector(self):
        """Mostrar selector de dispositivos"""
        if not hasattr(self, 'device_widgets'):
            self.load_devices()
        
        self.device_selector_frame.grid()
        self.root.update_idletasks()
        
        # Scroll al dispositivo seleccionado si hay uno
        if self.selected_device_id != -1:
            self.device_var.set(self.selected_device_id)
            # Calcular posición para scroll
            devices = sd.query_devices()
            input_devices = [i for i, d in enumerate(devices) if d['max_input_channels'] > 0]
            if self.selected_device_id in input_devices:
                index = input_devices.index(self.selected_device_id)
                total = len(input_devices)
                if total > 0:
                    self.device_canvas.yview_moveto(index / total)
    
    def hide_device_selector(self):
        """Ocultar selector de dispositivos"""
        self.device_selector_frame.grid_remove()
    
    def load_devices(self):
        """Cargar lista de dispositivos"""
        self.device_widgets = []
        
        # Limpiar frame si ya tiene widgets
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        devices = sd.query_devices()
        input_devices = []
        
        for i, device in enumerate(devices):
            if device['max_input_channels'] > 0:  # Solo dispositivos de entrada
                input_devices.append((i, device))
        
        # Preseleccionar dispositivo con más de 2 canales
        preselected_index = -1
        for i, (device_id, device) in enumerate(input_devices):
            if device['max_input_channels'] > 2 and preselected_index == -1:
                preselected_index = device_id
        
        for i, (device_id, device) in enumerate(input_devices):
            # Crear frame para cada dispositivo
            device_item = ttk.Frame(self.scrollable_frame, padding="10")
            if device_id == self.selected_device_id:
                device_item.config(style='Selected.TFrame')
            device_item.pack(fill=tk.X, pady=2)
            
            # Radio button
            rb = ttk.Radiobutton(device_item,
                                text=f"{device['name']}",
                                variable=self.device_var,
                                value=device_id,
                                style='Device.TRadiobutton',
                                command=lambda d=device_id: self.highlight_device(d))
            rb.pack(anchor=tk.W)
            
            # Información adicional
            channels = device['max_input_channels']
            samplerate = int(device['default_samplerate']) if device['default_samplerate'] else DEFAULT_SAMPLE_RATE
            
            info_text = f"  Canales: {channels} | Sample Rate: {samplerate} Hz"
            if channels > 2:
                info_text += " ⭐"
            
            info_label = ttk.Label(device_item,
                                  text=info_text,
                                  style='Stat.TLabel')
            info_label.pack(anchor=tk.W, padx=(20, 0))
            
            self.device_widgets.append((device_id, device_item))
        
        # Configurar preselección
        if preselected_index != -1 and self.selected_device_id == -1:
            self.device_var.set(preselected_index)
            self.update_device_display(preselected_index)
    
    def highlight_device(self, device_id):
        """Resaltar dispositivo seleccionado"""
        for d_id, widget in self.device_widgets:
            if d_id == device_id:
                widget.config(style='Selected.TFrame')
            else:
                widget.config(style='Panel.TFrame')
    
    def select_device(self):
        """Seleccionar dispositivo de la lista"""
        device_id = self.device_var.get()
        
        if device_id == -1:
            self.log_message("❌ Por favor selecciona un dispositivo de la lista", 'ERROR')
            return
        
        self.update_device_display(device_id)
        self.hide_device_selector()
        self.log_message(f"✅ Dispositivo seleccionado: {self.selected_device_name.get()}", 'SUCCESS')
    
    def update_device_display(self, device_id):
        """Actualizar display con información del dispositivo"""
        try:
            device_info = sd.query_devices(device_id)
            self.selected_device_id = device_id
            self.selected_device_name.set(device_info['name'])
            
            channels = device_info['max_input_channels']
            samplerate = int(device_info['default_samplerate']) if device_info['default_samplerate'] else DEFAULT_SAMPLE_RATE
            self.device_info_var.set(f"Canales: {channels} | Sample Rate: {samplerate} Hz")
            
            # Actualizar estadísticas
            if self.main_app.server_running:
                self.log_message(f"⚠️ Dispositivo cambiado. Reinicia el servidor para aplicar cambios.", 'WARNING')
            
        except Exception as e:
            self.log_message(f"❌ Error al obtener información del dispositivo: {e}", 'ERROR')
    
    def refresh_devices(self):
        """Actualizar lista de dispositivos"""
        self.load_devices()
        self.log_message("🔄 Lista de dispositivos actualizada", 'INFO')
    
    def setup_logs_frame(self, parent):
        """Frame de logs del sistema"""
        logs_frame = ttk.LabelFrame(parent,
                                   text="📝 Logs del Sistema",
                                   padding="10")
        logs_frame.grid(row=3, column=0, pady=(0, 20), sticky=(tk.W, tk.E, tk.N, tk.S))
        logs_frame.columnconfigure(0, weight=1)
        logs_frame.rowconfigure(0, weight=1)
        
        # Área de texto para logs
        self.log_text = scrolledtext.ScrolledText(logs_frame,
                                                 height=8,
                                                 bg=self.panel_color,
                                                 fg=self.fg_color,
                                                 font=('Consolas', 9),
                                                 insertbackground=self.accent_color)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configurar tags para colores
        self.log_text.tag_config('INFO', foreground=self.fg_color)
        self.log_text.tag_config('SUCCESS', foreground=self.success_color)
        self.log_text.tag_config('WARNING', foreground=self.warning_color)
        self.log_text.tag_config('ERROR', foreground=self.error_color)
        self.log_text.tag_config('RF', foreground='#cba6f7')
        self.log_text.tag_config('WEB', foreground='#89dceb')
    
    def setup_controls_frame(self, parent):
        """Frame de controles"""
        controls_frame = ttk.Frame(parent)
        controls_frame.grid(row=4, column=0, sticky=(tk.W, tk.E))
        controls_frame.columnconfigure(0, weight=1)
        
        # Botón de inicio
        self.start_btn = ttk.Button(controls_frame,
                                   text="🚀 Iniciar Servidor",
                                   style='Green.TButton',
                                   command=self.start_server)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        # Botón de detener
        self.stop_btn = ttk.Button(controls_frame,
                                  text="🛑 Detener Servidor",
                                  style='Red.TButton',
                                  command=self.stop_server,
                                  state='disabled')
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        # Botón de salir
        exit_btn = ttk.Button(controls_frame,
                             text="👋 Salir",
                             command=self.on_closing)
        exit_btn.pack(side=tk.RIGHT, padx=5)
    
    def log_message(self, message, tag='INFO'):
        """Agregar mensaje al log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        self.log_text.insert(tk.END, log_entry, tag)
        self.log_text.see(tk.END)
        self.log_text.update()
    
    def start_server(self):
        """Iniciar el servidor"""
        if self.selected_device_id == -1:
            self.log_message("❌ Por favor selecciona un dispositivo primero", 'ERROR')
            self.show_device_selector()
            return
        
        device_info = sd.query_devices(self.selected_device_id)
        self.log_message(f"🎙️ Iniciando servidor con: {device_info['name']}", 'RF')
        self.log_message(f"   Canales: {device_info['max_input_channels']}", 'RF')
        
        # Enviar comando al servidor principal
        if hasattr(self.main_app, 'start_server_with_device'):
            self.main_app.start_server_with_device(self.selected_device_id)
        
        # Actualizar estado
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.server_status_var.set("🟢 Servidor ejecutándose")
        
        self.log_message("✅ Servidor iniciado correctamente", 'SUCCESS')
    
    def stop_server(self):
        """Detener el servidor"""
        # Enviar comando al servidor principal
        if hasattr(self.main_app, 'stop_server'):
            self.main_app.stop_server()
        
        # Actualizar estado
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.server_status_var.set("🔴 Servidor detenido")
        
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
            
            time.sleep(0.5)  # Actualizar cada 500ms
    
    def queue_log_message(self, message, tag='INFO'):
        """Agregar mensaje al log desde otros threads"""
        self.stats_queue.put((message, tag))
    
    def on_closing(self):
        """Manejar cierre de la ventana"""
        self.running = False
        if hasattr(self.main_app, 'cleanup'):
            self.main_app.cleanup()
        self.root.destroy()
    
    def run(self):
        """Ejecutar la GUI"""
        self.root.mainloop()