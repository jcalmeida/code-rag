"""FastAPI application for the code RAG system."""
import logging
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.config import settings
from src.models import SearchQuery, SearchResult, WebhookPayload
from src.ingestion_service import IngestionService
from src.vector_store import VectorStore
from src.llm_chat import LLMChatService, ChatRequest, ChatResponse, ChatMessage

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Code RAG API",
    description="API for searching and querying code repositories using RAG",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
ingestion_service = IngestionService()
vector_store = VectorStore()
llm_chat_service = LLMChatService()


# Response models
class HealthResponse(BaseModel):
    status: str
    version: str
    vector_store_stats: Dict


class IngestResponse(BaseModel):
    message: str
    results: Dict[str, Dict]


class StateResponse(BaseModel):
    states: Dict


class ResetResponse(BaseModel):
    message: str
    repo_name: str


# Endpoints
@app.get("/", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    stats = vector_store.get_stats()
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        vector_store_stats=stats
    )


@app.post("/search", response_model=List[SearchResult])
async def search_code(query: SearchQuery):
    """
    Search for code using natural language or code queries.
    
    Args:
        query: Search query with filters
    
    Returns:
        List of search results with code chunks and similarity scores
    """
    try:
        # Convert language enums to strings if provided
        languages = [lang.value for lang in query.languages] if query.languages else None
        
        results = vector_store.search(
            query=query.query,
            top_k=query.top_k,
            repo_names=query.repo_names,
            languages=languages
        )
        
        return results
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest", response_model=IngestResponse)
async def ingest_repositories(
    background_tasks: BackgroundTasks,
    force_full_reindex: bool = False
):
    """
    Trigger ingestion of all enabled repositories.
    
    Args:
        force_full_reindex: If True, reprocess all files regardless of changes
    
    Returns:
        Ingestion results for each repository
    """
    try:
        # Run ingestion in background
        def run_ingestion():
            try:
                results = ingestion_service.process_all_repositories(force_full_reindex)
                logger.info(f"Ingestion completed: {results}")
            except Exception as e:
                logger.error(f"Ingestion error: {e}")
        
        background_tasks.add_task(run_ingestion)
        
        return IngestResponse(
            message="Ingestion started in background",
            results={}
        )
    except Exception as e:
        logger.error(f"Error starting ingestion: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest/{repo_name}", response_model=IngestResponse)
