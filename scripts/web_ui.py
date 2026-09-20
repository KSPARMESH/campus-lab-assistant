"""Interactive Web UI for Campus Lab Equipment Booking Assistant.
Runs a local server with zero extra dependencies (standard library http.server).

    python -m scripts.web_ui
"""
import http.server
import json
import socketserver
import urllib.parse
from pathlib import Path

from app.config import make_providers, open_stores
from app.worker import Worker

PORT = 8080

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Campus Lab Assistant - Multi-Agent AI</title>
    <style>
        :root {
            --bg: #0f172a;
            --surface: #1e293b;
            --surface-hover: #334155;
            --border: #334155;
            --primary: #38bdf8;
            --primary-glow: rgba(56, 189, 248, 0.2);
            --text: #f8fafc;
            --text-dim: #94a3b8;
            --success: #34d399;
            --warning: #fbbf24;
            --danger: #f87171;
            --agent-inv: #c084fc;
            --agent-desk: #f472b6;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        body { background: var(--bg); color: var(--text); display: flex; height: 100vh; overflow: hidden; }
        
        /* Sidebar */
        .sidebar { width: 340px; background: var(--surface); border-right: 1px solid var(--border); display: flex; flex-direction: column; }
        .sidebar-header { padding: 20px; border-bottom: 1px solid var(--border); }
        .sidebar-header h2 { font-size: 1.1rem; color: var(--primary); display: flex; align-items: center; gap: 8px; }
        .sidebar-header p { font-size: 0.8rem; color: var(--text-dim); margin-top: 4px; }
        .sidebar-content { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 16px; }
        
        .card { background: rgba(15, 23, 42, 0.6); border: 1px solid var(--border); border-radius: 8px; padding: 12px; font-size: 0.85rem; }
        .card h3 { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-dim); margin-bottom: 8px; }
        .badge { display: inline-block; padding: 2px 8px; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; }
        .badge-op { background: rgba(52, 211, 153, 0.2); color: var(--success); }
        .badge-maint { background: rgba(248, 113, 113, 0.2); color: var(--danger); }
        .researcher-select { width: 100%; padding: 8px; background: var(--bg); border: 1px solid var(--border); color: var(--text); border-radius: 6px; font-size: 0.9rem; margin-top: 4px; }
        
        /* Main Chat Area */
        .main { flex: 1; display: flex; flex-direction: column; background: var(--bg); }
        .chat-header { padding: 16px 24px; border-bottom: 1px solid var(--border); background: var(--surface); display: flex; justify-content: space-between; align-items: center; }
        .chat-title { font-weight: 600; font-size: 1.1rem; }
        .chat-status { font-size: 0.8rem; color: var(--success); display: flex; align-items: center; gap: 6px; }
        .chat-status::before { content: ""; width: 8px; height: 8px; background: var(--success); border-radius: 50%; display: inline-block; }
        
        .chat-messages { flex: 1; overflow-y: auto; padding: 24px; display: flex; flex-direction: column; gap: 16px; }
        .message { max-width: 80%; padding: 14px 18px; border-radius: 12px; font-size: 0.95rem; line-height: 1.5; }
        .message-user { align-self: flex-end; background: var(--primary); color: #0f172a; font-weight: 500; border-bottom-right-radius: 2px; }
        .message-assistant { align-self: flex-start; background: var(--surface); border: 1px solid var(--border); border-bottom-left-radius: 2px; }
        
        /* Agent Trace Accordion */
        .trace { margin-top: 10px; border-top: 1px solid var(--border); padding-top: 8px; font-size: 0.8rem; font-family: monospace; }
        .trace-item { padding: 4px 0; display: flex; gap: 6px; }
        .trace-tag { font-weight: 600; border-radius: 4px; padding: 1px 4px; }
        .tag-inv { color: var(--agent-inv); background: rgba(192, 132, 252, 0.15); }
        .tag-desk { color: var(--agent-desk); background: rgba(244, 114, 182, 0.15); }
        .tag-sup { color: var(--warning); background: rgba(251, 191, 36, 0.15); }

        /* Input bar */
        .input-bar { padding: 16px 24px; background: var(--surface); border-top: 1px solid var(--border); display: flex; gap: 12px; }
        .input-bar input { flex: 1; padding: 12px 16px; background: var(--bg); border: 1px solid var(--border); color: var(--text); border-radius: 8px; font-size: 0.95rem; outline: none; }
        .input-bar input:focus { border-color: var(--primary); box-shadow: 0 0 0 2px var(--primary-glow); }
        .input-bar button { padding: 12px 24px; background: var(--primary); color: #0f172a; font-weight: 600; border: none; border-radius: 8px; cursor: pointer; transition: 0.2s; }
        .input-bar button:hover { opacity: 0.9; }

        /* Quick prompts */
        .quick-prompts { display: flex; gap: 8px; margin-bottom: 8px; overflow-x: auto; }
        .quick-btn { background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.2); color: var(--primary); border-radius: 9999px; padding: 4px 12px; font-size: 0.75rem; cursor: pointer; white-space: nowrap; }
        .quick-btn:hover { background: rgba(56, 189, 248, 0.2); }
    </style>
</head>
<body>
    <aside class="sidebar">
        <div class="sidebar-header">
            <h2>🔬 Lab Assistant</h2>
            <p>Multi-Agent Durable Booking Desk</p>
        </div>
        <div class="sidebar-content">
            <div class="card">
                <h3>Active Researcher</h3>
                <select id="researcher-select" class="researcher-select">
                    <option value="22CS045">22CS045 - Priya Raman (Safety Level 3)</option>
                    <option value="22IT017">22IT017 - Arjun Kumar (Safety Level 1)</option>
                    <option value="22EC031">22EC031 - Divya Sekar (Safety Level 2)</option>
                    <option value="22ME009">22ME009 - Rahul Roy (Suspended)</option>
                </select>
            </div>
            
            <div class="card">
                <h3>Available Instruments</h3>
                <div id="equipment-list" style="display:flex; flex-direction:column; gap:6px; margin-top:6px;">
                    <div>• <b>SEM Microscope</b> (L3) <span class="badge badge-op">Room 101</span></div>
                    <div>• <b>Oscilloscope 4GHz</b> (L2) <span class="badge badge-op">Room 204</span></div>
                    <div>• <b>GPU Cluster Node A</b> (L1) <span class="badge badge-op">Room 302</span></div>
                    <div>• <b>UV-Vis Spectro</b> (L2) <span class="badge badge-op">Room 105</span></div>
                    <div>• <b>Cleanroom Unit</b> (L3) <span class="badge badge-maint">Maintenance</span></div>
                </div>
            </div>

            <div class="card">
                <h3>Database Policies</h3>
                <div style="color:var(--text-dim); font-size:0.8rem; line-height:1.4;">
                    • <b>Max Active Bookings:</b> 2 slots<br>
                    • <b>Safety Enforcement:</b> Strict (in DB)<br>
                    • <b>Clash Prevention:</b> Atomic locks & keys
                </div>
            </div>
        </div>
    </aside>

    <main class="main">
        <header class="chat-header">
            <div class="chat-title">Campus Lab Equipment Multi-Agent Console</div>
            <div class="chat-status">Multi-Agent System Online</div>
        </header>

        <div class="chat-messages" id="messages">
            <div class="message message-assistant">
                👋 Hello! I am the <b>Campus Lab Equipment Assistant</b>.<br>
                I coordinate with the <b>Inventory Specialist</b> (to look up instruments and slots) and the <b>Booking Desk Specialist</b> (to check your safety level and book slots).<br>
                How can I assist you with lab equipment today?
            </div>
        </div>

        <div style="padding: 0 24px;">
            <div class="quick-prompts">
                <button class="quick-btn" onclick="setPrompt('Is Scanning Electron Microscope (SEM) available on 2026-09-21? If so, book slot 1 for me.')">Book SEM Slot 1</button>
                <button class="quick-btn" onclick="setPrompt('Can I book the Scanning Electron Microscope (SEM) slot 2?')">Check Arjun Safety Refusal</button>
                <button class="quick-btn" onclick="setPrompt('What equipment is available in the lab?')">List All Equipment</button>
            </div>
        </div>

        <form class="input-bar" id="chat-form">
            <input type="text" id="user-input" placeholder="Ask about instruments, available slots, or book equipment..." required autocomplete="off" />
            <button type="submit">Send</button>
        </form>
    </main>

    <script>
        const messages = document.getElementById('messages');
        const form = document.getElementById('chat-form');
        const input = document.getElementById('user-input');
        const researcherSelect = document.getElementById('researcher-select');

        function setPrompt(text) {
            input.value = text;
            input.focus();
        }

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const text = input.value.trim();
            if (!text) return;

            const rollNo = researcherSelect.value;
            input.value = '';

            // Render user message
            const userDiv = document.createElement('div');
            userDiv.className = 'message message-user';
            userDiv.textContent = text;
            messages.appendChild(userDiv);

            // Render loading message
            const loadingDiv = document.createElement('div');
            loadingDiv.className = 'message message-assistant';
            loadingDiv.innerHTML = '<em>Consulting specialists and checking lab database...</em>';
            messages.appendChild(loadingDiv);
            messages.scrollTop = messages.scrollHeight;

            try {
                const res = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ roll_no: rollNo, message: text })
                });
                const data = await res.json();

                let traceHtml = '';
                if (data.steps && data.steps.length > 0) {
                    traceHtml = '<div class="trace"><div style="color:var(--text-dim); margin-bottom:4px;">Multi-Agent Execution Trace:</div>';
                    data.steps.forEach(s => {
                        let tagClass = s.agent === 'inventory' ? 'tag-inv' : (s.agent === 'booking_desk' ? 'tag-desk' : 'tag-sup');
                        let replayNote = s.replayed ? ' <span style="color:var(--success)">[replayed]</span>' : '';
                        traceHtml += `<div class="trace-item"><span class="trace-tag ${tagClass}">[${s.agent}]</span> <span>${s.tool || s.kind}${replayNote}</span></div>`;
                    });
                    traceHtml += '</div>';
                }

                loadingDiv.innerHTML = (data.reply || data.error || 'Done.') + traceHtml;
            } catch (err) {
                loadingDiv.innerHTML = '<span style="color:var(--danger)">Error communicating with server: ' + err + '</span>';
            }
            messages.scrollTop = messages.scrollHeight;
        });
    </script>
