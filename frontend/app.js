async function pollState() {
    try {
        const response = await fetch('/api/state');
        const data = await response.json();
        document.getElementById('status').innerText = `System Status: ${data.status}`;
    } catch (error) {
        document.getElementById('status').innerText = 'System Offline - Reconnecting...';
        console.error("Polling error:", error);
    }
}

// Poll the server every 500ms
setInterval(pollState, 500);