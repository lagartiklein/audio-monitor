class AudioMonitor {
    constructor() {
        this.socket = null;
        this.activeChannels = new Set();
        this.init();
    }

    async init() {
        console.log('[AudioMonitor] Initializing...');
        this.socket = io({ transports: ['websocket'], reconnection: true });
        
        this.socket.on('connect', () => {
            console.log('[Socket] Connected');
            document.getElementById('status').textContent = 'Status: Connected';
        });
        
        this.socket.on('disconnect', () => {
            console.log('[Socket] Disconnected');
            document.getElementById('status').textContent = 'Status: Disconnected';
        });
        
        this.socket.on('device_info', (info) => {
            console.log('Device info:', info);
            document.getElementById('device-info').innerHTML = 
                `<strong>${info.name}</strong> | ${info.channels} channels | ${info.sample_rate}Hz`;
        });
        
        this.socket.on('audio', (data) => {
            console.log('Audio packet received:', data.byteLength, 'bytes');
        });
        
        this.socket.on('pong', (data) => {
            const latency = Date.now() - data.client_timestamp;
            console.log('Network latency:', latency + 'ms');
        });
        
        setInterval(() => {
            if (this.socket?.connected) {
                this.socket.emit('ping', { timestamp: Date.now() });
            }
        }, 2000);
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', () => {
    window.audioMonitor = new AudioMonitor();
});