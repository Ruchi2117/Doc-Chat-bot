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

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
env_path = os.getenv("DOTENV_PATH", None)
load_dotenv(dotenv_path=env_path)

# Initialize FastAPI app
app = FastAPI(
    title="RAG Chatbot API",
    root_path="/api"
)

# Configure CORS origins from environment or default to all
origins = os.getenv("CORS_ORIGINS", "*").split(",")
if origins == ["*"]:
    allow_origins = ["*"]
else:
    allow_origins = origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
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

ALLOWED_EXTENSIONS = {'.txt', '.pdf', '.md', '.doc', '.docx'}

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Handle document uploads and process them for the RAG pipeline."""
    try:
        # Check file extension
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            return JSONResponse(
                status_code=400,
                content={"error": f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"}
            )

        # Create documents directory if it doesn't exist
        documents_dir = Path("documents")
        documents_dir.mkdir(exist_ok=True)

        # Save the file
        file_path = documents_dir / file.filename
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Process the new document
        global document_processor
        if document_processor is None:
            document_processor = DocumentProcessor()
            
        # Process only the new document and update vector store
        documents = await run_in_threadpool(document_processor.process_document, file_path)
        await run_in_threadpool(document_processor.update_vectorstore, documents)

        return JSONResponse(
            content={
                "message": "File uploaded and processed successfully",
                "filename": file.filename
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
    global rag_pipeline
    try:
        from rag_pipeline import RAGPipeline
        rag_pipeline = RAGPipeline()
        logger.info("RAG pipeline initialized successfully")
    except Exception as e:
        logger.exception("Failed to initialize RAG pipeline")
        raise

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