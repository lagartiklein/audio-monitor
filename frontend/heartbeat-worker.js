// heartbeat-worker.js
// Web Worker para enviar heartbeats periódicos al servidor aunque la pestaña esté en segundo plano

let interval = null;
let lastTimestamp = Date.now();

self.onmessage = function(e) {
    if (e.data && e.data.type === 'start') {
        const period = e.data.period || 3000;
        if (interval) clearInterval(interval);
        interval = setInterval(() => {
            lastTimestamp = Date.now();
            self.postMessage({ type: 'heartbeat', timestamp: lastTimestamp });
        }, period);
    } else if (e.data && e.data.type === 'stop') {
        if (interval) clearInterval(interval);
        interval = null;
    }
};