</body>
</html>
"""


class LabAssistantHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path == "/api/chat":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            payload = json.loads(body.decode("utf-8"))

            roll_no = payload.get("roll_no", "22CS045")
            message = payload.get("message", "")

            store, db = open_stores()
            providers = make_providers(mock=True)

            steps_recorded = []

            def trace_step(step):
                steps_recorded.append({
                    "agent": step.get("agent", "supervisor"),
                    "kind": step.get("kind"),
                    "tool": step.get("tool"),
                    "replayed": step.get("replayed", False),
                    "ok": step.get("ok", True)
                })

            thread_id = store.create_thread(roll_no)
            run_id = store.enqueue(thread_id, message, providers["supervisor"].model)

            worker = Worker(store, db, providers, worker_id="web-worker", on_step=trace_step)
            worker.run_until_idle()

            run = store.get_run(run_id)
            history = store.load_history(thread_id)
            reply = history[-1]["text"] if run["status"] == "succeeded" else f"Run {run['status']}: {run.get('error_code')}"

            response_data = {
                "run_id": run_id,
                "status": run["status"],
                "reply": reply,
                "steps": steps_recorded
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()


def main():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), LabAssistantHandler) as httpd:
        print(f"\n=====================================================================")
        print(f"  Campus Lab Assistant Web UI running at: http://localhost:{PORT}")
        print(f"  Open http://localhost:{PORT} in your browser to chat with the agent!")
        print(f"=====================================================================\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")


if __name__ == "__main__":
    main()
