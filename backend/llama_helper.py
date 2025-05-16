import os
import logging
from typing import Optional, AsyncGenerator
import httpx
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LlamaHelper:
    """
    Helper class for text generation using Groq API.
    """
    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError(
                "GROQ_API_KEY environment variable is required. "
                "Please create a .env file in the backend directory with your Groq API key:\n"
                "GROQ_API_KEY=your_api_key_here"
            )
        
        logger.info("Groq API key configured")
        
        self.api_base = "https://api.groq.com/openai/v1"
        self.model = "llama-3.3-70b-versatile"
        self.client = httpx.AsyncClient(
            base_url=self.api_base,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            timeout=30.0
        )

    async def generate_response(self, context: str, question: str) -> AsyncGenerator[str, None]:
        """
        Generate a response using Groq's API (non-streaming).
        """
        prompt = self._create_prompt(context, question)
        
        try:
            response = await self.client.post(
                "/chat/completions",
                json={
                    "messages": [
                        {"role": "system", "content": "You are a helpful AI assistant that answers questions based on the provided context. Keep your answers concise and relevant."},
                        {"role": "user", "content": prompt}
                    ],
                    "model": self.model,
                    "temperature": 0.7,
                    "max_tokens": 1024,
                    "stream": False  # Disable streaming for more reliable responses
                }
            )
            response.raise_for_status()
            data = response.json()
            
            # Get the complete response
            full_response = data["choices"][0]["message"]["content"]
            
            # Yield the response in one go
            yield full_response
            
        except Exception as e:
            logger.exception("Error generating response")
            raise RuntimeError(f"Failed to generate response: {str(e)}")

    def _create_prompt(self, context: str, question: str) -> str:
        """Create a prompt for the model."""
        return f"""Use the following context to answer the question. If you cannot find the answer in the context, say "I cannot find information about that in the provided context."

Context:
{context}

Question:
{question}

Answer:"""

    async def aclose(self):
        """Close the async client."""
        await self.client.aclose()
