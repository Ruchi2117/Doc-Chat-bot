import os
import logging
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
import uvicorn
from dotenv import load_dotenv
import json
import asyncio
import shutil
from pathlib import Path
from typing import List, Dict, Optional
from prepare_data import DocumentProcessor
from settings import csv_env, env_bool, resolve_path

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
env_path = os.getenv("DOTENV_PATH", None)
load_dotenv(dotenv_path=env_path)

# Initialize FastAPI app
app = FastAPI(
    title="RAG Chatbot API",
    root_path=os.getenv("ROOT_PATH", "")
)

# Configure CORS origins from environment or default to all.
allow_origins = csv_env("CORS_ORIGINS", "*")
allow_credentials = env_bool("CORS_ALLOW_CREDENTIALS", False) and allow_origins != ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define request model
class AskRequest(BaseModel):
    question: str
    use_cache: bool = True
    history: Optional[List[Dict[str, str]]] = None

# Initialize RAG pipeline placeholder
rag_pipeline = None
document_processor = None

ALLOWED_EXTENSIONS = {'.txt', '.pdf', '.md', '.docx'}


@app.get("/")
async def root():
    """Small root endpoint for platform smoke checks and browser visits."""
    return {
        "service": "RAG Chatbot Backend",
        "status": "ok",
        "docs": "/docs",
        "health": "/health",
    }


def vectorstore_has_data(vectorstore_path: Path) -> bool:
    return vectorstore_path.exists() and any(vectorstore_path.iterdir())


async def prepare_default_documents_if_needed(documents_dir: Path, vectorstore_path: Path):
    if not env_bool("AUTO_PREPARE_DOCUMENTS", True):
        logger.info("AUTO_PREPARE_DOCUMENTS is disabled")
        return

    if vectorstore_has_data(vectorstore_path):
        logger.info("Vector store already exists at %s", vectorstore_path)
        return

    if not documents_dir.exists() or not any(documents_dir.glob("**/*")):
        logger.warning("No bundled documents found in %s", documents_dir)
        return

    logger.info("Preparing bundled documents from %s", documents_dir)
    processor = DocumentProcessor(
        data_dir=documents_dir,
        vectorstore_path=vectorstore_path,
    )
    documents = await run_in_threadpool(processor.process_documents)
    if documents:
        await run_in_threadpool(processor.create_vectorstore_from_documents, documents)
    else:
        logger.warning("Bundled documents did not produce any chunks")

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Handle document uploads and process them for the RAG pipeline."""
    try:
        filename = Path(file.filename or "").name
        if not filename:
            return JSONResponse(
                status_code=400,
                content={"error": "Uploaded file must have a filename"}
            )

        # Check file extension
        file_ext = Path(filename).suffix.lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            return JSONResponse(
                status_code=400,
                content={"error": f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"}
            )

        global document_processor, rag_pipeline
        if document_processor is None:
            document_processor = DocumentProcessor()

        # Save the file
        document_processor.data_dir.mkdir(parents=True, exist_ok=True)
        file_path = document_processor.data_dir / filename
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Process the new document
        documents = await run_in_threadpool(document_processor.process_document, file_path)
        if not documents:
            return JSONResponse(
                status_code=400,
                content={"error": "No readable text could be extracted from this file"}
            )

        await run_in_threadpool(document_processor.update_vectorstore, documents)
        if rag_pipeline is not None:
            await run_in_threadpool(rag_pipeline.reload_vectorstore)

        return JSONResponse(
            content={
                "message": "File uploaded and processed successfully",
                "filename": filename
            }
        )
    except Exception as e:
        logger.exception("Error processing uploaded file")
        return JSONResponse(
            status_code=500,
            content={"error": f"Error processing file: {str(e)}"}
        )

@app.get("/health")
async def health_check():
    """Health check endpoint to verify the backend is running."""
    return {
        "status": "ok",
        "service": "RAG Chatbot Backend",
        "rag_pipeline": "initialized" if rag_pipeline else "not initialized"
    }

@app.on_event("startup")
async def startup_event():
    global rag_pipeline, document_processor
    try:
        from rag_pipeline import RAGPipeline
        documents_dir = resolve_path("DOCUMENTS_DIR", "documents")
        vectorstore_path = resolve_path("VECTORSTORE_PATH", "vectorstore")
        documents_dir.mkdir(parents=True, exist_ok=True)
        vectorstore_path.mkdir(parents=True, exist_ok=True)

        await prepare_default_documents_if_needed(documents_dir, vectorstore_path)

        document_processor = DocumentProcessor(
            data_dir=documents_dir,
            vectorstore_path=vectorstore_path,
        )
        rag_pipeline = RAGPipeline(chroma_path=str(vectorstore_path))
        logger.info("RAG pipeline initialized successfully")
    except Exception as e:
        logger.exception("Failed to initialize RAG pipeline")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    if rag_pipeline and getattr(rag_pipeline, "llama_helper", None):
        await rag_pipeline.llama_helper.aclose()

async def stream_response(question: str, use_cache: bool = True, history: Optional[List[Dict[str, str]]] = None):
    """Stream response chunks as Server-Sent Events."""
    try:
        async for chunk, metadata, scores in rag_pipeline.answer_question_stream(question, use_cache=use_cache, history=history):
            # Prepare SSE message
            data = {
                "chunk": chunk,
                "metadata": metadata,
                "scores": scores
            }
            yield f"data: {json.dumps(data)}\n\n"
        
        # Send end marker
        yield "data: [DONE]\n\n"
    except Exception as e:
        logger.exception("Error in stream_response")
        error_data = {"error": str(e)}
        yield f"data: {json.dumps(error_data)}\n\n"
        yield "data: [DONE]\n\n"

@app.get("/ask")
async def ask_question_get(question: str, use_cache: bool = True):
    """GET endpoint for SSE streaming."""
    if not question.strip():
        raise HTTPException(status_code=400, detail="`question` field is required")

    return StreamingResponse(
        stream_response(question.strip(), use_cache=use_cache, history=None),
        media_type="text/event-stream"
    )

@app.post("/ask")
async def ask_question_post(payload: AskRequest):
    """POST endpoint for regular requests."""
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="`question` field is required")

    return StreamingResponse(
        stream_response(question, use_cache=payload.use_cache, history=payload.history),
        media_type="text/event-stream"
    )

if __name__ == "__main__":
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        log_level="info",
        reload=bool(os.getenv("DEV_MODE", False)),
    )
