"""
SEO Analyzer — Local dev static file server.

All analysis logic has been migrated to mw-backend (server.py),
accessible at http://localhost:5050/seo/* when running locally.

This server simply serves the static frontend on port 5015 so it can
be loaded in an iframe from http://localhost:5173 (michaelwegter.com dev).

Run:
  python server.py
  # or via start.sh
"""

import os
from pathlib import Path
from flask import Flask, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder="static")
CORS(app)

PORT = int(os.environ.get("PORT", 5015))
STATIC_DIR = Path(__file__).parent / "static"


@app.route("/")
@app.route("/\<path:filename\>")
def serve_static(filename="index.html"):
    safe = filename if (STATIC_DIR / filename).exists() else "index.html"
    return send_from_directory(str(STATIC_DIR), safe)


if __name__ == "__main__":
    print(f"  SEO Analyzer (static dev server) running at http://localhost:{PORT}")
    print(f\    print(f	o mw-backend at http://localhost:5050/seo/*")
    app.run(host="0.0.0.0", port=PORT, debug=False)
