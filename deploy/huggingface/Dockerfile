# NutriGo backend on Hugging Face Spaces (Docker SDK).
# Upload this file and README.md (same folder) to a Docker Space. The image clones the code from
# GitHub, so the 89 MB model never has to go through the Space's git (which needs LFS above 10 MB).
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Spaces run the container as uid 1000; give that user the app folder so the request log,
# accounts, plans and uploaded photos can be written (they are lost when the Space restarts).
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /home/user/app

ARG NUTRIGO_REPO=https://github.com/KarimAshraf04/NutriGo.git
ARG NUTRIGO_BRANCH=main
# changes whenever the branch gets a new commit, so a rebuild never reuses an old clone
ADD https://api.github.com/repos/KarimAshraf04/NutriGo/git/refs/heads/${NUTRIGO_BRANCH} /tmp/nutrigo-ref.json
RUN git clone --depth 1 --branch ${NUTRIGO_BRANCH} ${NUTRIGO_REPO} .

RUN pip install --no-cache-dir --user -r backend/requirements.txt gunicorn

WORKDIR /home/user/app/backend
EXPOSE 7860
# one worker = the model is loaded once (~0.5 GB); threads serve requests in parallel
CMD ["gunicorn", "--workers", "1", "--threads", "8", "--timeout", "120", "--bind", "0.0.0.0:7860", "app:create_app()"]
