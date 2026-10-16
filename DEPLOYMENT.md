# WILD-ID Nexus (Pugmark) — Running & Deployment Guide

## 1. Project Overview

**WILD-ID Nexus** (codebase: `pugmark`) is a computer vision web platform for re-identifying individual wild animals (tigers, leopards, zebras, giraffes, etc.) across sightings from photos and video clips.
- **Backend**: Python 3.12, Django 5.1
- **Computer Vision Engine**: OpenCV (`opencv-contrib-python-headless`), NumPy, SIFT keypoint descriptor matching, RANSAC affine geometric verification (HotSpotter mark-recapture method)
- **Database**: SQLite (built-in, or PostgreSQL for large-scale production)
- **Static Assets**: Handled by WhiteNoise for production efficiency

---

## 2. Running Locally

### Option A: Windows (One-Click)
Simply double-click `run.bat` in the project root (or run it from Command Prompt / PowerShell):
```cmd
.\run.bat
```
*(Or in PowerShell: `.\run.ps1`)*

This script automatically:
1. Detects or sets up the Python virtual environment (`.venv`)
2. Installs required dependencies (`requirements.txt`)
3. Runs database migrations
4. Opens your browser to **http://127.0.0.1:8000/**
5. Starts the development server

### Option B: Using npm
If you prefer npm:
```bash
npm start
```

### Option C: Manual Python Execution
```bash
cd pugmark
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On macOS / Linux:
# source .venv/bin/activate

pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```
Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

---

## 3. Deployment Options

Because WILD-ID Nexus performs computer vision matching (OpenCV, SIFT feature extraction, video frame sampling) and manages uploaded photo/video assets and match reports, it requires a continuous runtime environment rather than a stateless serverless function (such as Vercel).

Here are the 3 easiest ways to deploy:

### Option 1: Render.com (Recommended — Fast & Free/Low Cost)

1. Push this project to your GitHub repository.
2. Sign in to [Render.com](https://render.com).
3. Click **New +** -> **Blueprint**.
4. Connect your GitHub repository. Render will automatically detect `render.yaml` in the repository and set up:
   - Build Command: `pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate`
   - Start Command: `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120`
5. Click **Apply**. In 2-3 minutes, your live web URL (e.g. `https://wildid-nexus.onrender.com`) will be active.

*(Alternatively, create a **Web Service** on Render, set **Root Directory** to `pugmark`, and choose Python 3).*

---

### Option 2: Railway.app (One-Click Git Deploy)

1. Push this project to GitHub.
2. Sign in to [Railway.app](https://railway.app).
3. Click **New Project** -> **Deploy from GitHub repo**.
4. Select your repository. Railway automatically detects the `Dockerfile` (or `Procfile`) and begins deployment.
5. Under service **Settings**:
   - Add environment variables if desired (e.g. `DJANGO_DEBUG=0`, `DJANGO_SECRET_KEY=your-secret-key`).
   - Click **Generate Domain** to get a public URL (`https://your-app.up.railway.app`).

---

### Option 3: Docker (Any VPS, AWS, GCP, or DigitalOcean)

The project includes a production-ready `Dockerfile` with OpenCV and FFmpeg system dependencies pre-configured.

1. **Build the image**:
   ```bash
   docker build -t wildid-nexus .
   ```
2. **Run the container**:
   ```bash
   docker run -d -p 8000:8000 -v wildid_media:/app/media --name wildid wildid-nexus
   ```
3. Open `http://<your-server-ip>:8000/`.

---

## 4. Key Environment Variables for Production

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `DJANGO_DEBUG` | `0` (in Docker) / `1` (local) | Set to `0` in production for security. |
| `DJANGO_SECRET_KEY` | auto-generated | Set to a random secret string in production. |
| `CSRF_TRUSTED_ORIGINS` | `http://127.0.0.1:8000` + cloud defaults | Comma-separated list of public origins, e.g. `https://wildid.example.com`. |
