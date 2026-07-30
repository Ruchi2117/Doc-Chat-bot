# Doc Chatbot

Doc Chatbot is a full-stack Retrieval-Augmented Generation (RAG) app for chatting with uploaded documents. The frontend is built with React and Vite, and the backend is a FastAPI service that indexes documents with Chroma, sentence-transformer embeddings, and Groq-hosted LLM responses.

## Features

- Upload and index `.txt`, `.md`, `.pdf`, and `.docx` files.
- Ask natural-language questions over the indexed document set.
- Stream answers back to the chat UI with source metadata.
- Uses bundled sample documents so a fresh deployment works immediately after startup.
- Docker-ready backend and static frontend deployment config.

## Tech Stack

- Frontend: React, Vite, Material UI, Axios
- Backend: FastAPI, LangChain, ChromaDB, Sentence Transformers, spaCy
- LLM provider: Groq API
- Deployment: Render Blueprint for frontend + backend, with optional Vercel frontend config

## Local Setup

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Set `GROQ_API_KEY` in `backend/.env`, then run:

```bash
uvicorn main:app --reload
```

Backend URL: `http://localhost:8000`

### Frontend

```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

Frontend URL: `http://localhost:5173`

## Environment Variables

Backend:

```env
GROQ_API_KEY=your_groq_api_key_here
CORS_ORIGINS=http://localhost:5173
DOCUMENTS_DIR=documents
VECTORSTORE_PATH=vectorstore
AUTO_PREPARE_DOCUMENTS=true
EMBEDDING_MODEL=all-MiniLM-L6-v2
EMBEDDING_DEVICE=cpu
GROQ_MODEL=llama-3.3-70b-versatile
```

Frontend:

```env
VITE_API_URL=http://localhost:8000
```

## Deployment

The recommended deployment is Render for both services:

- Static frontend: `ruchi-doc-chatbot`
- Docker backend API: `ruchi-doc-chatbot-api`

The repo includes `render.yaml`, so Render can create both services from one Blueprint. During Blueprint setup, provide `GROQ_API_KEY` when Render asks for the secret.

See [DEPLOYMENT.md](DEPLOYMENT.md) for the exact steps and production notes.

## Important Production Notes

- Render's free web service can spin down after inactivity, so the first request may be slow.
- Free Render web services have an ephemeral filesystem. Uploaded documents and generated vectors can reset after restart or redeploy.
- For a stronger long-term deployment, upgrade the backend service and attach a persistent disk mounted at `/app/data`, then set:

```env
DOCUMENTS_DIR=/app/data/documents
VECTORSTORE_PATH=/app/data/vectorstore
```

## License

This project is licensed under the MIT License.
