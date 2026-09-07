# Deploy the UI on Vercel

This product is a **React SPA + a Java/FastAPI API**. Vercel can host the UI. It cannot run the API: MPP parsing needs Java 17, JPype, and uploads up to 50 MB, which Vercel serverless/proxy limits do not support.

Local Docker Compose is unchanged. Empty `VITE_API_BASE` keeps same-origin `/api` calls for Vite and nginx.

## 1. Host the API first

Build and run `backend/Dockerfile` on a host that allows large uploads and a long-running process (Railway, Render, Fly.io, Azure Container Apps, or a VM).

Required environment:

```
AUTH_MODE=disabled
AI_STUB=true
DATA_DIR=/data
CORS_ORIGINS=https://YOUR-PROJECT.vercel.app
```

For live SOW/WSR analysis, set `AI_STUB=false` and `OPENAI_API_KEY`. If you later turn on `AUTH_MODE=required`, also set:

```
COOKIE_SAMESITE=none
COOKIE_SECURE=true
AUTH_BOOTSTRAP_PASSWORD=<secret>
```

Publish HTTPS on port 8000 (or whatever the host maps to). Confirm `GET https://YOUR-API/health` returns 200.

## 2. Connect the GitHub repo to Vercel

1. [vercel.com/new](https://vercel.com/new) → import `Vicky6790/Projectautomation`.
2. Leave Root Directory empty (repo-root `vercel.json` builds `frontend/`).
3. Framework: Other. Build/output are already in `vercel.json`.
4. Environment variable (Production **and** Preview), set **before** the first production build:

   | Name | Value |
   | --- | --- |
   | `VITE_API_BASE` | `https://YOUR-API` with **no trailing slash** |

5. Deploy. After the first Vercel URL is known, add it to the API `CORS_ORIGINS` (comma-separated if you also use a custom domain or preview URLs).
6. Redeploy the API if you changed CORS, then hard-refresh the Vercel site.

## 3. Custom domain (optional)

Add the domain in Vercel, then append `https://your-domain` to `CORS_ORIGINS` and restart the API.

## What not to do

- Do not proxy `/api` through Vercel rewrites. Uploads will fail the platform body-size limit.
- Do not point `VITE_API_BASE` at `http://localhost`. The browser of whoever opens the Vercel site would try *their* machine.
- Do not expect GitHub `develop` to update localhost. Local Compose still builds from your working tree.
