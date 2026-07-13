"""
app.py
------
Thin web wrapper around engine.build_proposal() so this can run as a
Render.com web service and be pinged by an n8n HTTP Request node.

ENDPOINTS
    GET  /               health check (Render uses this to confirm the
                          service is alive; also handy to sanity-check
                          the URL from a browser)
    POST /generate       body = the same JSON payload engine.py expects
                          on the CLI (see engine.py docstring for schema).
                          Returns the finished PDF as a binary response,
                          plus a X-Warnings header with any validation
                          warnings (JSON-encoded string) so n8n can branch
                          on it without parsing the PDF.

RUN LOCALLY
    pip install -r requirements.txt
    python3 app.py
    # then POST data/sample_payload.json to http://localhost:8000/generate

DEPLOY
    See README.md "Deploying to Render" section.
"""

import io
import json
import os
import tempfile

from flask import Flask, request, send_file, jsonify

from engine import build_proposal

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(BASE_DIR, "template.pdf")


@app.get("/")
def health():
    return jsonify(status="ok", service="weott-proposal-engine")


@app.post("/generate")
def generate():
    payload = request.get_json(force=True, silent=True)
    if payload is None:
        return jsonify(error="Request body must be valid JSON"), 400

    # Use a temp file for the output PDF -- Render's filesystem is
    # ephemeral, which is fine here since we stream the bytes straight
    # back in the response and never need the file afterwards.
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "output.pdf")
        try:
            report = build_proposal(payload, TEMPLATE_PATH, output_path)
        except Exception as exc:
            return jsonify(error=f"Proposal generation failed: {exc}"), 500

        with open(output_path, "rb") as f:
            pdf_bytes = f.read()

    response = send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name="proposal.pdf",
    )
    # Expose the warnings/report so n8n can read them from the response
    # headers without needing a second endpoint or parsing the PDF.
    response.headers["X-Warnings"] = json.dumps(report["warnings"])
    response.headers["X-Using-Brand-Font"] = str(report["using_brand_font"])
    response.headers["X-Page-Count"] = str(report["page_count_final"])
    return response


if __name__ == "__main__":
    # Render sets $PORT; default to 8000 for local runs.
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
