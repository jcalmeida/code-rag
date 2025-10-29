"""LLM integration for conversational code assistance."""
import logging
from typing import List, Optional
from openai import OpenAI
from pydantic import BaseModel

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

from src.config import settings
from src.vector_store import VectorStore
from src.models import SearchResult

logger = logging.getLogger(__name__)


class ChatMessage(BaseModel):
    """Chat message model."""
    role: str  # "user", "assistant", "system"
    content: str


class ChatRequest(BaseModel):
    """Chat request with RAG context."""
    message: str
    repo_names: Optional[List[str]] = None
    languages: Optional[List[str]] = None
    max_context_chunks: int = 5
    model: str = "claude-3-5-sonnet-latest"  # Default to Claude, fallback to GPT


class ChatResponse(BaseModel):
    """Chat response with sources."""
    response: str
    sources: List[SearchResult]
    model_used: str


class LLMChatService:
    """Service for LLM-powered chat with RAG context."""
    
    def __init__(self):
        self.openai_client = OpenAI(api_key=settings.openai_api_key)
        self.anthropic_client = None
        if ANTHROPIC_AVAILABLE and settings.anthropic_api_key:
            self.anthropic_client = Anthropic(api_key=settings.anthropic_api_key)
        self.vector_store = VectorStore()
    
    def chat(self, request: ChatRequest) -> ChatResponse:
        """Process chat request with RAG context."""
        # 1. Search for relevant code chunks
        search_results = self.vector_store.search(
            query=request.message,
            top_k=request.max_context_chunks,
            repo_names=request.repo_names,
            languages=request.languages
        )
        
        # 2. Build context from search results
        context_parts = []
        for i, result in enumerate(search_results, 1):
            chunk = result.chunk
            context_parts.append(
                f"## Code Context {i} (Score: {result.score:.3f})\n"
                f"**File**: {chunk.file_path} (lines {chunk.start_line}-{chunk.end_line})\n"
                f"**Type**: {chunk.chunk_type}\n"
                f"**Name**: {chunk.metadata.get('name', 'N/A')}\n"
                f"```{chunk.language.value}\n{chunk.content}\n```\n"
            )
        
        context = "\n".join(context_parts)
        
        # 3. Create system prompt
        system_prompt = f"""You are a helpful code assistant with access to a codebase. 
Use the provided code context to answer the user's question accurately.

IMPORTANT GUIDELINES:
- Reference specific files, methods, and line numbers when relevant
- If the context doesn't contain enough information, say so clearly
- Provide code examples from the context when helpful
- Explain how different parts of the code work together
- Be concise but thorough

CODE CONTEXT:
{context}

If no relevant code context is provided, let the user know that you need more specific information or that the code might not be in the indexed repositories."""

        # 4. Call LLM (Claude or OpenAI)
        try:
            if self._is_claude_model(request.model) and self.anthropic_client:
                # Use Claude
                response = self.anthropic_client.messages.create(
                    model=request.model,
                    max_tokens=1500,
                    temperature=0.1,
                    system=system_prompt,
                    messages=[
                        {"role": "user", "content": request.message}
                    ]
                )
                llm_response = response.content[0].text
            else:
                # Use OpenAI (fallback or explicit)
                model = request.model if not self._is_claude_model(request.model) else "gpt-4o-mini"
                response = self.openai_client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": request.message}
                    ],
                    temperature=0.1,
                    max_tokens=1500
                )
                llm_response = response.choices[0].message.content
                request.model = model  # Update to actual model used
            
            return ChatResponse(
                response=llm_response,
                sources=search_results,
                model_used=request.model
            )
            
        except Exception as e:
            logger.error(f"LLM API error with {request.model}: {e}")
            
            # If Claude failed, try falling back to OpenAI
            if self._is_claude_model(request.model):
                logger.info("Claude failed, falling back to OpenAI GPT-4o-mini")
                try:
                    response = self.openai_client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": request.message}
                        ],
                        temperature=0.1,
                        max_tokens=1500
                    )
                    return ChatResponse(
                        response=response.choices[0].message.content,
                        sources=search_results,
                        model_used="gpt-4o-mini (fallback)"
                    )
                except Exception as fallback_error:
                    logger.error(f"Fallback to OpenAI also failed: {fallback_error}")
            
            return ChatResponse(
                response=f"Sorry, I encountered an error while processing your request: {str(e)}",
                sources=search_results,
                model_used=request.model
            )
    
    def _is_claude_model(self, model: str) -> bool:
        """Check if the model is a Claude model."""
        claude_models = [
            "claude-3-5-sonnet-latest",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-sonnet-20240620", 
            "claude-3-5-haiku-latest",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-latest",
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307"
        ]
        return model in claude_models or model.startswith("claude-")
    
    def chat_with_history(
        self, 
        request: ChatRequest, 
        chat_history: List[ChatMessage]
    ) -> ChatResponse:
        """Chat with conversation history."""
        # Get RAG context for current message
        search_results = self.vector_store.search(
            query=request.message,
            top_k=request.max_context_chunks,
            repo_names=request.repo_names,
            languages=request.languages
        )
        
        # Build context
        context_parts = []
        for i, result in enumerate(search_results, 1):
            chunk = result.chunk
            context_parts.append(
                f"## Code Context {i}\n"
                f"**File**: {chunk.file_path}\n"
                f"```{chunk.language.value}\n{chunk.content}\n```\n"
            )
        
        context = "\n".join(context_parts)
        
        # Build messages with history
        messages = [
            {
                "role": "system", 
                "content": f"""You are a helpful code assistant. Use the code context to answer questions.

CODE CONTEXT:
{context}"""
            }
        ]
        
        # Add chat history
        for msg in chat_history[-10:]:  # Keep last 10 messages
            messages.append({"role": msg.role, "content": msg.content})
        
        # Add current message
        messages.append({"role": "user", "content": request.message})
        
        try:
            if self._is_claude_model(request.model) and self.anthropic_client:
                # Use Claude - need to separate system message from conversation
                system_content = messages[0]["content"]
                conversation_messages = messages[1:]  # Skip system message
                
                response = self.anthropic_client.messages.create(
                    model=request.model,
                    max_tokens=1500,
                    temperature=0.1,
                    system=system_content,
                    messages=conversation_messages
                )
                llm_response = response.content[0].text
            else:
                # Use OpenAI
                model = request.model if not self._is_claude_model(request.model) else "gpt-4o-mini"
                response = self.openai_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=1500
                )
                llm_response = response.choices[0].message.content
                request.model = model
            
            return ChatResponse(
                response=llm_response,
                sources=search_results,
                model_used=request.model
            )
            
        except Exception as e:
            logger.error(f"LLM API error: {e}")
            return ChatResponse(
                response=f"Error: {str(e)}",
                sources=search_results,
                model_used=request.model
            )
