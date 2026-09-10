# Deploy the UI from the `vercel` branch

Vercel hosts the **React SPA only**. It cannot run this API: MPP parsing needs Java 17, JPype, a long-lived process, and uploads up to 50 MB. Vercel does not run Docker images.

Architecture:

| Piece | Where it runs |
| --- | --- |
| UI (`frontend/`) | Vercel, Git branch **`vercel`** |
| API (`backend/Dockerfile`) | Railway, Render, Fly.io, Azure Container Apps, or a VM |
| Local Docker Compose | Unchanged on your machine (`develop` / `master`) |

Empty `VITE_API_BASE` keeps same-origin `/api` for Vite and nginx. The Vercel build **must** set `VITE_API_BASE` to the hosted API, or the browser will call `/api` on `*.vercel.app` and fail.

Do **not** proxy `/api` through Vercel rewrites. Uploads will hit the platform body-size limit.

## 1. Host the API first

Build and run `backend/Dockerfile` on a host that allows large uploads.

Required environment:

```
AUTH_MODE=disabled
AI_STUB=true
DATA_DIR=/data
CORS_ORIGINS=https://YOUR-PROJECT.vercel.app
CORS_ORIGIN_REGEX=https://.*\.vercel\.app
```

For live SOW/WSR analysis, set `AI_STUB=false` and `OPENAI_API_KEY`. If you later turn on `AUTH_MODE=required`, also set:

```
COOKIE_SAMESITE=none
COOKIE_SECURE=true
AUTH_BOOTSTRAP_PASSWORD=<secret>
```

`CORS_ORIGIN_REGEX` lets Vercel preview URLs call the API without listing each one. Confirm `GET https://YOUR-API/health` returns 200.

## 2. Connect GitHub to Vercel

1. [vercel.com/new](https://vercel.com/new) → import `Vicky6790/Projectautomation`.
2. **Production Branch:** `vercel` (not `master` or `develop`).
3. Leave Root Directory empty. Repo-root `vercel.json` builds `frontend/` with Node 22.
4. Framework: Other. Build/output are already in `vercel.json`.
5. Environment variable (Production **and** Preview), set **before** the first production build:

   | Name | Value |
   | --- | --- |
   | `VITE_API_BASE` | `https://YOUR-API` with **no trailing slash** |

6. Deploy. After the first Vercel URL is known, add it to the API `CORS_ORIGINS` if you are not using `CORS_ORIGIN_REGEX`.
7. Redeploy the API if you changed CORS, then hard-refresh the Vercel site.

## 3. Custom domain (optional)

Add the domain in Vercel, then append `https://your-domain` to `CORS_ORIGINS` and restart the API.

## What not to do

- Do not point `VITE_API_BASE` at `http://localhost`. The browser of whoever opens the Vercel site would try *their* machine.
- Do not expect GitHub `develop` to update localhost. Local Compose still builds from your working tree.
- Do not set Vercel Root Directory to `backend` or enable Docker on Vercel.
