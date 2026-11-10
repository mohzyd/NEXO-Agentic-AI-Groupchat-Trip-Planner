"""
chat_host.py
دردشة HTML مربوطة مع Flask + Socket.IO لتجربة الكود الخلفي.

التثبيت:
    pip install flask flask-socketio

التشغيل:
    python chat_host.py
    ثم افتح:  http://127.0.0.1:5000
"""

from datetime import datetime

from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit
from utils import Tunnel, Pipes, TunnelResponse
import atexit

CHAT_ID = None

HTML_PAGE = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>دردشة تجريبية</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: Tahoma, Arial, sans-serif; background: #f0f2f5; margin: 0;
         display: flex; justify-content: center; align-items: center; height: 100vh; }
  #chat { width: 100%; max-width: 480px; height: 90vh; background: #fff; border-radius: 12px;
          box-shadow: 0 4px 16px rgba(0,0,0,.12); display: flex; flex-direction: column; overflow: hidden; }
  #header { background: #2563eb; color: #fff; padding: 14px 16px; display: flex;
            justify-content: space-between; align-items: center; }
  #status { font-size: 12px; }
  #messages { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 8px; }
  .msg { max-width: 80%; padding: 8px 12px; border-radius: 10px; background: #e5e7eb; word-wrap: break-word; }
  .msg.me { align-self: flex-start; background: #2563eb; color: #fff; }
  .msg.server { align-self: center; background: #fef3c7; font-size: 13px; }
  .msg .meta { font-size: 11px; opacity: .7; margin-bottom: 2px; }
  #form { display: flex; gap: 8px; padding: 10px; border-top: 1px solid #e5e7eb; }
  #input { flex: 1; padding: 10px; border: 1px solid #d1d5db; border-radius: 8px; font-size: 15px; }
  button { padding: 10px 18px; border: 0; border-radius: 8px; background: #2563eb; color: #fff;
           font-size: 15px; cursor: pointer; }
</style>
</head>
<body>
<div id="chat">
  <div id="header">
    <span>دردشة تجريبية</span>
    <span id="status">غير متصل</span>
  </div>
  <div id="messages"></div>
  <div id="form">
    <input id="input" placeholder="اكتب رسالتك..." autocomplete="off">
    <button id="send">إرسال</button>
  </div>
</div>

<script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
<script>
  const username = prompt("اسمك؟") || "ضيف";
  const socket = io();
  const box = document.getElementById("messages");
  const input = document.getElementById("input");
  const status = document.getElementById("status");

  function addMessage(data, cls) {
    const div = document.createElement("div");
    div.className = "msg " + cls;
    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = data.user + " • " + data.time;
    const body = document.createElement("div");
    body.textContent = data.text;
    div.appendChild(meta);
    div.appendChild(body);
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
  }

  socket.on("connect", () => {
    status.textContent = "متصل";
    socket.emit("join", { user: username });
  });
  socket.on("disconnect", () => { status.textContent = "غير متصل"; });

  socket.on("message", (data) => {
    const cls = data.system ? "server" : (data.user === username ? "me" : "");
    addMessage(data, cls);
  });

  function send() {
    const text = input.value.trim();
    if (!text) return;
    socket.emit("message", { user: username, text: text });
    input.value = "";
    input.focus();
  }
  document.getElementById("send").onclick = send;
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") send(); });
</script>
</body>
</html>
"""


def _now():
    return datetime.now().strftime("%H:%M")


def run_chat_host(host="0.0.0.0", port=5000, debug=False, on_message=None, chat_id: str = None, to_pipe_id: str = None):
    """
    تشغيل سيرفر الدردشة.

    المعاملات:
        host: عنوان التشغيل (0.0.0.0 يسمح بالاتصال من أجهزة أخرى بنفس الشبكة).
        port: المنفذ.
        debug: وضع التطوير.
        on_message: (اختياري) دالة من كودك الخلفي تُستدعى مع كل رسالة.
            تستقبل dict فيه {"user", "text", "time"}.
            إذا رجّعت نص، يُرسل للجميع كرد من "السيرفر".
    """

    global CHAT_ID
    CHAT_ID = chat_id
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "dev-secret-key"
    socketio = SocketIO(app, cors_allowed_origins="*")

    @app.route("/")
    def index():
        return render_template_string(HTML_PAGE)

    @socketio.on("connect")
    def handle_connect():
        print(f"[+] اتصال جديد: {request.sid}")

    @socketio.on("disconnect")
    def handle_disconnect():
        print(f"[-] انقطع الاتصال: {request.sid}")

    @socketio.on("join")
    def handle_join(data):
        user = str(data.get("user", "guest"))[:30]
        emit("message", {"user": "server", "text": f"{user} joined the chat",
                         "time": _now(), "system": True}, broadcast=True)

    @socketio.on("message")
    def handle_message(data):
        payload = {
            "user": str(data.get("user", "guest"))[:30],
            "text": str(data.get("text", ""))[:1000],
            "time": _now(),
        }
        print(f"[msg] {payload['user']}: {payload['text']}")
        emit("message", payload, broadcast=True)

        # ربط كودك الخلفي هنا
        if on_message is not None:
            try:
                reply = on_message(payload)
            except Exception as exc:
                reply = f"خطأ في الكود الخلفي: {exc}"
            if reply:
                emit("message", {"user": "السيرفر", "text": str(reply),
                                 "time": _now(), "system": True}, broadcast=True)

    print(f"chat running on http://{host}:{port}")
    socketio.run(app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True)