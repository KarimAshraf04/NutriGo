"""Start NutriGo inside a free Hugging Face *Gradio* Space (Docker Spaces need a paid plan).

The Space only holds this file, README.md and requirements.txt. At start-up it clones the code from
GitHub (so the 89 MB model never goes through the Space's git), then serves on port 7860:
  /        the NutriGo Flask app (Flutter API under /api, admin dashboard under /admin)
  /space   a small Gradio page with the links (the Gradio SDK expects a Gradio app)
User accounts, plans and photos live on the Space's temporary disk and reset when it restarts.
"""
import os
import subprocess
import sys

REPO = os.environ.get("NUTRIGO_REPO", "https://github.com/KarimAshraf04/NutriGo.git")
BRANCH = os.environ.get("NUTRIGO_BRANCH", "main")
HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.join(HERE, "nutrigo_code")
PORT = int(os.environ.get("PORT", 7860))


def fetch_code():
    """Clone the repo, or update it when the Space restarts."""
    if os.path.isdir(os.path.join(CODE, ".git")):
        subprocess.run(["git", "-C", CODE, "fetch", "--depth", "1", "origin", BRANCH], check=True)
        subprocess.run(["git", "-C", CODE, "reset", "--hard", "FETCH_HEAD"], check=True)
    else:
        subprocess.run(["git", "clone", "--depth", "1", "--branch", BRANCH, REPO, CODE], check=True)


def build_app():
    from a2wsgi import WSGIMiddleware
    from fastapi import FastAPI

    sys.path.insert(0, os.path.join(CODE, "backend"))
    import app as nutrigo  # backend/app.py

    flask_app = nutrigo.create_app()
    web = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    try:
        import gradio as gr
        with gr.Blocks(title="NutriGo") as ui:
            gr.Markdown("# NutriGo backend\n"
                        "- Admin dashboard: [/admin](/admin)\n"
                        "- API status: [/api/status](/api/status)\n"
                        "- Flutter `baseUrl`: this Space's direct URL (`https://<user>-<space>.hf.space`)")
        web = gr.mount_gradio_app(web, ui, path="/space")
    except ImportError:  # running outside a Gradio Space
        pass
    web.mount("/", WSGIMiddleware(flask_app))  # last: everything else goes to Flask
    return web


if __name__ == "__main__":
    fetch_code()
    import uvicorn
    uvicorn.run(build_app(), host="0.0.0.0", port=PORT, proxy_headers=True, forwarded_allow_ips="*")
