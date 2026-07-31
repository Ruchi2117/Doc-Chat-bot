# Deployment Guide

This project should be deployed as two services:

- A static React/Vite frontend.
- A Dockerized FastAPI backend using the Render-friendly vector RAG profile.

Render's free backend has a 512 MB memory limit. The deployment profile keeps the RAG flow, but uses Chroma's ONNX MiniLM embeddings instead of loading Torch, sentence-transformers, and spaCy at runtime.

The easiest path is the included Render Blueprint in `render.yaml`.

## 1. Prepare the Repository

Commit and push the latest project changes to GitHub.

```bash
git add .
git commit -m "Prepare production deployment"
git push origin main
```

## 2. Get a Groq API Key

Create or open your Groq account, then copy an API key. Do not commit this key to GitHub.

The backend needs:

```env
GROQ_API_KEY=your_groq_api_key_here
RAG_PROFILE=render
```

## 3. Deploy Both Services on Render

1. Open the Render Dashboard.
2. Choose **New** > **Blueprint**.
3. Connect the GitHub repository.
4. Select this repo and the `main` branch.
5. Render will detect `render.yaml`.
6. When prompted for `GROQ_API_KEY`, paste your Groq API key.
7. Create the Blueprint.

The Blueprint sets `RAG_PROFILE=render` for the backend. Keep that value on the free instance.

It also sets `AUTO_PREPARE_DOCUMENTS=false`, so the production demo answers only from documents uploaded in the current browser session. That prevents bundled sample files or previous uploads from being mixed into a fresh demo.

Uploads return quickly and continue indexing in the background. On Render free, large PDFs can still take a bit to extract and embed, so keep resume-demo files small when possible.

Render should create:

- Frontend: `https://ruchi-doc-chatbot.onrender.com`
- Backend API: `https://ruchi-doc-chatbot-api.onrender.com`

If you rename either service in Render, update these values in `render.yaml` before redeploying:

- Frontend `VITE_API_URL`
- Backend `CORS_ORIGINS`

## 4. Verify the Deployment

Open:

```text
https://ruchi-doc-chatbot-api.onrender.com/health
```

Expected response:

```json
{
  "status": "ok",
  "service": "RAG Chatbot Backend",
  "rag_pipeline": "initialized"
}
```

Then open:

```text
https://ruchi-doc-chatbot.onrender.com
```

Upload a small `.txt`, `.md`, `.pdf`, or `.docx` file and ask a question about it.

## 5. Optional Vercel Frontend

You can also deploy only the frontend to Vercel and keep the backend on Render.

Vercel settings:

```text
Install Command: cd frontend && npm ci
Build Command: cd frontend && npm run build
Output Directory: frontend/dist
```

Set this Vercel environment variable:

```env
VITE_API_URL=https://ruchi-doc-chatbot-api.onrender.com
```

Then update the backend `CORS_ORIGINS` on Render to the Vercel frontend URL.

## 6. Persistence Upgrade

The free Render backend is fine for a resume demo, but its filesystem is ephemeral. For persistent uploaded documents and vectors:

1. Upgrade the backend service from Free to a paid instance type.
2. Add a persistent disk:

```yaml
disk:
  name: doc-chatbot-data
  mountPath: /app/data
  sizeGB: 1
```

3. Set these backend environment variables:

```env
DOCUMENTS_DIR=/app/data/documents
VECTORSTORE_PATH=/app/data/vectorstore
```

4. Redeploy the backend.

## 7. Full RAG Profile

The original heavier local pipeline is still available for local development or a larger paid backend.

Install the extra dependencies:

```bash
cd backend
pip install -r requirements.txt
pip install -r requirements-full.txt
```

Then set:

```env
RAG_PROFILE=full
EMBEDDING_MODEL=all-MiniLM-L6-v2
EMBEDDING_DEVICE=cpu
```

Do not use `RAG_PROFILE=full` on Render's free 512 MB instance.

## 8. Resume Link

Use the frontend URL on your resume:

```text
https://ruchi-doc-chatbot.onrender.com
```

Add the backend URL only in the GitHub README or project notes, not as the primary resume link.
