"""Data models for the code RAG system."""
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class Language(str, Enum):
    """Supported programming languages."""
    CSHARP = "csharp"
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    GO = "go"


class RepositoryConfig(BaseModel):
    """Configuration for a single repository."""
    name: str = Field(..., description="Unique name for the repository")
    url: str = Field(..., description="Git URL (HTTPS or SSH)")
    branch: str = Field(default="master", description="Branch to track")
    local_path: str = Field(..., description="Local directory name for the repo")
    enabled: bool = Field(default=True, description="Whether to process this repo")
    languages: List[Language] = Field(
        default=[Language.CSHARP],
        description="Languages to process in this repo"
    )
    exclude_patterns: List[str] = Field(
        default_factory=list,
        description="Glob patterns for files/directories to exclude"
    )


class RepositoriesConfig(BaseModel):
    """Configuration for all repositories."""
    repositories: List[RepositoryConfig]


class CodeChunk(BaseModel):
    """A chunk of code with metadata."""
    id: str = Field(..., description="Unique identifier for the chunk")
    repo_name: str = Field(..., description="Repository name")
    file_path: str = Field(..., description="Relative path to the file")
    language: Language = Field(..., description="Programming language")
    content: str = Field(..., description="Code content")
    start_line: int = Field(..., description="Starting line number")
    end_line: int = Field(..., description="Ending line number")
    commit_hash: str = Field(..., description="Git commit hash")
    chunk_type: str = Field(
        default="code",
        description="Type of chunk (class, method, function, etc.)"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the chunk was created"
    )


class RepositoryState(BaseModel):
    """State tracking for a repository."""
    repo_name: str
    last_commit_hash: Optional[str] = None
    last_processed_at: Optional[datetime] = None
    total_chunks: int = 0
    total_files: int = 0


class SearchQuery(BaseModel):
    """Query model for code search."""
    query: str = Field(..., description="Natural language or code search query")
    repo_names: Optional[List[str]] = Field(
        default=None,
        description="Filter by specific repositories"
    )
    languages: Optional[List[Language]] = Field(
        default=None,
        description="Filter by programming languages"
    )
    top_k: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Number of results to return"
    )


class SearchResult(BaseModel):
    """Search result with code chunk and similarity score."""
    chunk: CodeChunk
    score: float = Field(..., description="Similarity score")
    
    
class WebhookPayload(BaseModel):
    """Webhook payload from GitHub/GitLab."""
    repository: Dict[str, Any]
    ref: Optional[str] = None
    commits: Optional[List[Dict[str, Any]]] = None
    action: Optional[str] = None
