from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from llama_helper import LlamaHelper
from typing import List, Dict, Tuple, AsyncGenerator, Optional
import spacy
import logging
import os
from dataclasses import dataclass
from heapq import nlargest
from pathlib import Path
from functools import lru_cache
import asyncio
import time
from collections import OrderedDict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class SearchResult:
    content: str
    metadata: Dict
    vector_score: float
    hybrid_score: float

class ResponseCache:
    """LRU cache for storing question-response pairs with TTL."""
    def __init__(self, capacity: int = 1000, ttl: int = 3600):
        self.capacity = capacity
        self.ttl = ttl  # Time-to-live in seconds
        self.cache = OrderedDict()

    async def get(self, question: str) -> Optional[Tuple[str, List[Dict], List[float]]]:
        if question not in self.cache:
            return None
        
        timestamp, response = self.cache[question]
        if time.time() - timestamp > self.ttl:
            del self.cache[question]
            return None
            
        self.cache.move_to_end(question)
        return response

    async def put(self, question: str, response: Tuple[str, List[Dict], List[float]]):
        self.cache[question] = (time.time(), response)
        self.cache.move_to_end(question)
        
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)

class RAGPipeline:
    """
    Retrieval-Augmented Generation pipeline combining semantic search with keyword relevance.
    """
    def __init__(
        self,
        chroma_path: str = None,
        embedding_model: str = None,
        device: str = None,
        cache_capacity: int = 1000,
        cache_ttl: int = 3600
    ):
        # Initialize response cache
        self.response_cache = ResponseCache(capacity=cache_capacity, ttl=cache_ttl)
        
        # Load environment settings
        if chroma_path is None:
            # Get the directory where this file is located
            current_dir = Path(__file__).resolve().parent
            chroma_path = str(current_dir / "vectorstore")
        
        embedding_model = embedding_model or os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        device = device or os.getenv("EMBEDDING_DEVICE", "cpu")

        logger.info(f"Using vector store at: {chroma_path}")

        # Initialize embedding function with caching
        self.embedding_function = CachedEmbeddings(
            HuggingFaceEmbeddings(
                model_name=embedding_model,
                model_kwargs={"device": device}
            )
        )

        # Load or create vector store
        try:
            self.db = Chroma(
                persist_directory=chroma_path,
                embedding_function=self.embedding_function
            )
            logger.info(f"Loaded Chroma vectorstore from '{chroma_path}'")
        except Exception as e:
            logger.exception("Failed to initialize Chroma vectorstore")
            raise

        # Initialize LLaMA helper
        self.llama_helper = LlamaHelper()

        # Load spaCy pipeline with caching
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except OSError:
            logger.info("Downloading spaCy 'en_core_web_sm' model...")
            spacy.cli.download("en_core_web_sm")
            self.nlp = spacy.load("en_core_web_sm")

    @lru_cache(maxsize=1000)
    def preprocess_query(self, query: str) -> Tuple[str, str]:
        """
        Preprocess the query with spaCy, with caching.
        Returns tuple of (enhanced query, serialized doc).
        """
        doc = self.nlp(query)
        important = [tok.text for tok in doc
                     if tok.ent_type_ or tok.pos_ in {"NOUN", "VERB", "PROPN"}
                     or not (tok.is_stop or tok.is_punct)]
        enhanced = " ".join(important) if important else query.strip()
        return enhanced, doc.to_bytes().hex()

    @lru_cache(maxsize=1000)
    def calculate_keyword_score(self, text: str, doc_hex: str) -> float:
        """
        Compute keyword overlap score with caching.
        """
        doc = spacy.tokens.Doc(self.nlp.vocab).from_bytes(bytes.fromhex(doc_hex))
        doc_text = self.nlp(text.lower())
        query_tokens = {tok.text.lower() for tok in doc
                        if tok.ent_type_ or tok.pos_ in {"NOUN", "VERB", "PROPN"}}
        if not query_tokens:
            return 0.0
        matches = sum(1 for tok in doc_text if tok.text in query_tokens)
        return matches / len(query_tokens)

    async def hybrid_search(self, query: str, k: int = 3) -> List[SearchResult]:
        """
        Asynchronous hybrid search combining vector similarity with keyword relevance.
        """
        processed, doc_hex = self.preprocess_query(query)
        
        # Fetch results asynchronously
        raw_results = await asyncio.to_thread(
            self.db.similarity_search_with_score,
            processed,
            k=k * 3
        )
        
        candidates: List[SearchResult] = []
        for doc_obj, dist in raw_results:
            # Calculate scores asynchronously
            keyword_score = await asyncio.to_thread(
                self.calculate_keyword_score,
                doc_obj.page_content,
                doc_hex
            )
            similarity = 1 - dist
            hybrid = 0.7 * similarity + 0.3 * keyword_score
            candidates.append(
                SearchResult(
                    content=doc_obj.page_content,
                    metadata=doc_obj.metadata,
                    vector_score=similarity,
                    hybrid_score=hybrid
                )
            )

        top = nlargest(k, candidates, key=lambda x: x.hybrid_score)
        logger.info(f"Selected top {len(top)} docs for query '{query}'")
        return top

    async def answer_question_stream(
        self,
        query: str,
        k: int = 3,
        use_cache: bool = True
    ) -> AsyncGenerator[Tuple[str, List[Dict], List[float]], None]:
        """
        Stream responses from the RAG pipeline with caching support.
        """
        # Check cache first if enabled
        if use_cache:
            cached_response = await self.response_cache.get(query)
            if cached_response is not None:
                logger.info("Cache hit for query: %s", query)
                yield cached_response
                return

        results = await self.hybrid_search(query, k)
        if not results:
            response = ("No relevant information found.", [], [])
            if use_cache:
                await self.response_cache.put(query, response)
            yield response
            return

        # Assemble context
        context = "\n\n".join(r.content for r in results)
        
        # Collect full response for caching
        full_response = []
        metadata = [r.metadata for r in results]
        scores = [r.hybrid_score for r in results]
        
        # Stream the response
        async for chunk in self.llama_helper.generate_response(context, query):
            full_response.append(chunk)
            yield (chunk, metadata, scores)
        
        # Cache the complete response if enabled
        if use_cache:
            complete_response = ("".join(full_response), metadata, scores)
            await self.response_cache.put(query, complete_response)

