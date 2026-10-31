---
title: NutriGo
emoji: 🥗
colorFrom: green
colorTo: green
sdk: gradio
python_version: "3.12"
app_file: start.py
pinned: false
---

# NutriGo backend

Flask API for the NutriGo Flutter app (food recognition, healthier swaps, 7-day meal plans,
accounts) and the admin dashboard at `/admin`. `start.py` clones the code from
https://github.com/KarimAshraf04/NutriGo at start-up and serves it on port 7860.

- Flutter `baseUrl`: this Space's direct URL, `https://<user>-<space>.hf.space`
- Admin dashboard: `https://<user>-<space>.hf.space/admin`

Set the Space secrets `NUTRIGO_ADMIN_PASSWORD` and `NUTRIGO_SECRET_KEY` before using it
(without the first, the dashboard password is the public default `123456789`).
After a `git push` to GitHub, restart the Space (Settings → Restart) to load the new code.
On the free tier the disk is temporary: accounts, plans, meal photos and the request log are
reset whenever the Space restarts.

(`Dockerfile` in the GitHub folder is only for a paid Docker Space; a Gradio Space ignores it.)
