---
title: NutriGo
emoji: 🥗
colorFrom: green
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# NutriGo backend

Flask API for the NutriGo Flutter app (food recognition, healthier swaps, 7-day meal plans,
accounts) and the admin dashboard at `/admin`. The code is built from
https://github.com/KarimAshraf04/NutriGo (see `deploy/huggingface/` there).

- Flutter `baseUrl`: this Space's direct URL, `https://<user>-<space>.hf.space`
- Admin dashboard: `https://<user>-<space>.hf.space/admin`

Set the Space secrets `NUTRIGO_ADMIN_PASSWORD` and `NUTRIGO_SECRET_KEY` before using it.
On the free tier the disk is temporary: accounts, plans, meal photos and the request log are
reset whenever the Space restarts or is rebuilt.
