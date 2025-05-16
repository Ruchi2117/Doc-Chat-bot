import os
import logging
from pathlib import Path
from typing import List, Dict
from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    UnstructuredMarkdownLoader
)
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DocumentProcessor:
    def __init__(
        self,
        data_dir: str = "documents",
        vectorstore_path: str = "vectorstore",
        embedding_model: str = "all-MiniLM-L6-v2",
        chunk_size: int = 500,
        chunk_overlap: int = 50
    ):
        self.data_dir = Path(data_dir)
        self.vectorstore_path = Path(vectorstore_path)
        
        # Create directories if they don't exist
        self.data_dir.mkdir(exist_ok=True)
        self.vectorstore_path.mkdir(exist_ok=True)
        
        # Initialize embedding function
        self.embedding_function = HuggingFaceEmbeddings(
            model_name=embedding_model,
            model_kwargs={"device": "cpu"}
        )
        
        # Initialize text splitter
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            add_start_index=True,
        )
        
        # File type to loader mapping
        self.loaders = {
            ".pdf": PyPDFLoader,
            ".txt": TextLoader,
            ".md": UnstructuredMarkdownLoader
        }
    
    def process_documents(self) -> List[Dict]:
        """Process all supported documents in the data directory."""
        documents = []
        
        # Process each file in the data directory
        for file_path in self.data_dir.glob("**/*"):
            if file_path.suffix.lower() in self.loaders:
                logger.info(f"Processing {file_path}")
                try:
                    # Load and split the document
                    loader = self.loaders[file_path.suffix.lower()](str(file_path))
                    doc = loader.load()
                    chunks = self.text_splitter.split_documents(doc)
                    documents.extend(chunks)
                    logger.info(f"Added {len(chunks)} chunks from {file_path.name}")
                except Exception as e:
                    logger.error(f"Error processing {file_path}: {str(e)}")
        
        return documents
    
    def create_vectorstore(self, documents: List[Dict]):
        """Create or update the vector store with the processed documents."""
        if not documents:
            logger.warning("No documents to process!")
            return
        
        try:
            # Create new vector store
            vectorstore = Chroma.from_documents(
                documents=documents,
                embedding=self.embedding_function,
                persist_directory=str(self.vectorstore_path)
            )
            vectorstore.persist()
            logger.info(f"Successfully created vector store at {self.vectorstore_path}")
            
            # Log some stats
            logger.info(f"Processed {len(documents)} chunks in total")
            logger.info("Vector store is ready for querying!")
            
        except Exception as e:
            logger.error(f"Error creating vector store: {str(e)}")
            raise

def main():
    # Initialize processor
    processor = DocumentProcessor()
    
    # Check if there are any documents
    if not list(processor.data_dir.glob("**/*")):
        logger.warning(f"No documents found in {processor.data_dir}. Please add some documents first!")
        logger.info("Supported formats: PDF, TXT, MD")
        return
    
    # Process documents and create vector store
    documents = processor.process_documents()
    processor.create_vectorstore(documents)

if __name__ == "__main__":
    main()