class CachedEmbeddings:
    """Wrapper for embedding function with caching and batch processing."""
    def __init__(self, embeddings, cache_size=1000, batch_size=32):
        self.embeddings = embeddings
        self.cache = lru_cache(maxsize=cache_size)(self._embed_documents)
        self.cache_query = lru_cache(maxsize=cache_size)(self._embed_query)
        self.batch_size = batch_size

    def _embed_documents(self, text: str) -> List[float]:
        return self.embeddings.embed_documents([text])[0]

    def _embed_query(self, text: str) -> List[float]:
        return self.embeddings.embed_query(text)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed documents with batching and caching support."""
        results = []
        # Process in batches
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            # Check cache for each text in batch
            batch_results = []
            uncached_texts = []
            uncached_indices = []
            
            for j, text in enumerate(batch):
                try:
                    # Try to get from cache
                    embedding = self.cache(text)
                    batch_results.append((j, embedding))
                except KeyError:
                    uncached_texts.append(text)
                    uncached_indices.append(j)
            
            # Process uncached texts in one batch if any
            if uncached_texts:
                embeddings = self.embeddings.embed_documents(uncached_texts)
                for idx, embedding in zip(uncached_indices, embeddings):
                    batch_results.append((idx, embedding))
            
            # Sort results by original index and append
            batch_results.sort(key=lambda x: x[0])
            results.extend(embedding for _, embedding in batch_results)
        
        return results

    def embed_query(self, text: str) -> List[float]:
        return self.cache_query(text)