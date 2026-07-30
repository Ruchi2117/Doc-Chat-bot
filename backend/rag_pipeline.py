import asyncio
import logging
import os
import re
import time
from collections import OrderedDict
from dataclasses import dataclass
from heapq import nlargest
from typing import AsyncGenerator, Dict, List, Optional, Tuple

import chromadb
from llama_helper import LlamaHelper
from settings import resolve_path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "he", "in", "is", "it", "its", "of", "on", "or", "that", "the", "to",
    "was", "were", "what", "when", "where", "which", "who", "why", "with",
}


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
        self.ttl = ttl
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
    Render-friendly RAG pipeline.

    It keeps the core architecture: Chroma vector retrieval, source metadata,
    context assembly, and Groq answer generation. It avoids Torch/spaCy so the
    free Render instance can stay under 512 MB.
    """

    def __init__(
        self,
        chroma_path: str = None,
        embedding_model: str = None,
        device: str = None,
        cache_capacity: int = 1000,
        cache_ttl: int = 3600,
    ):
        self.response_cache = ResponseCache(capacity=cache_capacity, ttl=cache_ttl)
        self.chroma_path = chroma_path or str(resolve_path("VECTORSTORE_PATH", "vectorstore"))
        self.collection_name = os.getenv("CHROMA_COLLECTION", "doc_chatbot")
        self.client = None
        self.collection = None

        logger.info("Using Chroma vector store at: %s", self.chroma_path)
        self.reload_vectorstore()
        self.llama_helper = LlamaHelper()

    def reload_vectorstore(self):
        """Reconnect to Chroma after newly uploaded documents are persisted."""
        self.client = chromadb.PersistentClient(path=self.chroma_path)
        self.collection = self.client.get_or_create_collection(name=self.collection_name)
        self.response_cache.cache.clear()
        logger.info("Loaded Chroma collection '%s'", self.collection_name)

    async def hybrid_search(self, query: str, k: int = 3) -> List[SearchResult]:
        """Semantic vector search with a light keyword relevance boost."""
        count = await asyncio.to_thread(self.collection.count)
        if count == 0:
            return []

        n_results = min(k * 3, count)
        raw_results = await asyncio.to_thread(
            self.collection.query,
            query_texts=[query],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )

        documents = raw_results.get("documents", [[]])[0]
        metadatas = raw_results.get("metadatas", [[]])[0]
        distances = raw_results.get("distances", [[]])[0]
        query_tokens = self._important_tokens(query)

        source_groups: dict[str, list[SearchResult]] = {}
        for content, metadata, distance in zip(documents, metadatas, distances):
            metadata = metadata or {}
            vector_score = 1 / (1 + float(distance))
            keyword_score = self._keyword_score(content, query_tokens)
            hybrid_score = 0.75 * vector_score + 0.25 * keyword_score
            result = SearchResult(
                content=content,
                metadata=metadata,
                vector_score=vector_score,
                hybrid_score=hybrid_score,
            )
            source = metadata.get("source", "unknown")
            source_groups.setdefault(source, []).append(result)

        candidates = [max(items, key=lambda item: item.hybrid_score) for items in source_groups.values()]
        top = nlargest(k, candidates, key=lambda item: item.hybrid_score)
        logger.info("Selected top %s docs for query '%s'", len(top), query)
        return top

    async def answer_question_stream(
        self,
        query: str,
        k: int = 3,
        use_cache: bool = True,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncGenerator[Tuple[str, List[Dict], List[float]], None]:
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

        context = "\n\n".join(result.content for result in results)
        full_query = query
        if history:
            formatted_history = "\n".join(
                f"{message['role']}: {message['content']}" for message in history
            )
            full_query = f"{formatted_history}\nuser: {query}"

        source_to_metadata = {}
        for result in results:
            source = result.metadata.get("source", "unknown")
            source_to_metadata.setdefault(source, result.metadata)

        metadata = list(source_to_metadata.values())
        scores = [result.hybrid_score for result in results]
        full_response = []

        async for chunk in self.llama_helper.generate_response(context, full_query):
            full_response.append(chunk)
            yield (chunk, metadata, scores)

        if use_cache:
            complete_response = ("".join(full_response), metadata, scores)
            await self.response_cache.put(query, complete_response)

    def _important_tokens(self, text: str) -> set[str]:
        tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
        return {token for token in tokens if len(token) > 2 and token not in STOPWORDS}

    def _keyword_score(self, text: str, query_tokens: set[str]) -> float:
        if not query_tokens:
            return 0.0

        text_tokens = set(re.findall(r"[a-zA-Z0-9]+", text.lower()))
        matches = len(query_tokens & text_tokens)
        return matches / len(query_tokens)
