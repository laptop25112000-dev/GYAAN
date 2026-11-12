import os
import sys

# Ensure project root is always accessible in sys.path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from flask import Flask, render_template, send_from_directory
from gyaaan_core import chat_response, history_response, transcribe_response

app = Flask(
    __name__,
    template_folder=os.path.join(ROOT_DIR, "templates"),
    static_folder=os.path.join(ROOT_DIR, "static"),
    static_url_path="/static"
)


# Explicit static route to ensure Vercel always serves stylesheets and assets cleanly
@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory(os.path.join(ROOT_DIR, "static"), filename)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/history", methods=["GET", "DELETE"])
def handle_history():
    return history_response()


@app.route("/api/chat", methods=["POST"])
def api_chat():
    return chat_response()


@app.route("/api/transcribe", methods=["POST"])
def api_transcribe():
    return transcribe_response()


# Expose WSGI application object 'app' for Vercel
# Universal entrypoint (Replit, Render, Docker, Local)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"GYAAN UI ready at http://{host}:{port}")
    app.run(host=host, port=port, debug=False, use_reloader=False)
