"""Interactive High-Tech Web UI for Campus Lab Equipment Booking Assistant.
Zero external dependencies (uses standard library http.server).

    python -m scripts.web_ui
"""
import http.server
import json
import socketserver
import time
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
    <title>Campus Lab Assistant | Agentic AI Orchestrator</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-base: #090d16;
            --bg-surface: #111827;
            --bg-elevated: #1e293b;
            --bg-glass: rgba(17, 24, 39, 0.75);
            --border: rgba(255, 255, 255, 0.08);
            --border-glow: rgba(56, 189, 248, 0.3);
            --primary: #38bdf8;
            --primary-gradient: linear-gradient(135deg, #38bdf8 0%, #818cf8 100%);
            --accent-purple: #c084fc;
            --accent-pink: #f472b6;
            --accent-emerald: #34d399;
            --accent-amber: #fbbf24;
            --accent-rose: #fb7185;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --text-dark: #0f172a;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background-color: var(--bg-base);
            color: var(--text-main);
            font-family: 'Plus Jakarta Sans', sans-serif;
            display: flex;
            flex-direction: column;
            height: 100vh;
            overflow: hidden;
            background-image: 
                radial-gradient(at 0% 0%, rgba(56, 189, 248, 0.12) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(192, 132, 252, 0.08) 0px, transparent 50%);
        }

        /* Top Navigation */
        .navbar {
            height: 64px;
            background: var(--bg-glass);
            backdrop-filter: blur(16px);
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 28px;
            z-index: 10;
        }
        .brand {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .brand-icon {
            width: 36px;
            height: 36px;
            border-radius: 10px;
            background: var(--primary-gradient);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.2rem;
            box-shadow: 0 0 16px rgba(56, 189, 248, 0.4);
        }
        .brand-text h1 {
            font-size: 1.05rem;
            font-weight: 700;
            letter-spacing: -0.01em;
            background: linear-gradient(90deg, #ffffff, #93c5fd);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .brand-text p {
            font-size: 0.72rem;
            color: var(--text-muted);
            font-family: 'JetBrains Mono', monospace;
        }

        .nav-meta {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .agent-pill {
            display: flex;
            align-items: center;
            gap: 6px;
            padding: 6px 12px;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--border);
        }
        .dot-pulse {
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: var(--accent-emerald);
            box-shadow: 0 0 8px var(--accent-emerald);
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { transform: scale(1); opacity: 1; }
            50% { transform: scale(1.3); opacity: 0.6; }
        }

        /* App Layout */
        .app-container {
            flex: 1;
            display: flex;
            height: calc(100vh - 64px);
            overflow: hidden;
        }

        /* Sidebar Dashboard */
        .sidebar {
            width: 400px;
            background: var(--bg-surface);
            border-right: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            overflow-y: auto;
        }
        .sidebar-section {
            padding: 20px;
            border-bottom: 1px solid var(--border);
        }
        .section-title {
            font-size: 0.75rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--text-muted);
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        /* Researcher Cards */
        .researcher-cards {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        .researcher-card {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 12px;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .researcher-card:hover {
            background: rgba(56, 189, 248, 0.05);
            border-color: rgba(56, 189, 248, 0.3);
        }
        .researcher-card.active {
            background: rgba(56, 189, 248, 0.1);
            border-color: var(--primary);
            box-shadow: 0 0 16px rgba(56, 189, 248, 0.15);
        }
        .res-name {
            font-weight: 600;
            font-size: 0.88rem;
        }
        .res-dept {
            font-size: 0.75rem;
            color: var(--text-muted);
        }
        .tier-badge {
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 0.7rem;
            font-weight: 700;
            font-family: 'JetBrains Mono', monospace;
        }
        .tier-3 { background: rgba(52, 211, 153, 0.15); color: var(--accent-emerald); border: 1px solid rgba(52, 211, 153, 0.3); }
        .tier-2 { background: rgba(56, 189, 248, 0.15); color: var(--primary); border: 1px solid rgba(56, 189, 248, 0.3); }
        .tier-1 { background: rgba(251, 191, 36, 0.15); color: var(--accent-amber); border: 1px solid rgba(251, 191, 36, 0.3); }
        .tier-sus { background: rgba(251, 113, 133, 0.15); color: var(--accent-rose); border: 1px solid rgba(251, 113, 133, 0.3); }

        /* Instrument Matrix */
        .instrument-item {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 10px 14px;
            margin-bottom: 8px;
            font-size: 0.82rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .instrument-item .badge {
            padding: 2px 8px;
            border-radius: 9999px;
            font-size: 0.7rem;
            font-weight: 600;
        }
        .badge-live { background: rgba(52, 211, 153, 0.12); color: var(--accent-emerald); }
        .badge-off { background: rgba(251, 113, 133, 0.12); color: var(--accent-rose); }

        /* Stats Grid */
        .stats-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
        }
        .stat-card {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 10px;
            text-align: center;
        }
        .stat-value {
            font-size: 1.2rem;
            font-weight: 800;
            color: var(--primary);
            font-family: 'JetBrains Mono', monospace;
        }
        .stat-label {
            font-size: 0.7rem;
            color: var(--text-muted);
            margin-top: 2px;
        }

        /* Main Chat Area */
        .chat-main {
            flex: 1;
            display: flex;
            flex-direction: column;
            background: transparent;
            position: relative;
        }

        .chat-stream {
            flex: 1;
            overflow-y: auto;
            padding: 28px;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        /* Message Bubbles */
        .msg {
            max-width: 82%;
            display: flex;
            flex-direction: column;
            gap: 6px;
            animation: fadeIn 0.3s ease;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(6px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .msg-user {
            align-self: flex-end;
        }
        .msg-user .msg-content {
            background: var(--primary-gradient);
            color: var(--text-dark);
            font-weight: 600;
            border-radius: 16px 16px 4px 16px;
            padding: 14px 18px;
            box-shadow: 0 4px 20px rgba(56, 189, 248, 0.25);
        }
        .msg-assistant {
            align-self: flex-start;
        }
        .msg-assistant .msg-content {
            background: var(--bg-surface);
            border: 1px solid var(--border);
            color: var(--text-main);
            border-radius: 16px 16px 16px 4px;
            padding: 18px 22px;
            line-height: 1.6;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
        }

        /* Trace Container */
        .trace-box {
            margin-top: 14px;
            border-radius: 12px;
            background: rgba(0, 0, 0, 0.35);
            border: 1px solid var(--border);
            padding: 12px 14px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.78rem;
        }
        .trace-title {
            color: var(--text-muted);
            font-size: 0.7rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .trace-step {
            padding: 4px 0;
            display: flex;
            align-items: baseline;
            gap: 8px;
            line-height: 1.4;
        }
        .badge-agent {
            padding: 2px 6px;
            border-radius: 4px;
            font-weight: 700;
            font-size: 0.68rem;
            text-transform: uppercase;
        }
        .agent-sup { background: rgba(251, 191, 36, 0.2); color: var(--accent-amber); }
        .agent-inv { background: rgba(192, 132, 252, 0.2); color: var(--accent-purple); }
        .agent-desk { background: rgba(244, 114, 182, 0.2); color: var(--accent-pink); }
        .trace-replay {
            color: var(--accent-emerald);
            font-weight: 600;
            background: rgba(52, 211, 153, 0.1);
            padding: 1px 5px;
            border-radius: 4px;
        }

        /* Input Controls */
        .chat-footer {
            padding: 20px 28px;
            background: var(--bg-surface);
            border-top: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        .quick-chips {
            display: flex;
            gap: 8px;
            overflow-x: auto;
            padding-bottom: 4px;
        }
        .chip {
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--border);
            color: var(--primary);
            padding: 6px 14px;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
            cursor: pointer;
            white-space: nowrap;
            transition: all 0.2s;
        }
        .chip:hover {
            background: rgba(56, 189, 248, 0.15);
            border-color: var(--primary);
            transform: translateY(-1px);
        }

        .input-wrapper {
            display: flex;
            gap: 12px;
            position: relative;
        }
        .input-field {
            flex: 1;
            padding: 14px 20px;
            background: var(--bg-base);
            border: 1px solid var(--border);
            color: var(--text-main);
            border-radius: 12px;
            font-size: 0.95rem;
            outline: none;
            transition: all 0.2s;
        }
        .input-field:focus {
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.2);
        }
        .btn-send {
            padding: 0 28px;
            background: var(--primary-gradient);
            color: var(--text-dark);
            border: none;
            border-radius: 12px;
            font-weight: 700;
            font-size: 0.95rem;
            cursor: pointer;
            transition: all 0.2s;
            box-shadow: 0 4px 16px rgba(56, 189, 248, 0.3);
        }
        .btn-send:hover {
            opacity: 0.9;
            transform: scale(1.02);
        }
    </style>
</head>
<body>
    <nav class="navbar">
        <div class="brand">
            <div class="brand-icon">🔬</div>
            <div class="brand-text">
                <h1>Campus Lab Assistant</h1>
                <p>Autonomous Multi-Agent AI System</p>
            </div>
        </div>
        <div class="nav-meta">
            <div class="agent-pill"><span class="dot-pulse"></span> Supervisor Online</div>
            <div class="agent-pill">🔒 Supabase / SQLite Dual-DB</div>
            <div class="agent-pill">✅ 26 Tests Verified</div>
        </div>
    </nav>

    <div class="app-container">
        <!-- Sidebar -->
        <aside class="sidebar">
            <div class="sidebar-section">
                <div class="section-title">
                    <span>Authenticated Researcher</span>
                    <span style="color:var(--primary); font-size:0.7rem;">Click to Switch</span>
                </div>
                <div class="researcher-cards">
                    <div class="researcher-card active" onclick="selectResearcher('22CS045', this)">
                        <div>
                            <div class="res-name">Priya Raman</div>
                            <div class="res-dept">Roll: 22CS045 • Computer Science</div>
                        </div>
                        <span class="tier-badge tier-3">Level 3</span>
                    </div>
                    <div class="researcher-card" onclick="selectResearcher('22IT017', this)">
                        <div>
                            <div class="res-name">Arjun Kumar</div>
                            <div class="res-dept">Roll: 22IT017 • Information Tech</div>
                        </div>
                        <span class="tier-badge tier-1">Level 1</span>
                    </div>
                    <div class="researcher-card" onclick="selectResearcher('22EC031', this)">
                        <div>
                            <div class="res-name">Divya Sekar</div>
                            <div class="res-dept">Roll: 22EC031 • Electronics</div>
                        </div>
                        <span class="tier-badge tier-2">Level 2</span>
                    </div>
                    <div class="researcher-card" onclick="selectResearcher('22ME009', this)">
                        <div>
                            <div class="res-name">Rahul Roy</div>
                            <div class="res-dept">Roll: 22ME009 • Mechanical</div>
                        </div>
                        <span class="tier-badge tier-sus">Suspended</span>
                    </div>
                </div>
            </div>

            <div class="sidebar-section">
                <div class="section-title">Scientific Instruments</div>
                <div class="instrument-item">
                    <div><b>Scanning Electron Microscope</b><br><span style="color:var(--text-muted); font-size:0.72rem;">Central Lab 101 • Req: Level 3</span></div>
                    <span class="badge badge-live">2 Slots Open</span>
                </div>
                <div class="instrument-item">
                    <div><b>Digital Phosphor Oscilloscope</b><br><span style="color:var(--text-muted); font-size:0.72rem;">Circuits Lab 204 • Req: Level 2</span></div>
                    <span class="badge badge-live">1 Slot Open</span>
                </div>
                <div class="instrument-item">
                    <div><b>GPU Cluster (Node A)</b><br><span style="color:var(--text-muted); font-size:0.72rem;">AI Lab 302 • Req: Level 1</span></div>
                    <span class="badge badge-live">3 Slots Open</span>
                </div>
                <div class="instrument-item">
                    <div><b>UV-Vis Spectrophotometer</b><br><span style="color:var(--text-muted); font-size:0.72rem;">Materials Lab 105 • Req: Level 2</span></div>
                    <span class="badge badge-live">2 Slots Open</span>
                </div>
                <div class="instrument-item">
                    <div><b>Cleanroom Photolithography</b><br><span style="color:var(--text-muted); font-size:0.72rem;">Cleanroom 110 • Req: Level 3</span></div>
                    <span class="badge badge-off">Maintenance</span>
                </div>
            </div>

            <div class="sidebar-section">
                <div class="section-title">Database & Policy Engine</div>
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-value">2</div>
                        <div class="stat-label">Max Active Bookings</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">SHA-256</div>
                        <div class="stat-label">Idempotency Keys</div>
                    </div>
                </div>
            </div>
        </aside>

        <!-- Main Chat Area -->
        <main class="chat-main">
            <div class="chat-stream" id="chat-stream">
                <div class="msg msg-assistant">
                    <div class="msg-content">
                        👋 <b>Welcome to the Campus Lab Equipment Booking Assistant.</b><br>
                        I am your central autonomous supervisor. I coordinate directly with:
                        <ul style="margin: 8px 0 8px 18px;">
                            <li><b>Inventory Specialist</b> (Read-Only catalogue & availability lookups)</li>
                            <li><b>Booking Desk Specialist</b> (Policy validation, atomic slot reservation & notifications)</li>
                        </ul>
                        Choose a quick action below or ask any question to get started!
                    </div>
                </div>
            </div>

            <footer class="chat-footer">
                <div class="quick-chips">
                    <button class="chip" onclick="sendQuickPrompt('Is Scanning Electron Microscope (SEM) available on 2026-09-21? If it is, book slot 1 for me and send a confirmation.')">⚡ Book SEM Slot 1 (Happy Path)</button>
                    <button class="chip" onclick="testArjunRejection()">⚠️ Test Safety Refusal (Arjun Level 1 vs SEM Level 3)</button>
                    <button class="chip" onclick="testRahulSuspension()">🚫 Test Suspended Researcher (Rahul Roy)</button>
                    <button class="chip" onclick="sendQuickPrompt('What instruments are available in the lab?')">🔍 List All Instruments</button>
                </div>

                <form class="input-wrapper" id="chat-form">
                    <input type="text" id="user-input" class="input-field" placeholder="Type a message or select a test scenario above..." required autocomplete="off" />
                    <button type="submit" class="btn-send">Execute</button>
                </form>
            </footer>
        </main>
    </div>

    <script>
        let currentRollNo = '22CS045';
        const stream = document.getElementById('chat-stream');
        const form = document.getElementById('chat-form');
        const input = document.getElementById('user-input');

        function selectResearcher(rollNo, cardElem) {
            currentRollNo = rollNo;
            document.querySelectorAll('.researcher-card').forEach(c => c.classList.remove('active'));
            cardElem.classList.add('active');
        }

        function sendQuickPrompt(text) {
            input.value = text;
            form.dispatchEvent(new Event('submit'));
        }

        function testArjunRejection() {
            // Select Arjun automatically
            const arjunCard = document.querySelectorAll('.researcher-card')[1];
            selectResearcher('22IT017', arjunCard);
            sendQuickPrompt('Can I book the Scanning Electron Microscope (SEM) slot 2?');
        }

        function testRahulSuspension() {
            const rahulCard = document.querySelectorAll('.researcher-card')[3];
            selectResearcher('22ME009', rahulCard);
            sendQuickPrompt('Can I book the GPU Cluster on 2026-09-21?');
        }

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const text = input.value.trim();
            if (!text) return;

            input.value = '';

            // Append User message
            const userMsg = document.createElement('div');
            userMsg.className = 'msg msg-user';
            userMsg.innerHTML = `<div class="msg-content">${escapeHtml(text)}</div>`;
            stream.appendChild(userMsg);

            // Append Assistant loading message
            const asstMsg = document.createElement('div');
            asstMsg.className = 'msg msg-assistant';
            asstMsg.innerHTML = `<div class="msg-content"><em>Supervisor delegating to specialists and checking policies...</em></div>`;
            stream.appendChild(asstMsg);
            stream.scrollTop = stream.scrollHeight;

            try {
                const res = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ roll_no: currentRollNo, message: text })
                });
                const data = await res.json();

                let traceHtml = '';
                if (data.steps && data.steps.length > 0) {
                    traceHtml = '<div class="trace-box"><div class="trace-title">⚡ Autonomous Multi-Agent Trace</div>';
                    data.steps.forEach(s => {
                        let badgeClass = s.agent === 'inventory' ? 'agent-inv' : (s.agent === 'booking_desk' ? 'agent-desk' : 'agent-sup');
                        let replayTag = s.replayed ? ' <span class="trace-replay">REPLAYED (IDEMPOTENT)</span>' : '';
                        let stepDesc = s.tool ? `called tool <b>${s.tool}</b>` : `turn (${s.kind})`;
                        traceHtml += `<div class="trace-step"><span class="badge-agent ${badgeClass}">${s.agent}</span> <span>${stepDesc}${replayTag}</span></div>`;
                    });
                    traceHtml += '</div>';
                }

                asstMsg.querySelector('.msg-content').innerHTML = `<div>${escapeHtml(data.reply)}</div>${traceHtml}`;
            } catch (err) {
                asstMsg.querySelector('.msg-content').innerHTML = `<span style="color:var(--accent-rose)">Execution Error: ${err}</span>`;
            }
            stream.scrollTop = stream.scrollHeight;
        });

        function escapeHtml(str) {
            if (!str) return '';
            return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
        }
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
        print(f"  Campus Lab Assistant Modern Console running at: http://localhost:{PORT}")
        print(f"  Open http://localhost:{PORT} in your browser!")
        print(f"=====================================================================\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")


if __name__ == "__main__":
    main()