async def ingest_single_repository(
    repo_name: str,
    background_tasks: BackgroundTasks,
    force_full_reindex: bool = False
):
    """
    Trigger ingestion of a specific repository.
    
    Args:
        repo_name: Name of the repository to ingest
        force_full_reindex: If True, reprocess all files regardless of changes
    
    Returns:
        Ingestion results for the repository
    """
    try:
        # Load config and find the repository
        config = ingestion_service.load_repositories_config()
        repo_config = None
        
        for repo in config.repositories:
            if repo.name == repo_name:
                repo_config = repo
                break
        
        if not repo_config:
            raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found in config")
        
        if not repo_config.enabled:
            raise HTTPException(status_code=400, detail=f"Repository '{repo_name}' is disabled")
        
        # Run ingestion in background
        def run_ingestion():
            try:
                stats = ingestion_service.process_repository(repo_config, force_full_reindex)
                logger.info(f"Ingestion completed for {repo_name}: {stats}")
            except Exception as e:
                logger.error(f"Ingestion error for {repo_name}: {e}")
        
        background_tasks.add_task(run_ingestion)
        
        return IngestResponse(
            message=f"Ingestion started for {repo_name}",
            results={}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting ingestion for {repo_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhook/github")
async def github_webhook(
    payload: WebhookPayload,
    background_tasks: BackgroundTasks,
    x_hub_signature: Optional[str] = Header(None)
):
    """
    Webhook endpoint for GitHub push events.
    
    Automatically triggers ingestion when code is pushed.
    """
    try:
        # TODO: Verify webhook signature if webhook_secret is configured
        if settings.webhook_secret and x_hub_signature:
            # Implement HMAC verification here
            pass
        
        # Extract repository name from URL
        repo_url = payload.repository.get("clone_url") or payload.repository.get("html_url")
        
        if not repo_url:
            raise HTTPException(status_code=400, detail="Could not extract repository URL")
        
        # Find matching repository in config
        config = ingestion_service.load_repositories_config()
        repo_config = None
        
        for repo in config.repositories:
            if repo.url in repo_url or repo_url in repo.url:
                repo_config = repo
                break
        
        if not repo_config:
            logger.warning(f"Webhook received for unknown repository: {repo_url}")
            return {"message": "Repository not configured, ignoring"}
        
        # Trigger ingestion in background
        def run_ingestion():
            try:
                stats = ingestion_service.process_repository(repo_config, force_full_reindex=False)
                logger.info(f"Webhook ingestion completed for {repo_config.name}: {stats}")
            except Exception as e:
                logger.error(f"Webhook ingestion error for {repo_config.name}: {e}")
        
        background_tasks.add_task(run_ingestion)
        
        return {"message": f"Ingestion triggered for {repo_config.name}"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhook/gitlab")
async def gitlab_webhook(
    payload: Dict,
    background_tasks: BackgroundTasks,
    x_gitlab_token: Optional[str] = Header(None)
):
    """
    Webhook endpoint for GitLab push events.
    
    Automatically triggers ingestion when code is pushed.
    """
    try:
        # TODO: Verify webhook token if webhook_secret is configured
        if settings.webhook_secret and x_gitlab_token:
            if x_gitlab_token != settings.webhook_secret:
                raise HTTPException(status_code=401, detail="Invalid webhook token")
        
        # Extract repository URL from GitLab payload
        project = payload.get("project", {})
        repo_url = project.get("git_http_url") or project.get("http_url")
        
        if not repo_url:
            raise HTTPException(status_code=400, detail="Could not extract repository URL")
        
        # Find matching repository in config
        config = ingestion_service.load_repositories_config()
        repo_config = None
        
        for repo in config.repositories:
            if repo.url in repo_url or repo_url in repo.url:
                repo_config = repo
                break
        
        if not repo_config:
            logger.warning(f"Webhook received for unknown repository: {repo_url}")
            return {"message": "Repository not configured, ignoring"}
        
        # Trigger ingestion in background
        def run_ingestion():
            try:
                stats = ingestion_service.process_repository(repo_config, force_full_reindex=False)
                logger.info(f"Webhook ingestion completed for {repo_config.name}: {stats}")
            except Exception as e:
                logger.error(f"Webhook ingestion error for {repo_config.name}: {e}")
        
        background_tasks.add_task(run_ingestion)
        
        return {"message": f"Ingestion triggered for {repo_config.name}"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/state", response_model=StateResponse)
async def get_states():
    """Get the current state of all repositories."""
    states = ingestion_service.get_all_states()
    return StateResponse(
        states={name: state.model_dump() for name, state in states.items()}
    )


@app.get("/state/{repo_name}")
async def get_repository_state(repo_name: str):
    """Get the current state of a specific repository."""
    state = ingestion_service.get_repository_state(repo_name)
    
    if not state:
        raise HTTPException(status_code=404, detail=f"No state found for repository '{repo_name}'")
    
    return state


@app.delete("/reset/{repo_name}", response_model=ResetResponse)
async def reset_repository(repo_name: str):
    """
    Reset a repository by deleting all its chunks and state.
    Use this to force a complete reindex.
    """
    try:
        ingestion_service.reset_repository(repo_name)
        return ResetResponse(
            message=f"Repository '{repo_name}' has been reset",
            repo_name=repo_name
        )
    except Exception as e:
        logger.error(f"Error resetting repository {repo_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat", response_model=ChatResponse)
async def chat_with_code(request: ChatRequest):
    """
    Chat with an LLM that has access to your codebase via RAG.
    
    Ask questions about your code in natural language and get responses
    with relevant code context and explanations.
    """
    try:
        response = llm_chat_service.chat(request)
        return response
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ChatWithHistoryRequest(BaseModel):
    """Chat request with conversation history."""
    message: str
    chat_history: List[ChatMessage] = []
    repo_names: Optional[List[str]] = None
    languages: Optional[List[str]] = None
    max_context_chunks: int = 5
    model: str = "gpt-4o-mini"


@app.post("/chat/history", response_model=ChatResponse)
async def chat_with_history(request: ChatWithHistoryRequest):
    """
    Chat with conversation history for multi-turn conversations.
    
    Maintains context across multiple messages while pulling in
    relevant code context for each query.
    """
    try:
        chat_request = ChatRequest(
            message=request.message,
            repo_names=request.repo_names,
            languages=request.languages,
            max_context_chunks=request.max_context_chunks,
            model=request.model
        )
        
        response = llm_chat_service.chat_with_history(
            chat_request, 
            request.chat_history
        )
        return response
    except Exception as e:
        logger.error(f"Chat with history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.api:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True
    )
