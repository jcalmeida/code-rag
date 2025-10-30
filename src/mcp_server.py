"""MCP (Model Context Protocol) Server for Code RAG System.

This module provides an MCP server that exposes the Code RAG system's functionality
to AI assistants and other MCP clients. It allows assistants to search code,
ask questions with RAG context, and manage repositories.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Sequence
import json

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource,
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource
)

from src.config import settings
from src.vector_store import VectorStore
from src.llm_chat import LLMChatService, ChatRequest
from src.ingestion_service import IngestionService
from src.models import SearchQuery

logger = logging.getLogger(__name__)


class CodeRAGMCPServer:
    """MCP Server for Code RAG System."""
    
    def __init__(self):
        self.server = Server("code-rag")
        self.vector_store = VectorStore()
        self.llm_service = LLMChatService()
        self.ingestion_service = IngestionService()
        
        # Setup MCP server
        self.setup_tools()
        self.setup_resources()
    
    def setup_tools(self) -> None:
        """Setup MCP tools for the server."""
        
        @self.server.list_tools()
        async def handle_list_tools() -> List[Tool]:
            """List available tools."""
            return [
                Tool(
                    name="search_code",
                    description="Search for code using semantic similarity",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query for finding relevant code"
                            },
                            "repo_names": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Filter by specific repository names"
                            },
                            "languages": {
                                "type": "array", 
                                "items": {"type": "string"},
                                "description": "Filter by programming languages"
                            },
                            "top_k": {
                                "type": "integer",
                                "description": "Number of results to return",
                                "default": 5
                            }
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="chat_with_code",
                    description="Ask questions about the codebase with RAG context",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "message": {
                                "type": "string",
                                "description": "Question or message about the code"
                            },
                            "repo_names": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Filter by specific repository names"
                            },
                            "languages": {
                                "type": "array",
                                "items": {"type": "string"}, 
                                "description": "Filter by programming languages"
                            },
                            "max_context_chunks": {
                                "type": "integer",
                                "description": "Number of code chunks to include as context",
                                "default": 5
                            },
                            "model": {
                                "type": "string",
                                "description": "LLM model to use for the response",
                                "default": "claude-sonnet-4-5"
                            }
                        },
                        "required": ["message"]
                    }
                ),
                Tool(
                    name="ingest_repository",
                    description="Ingest or update a repository in the vector store",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "repo_name": {
                                "type": "string",
                                "description": "Name of the repository to ingest"
                            },
                            "force": {
                                "type": "boolean",
                                "description": "Force full re-indexing even if no changes detected",
                                "default": False
                            }
                        },
                        "required": ["repo_name"]
                    }
                ),
                Tool(
                    name="get_repository_stats",
                    description="Get statistics about indexed repositories and code chunks",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                )
            ]
        
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            """Handle tool calls."""
            try:
                if name == "search_code":
                    return await self._search_code(**arguments)
                elif name == "chat_with_code":
                    return await self._chat_with_code(**arguments)
                elif name == "ingest_repository":
                    return await self._ingest_repository(**arguments)
                elif name == "get_repository_stats":
                    return await self._get_repository_stats()
                else:
                    raise ValueError(f"Unknown tool: {name}")
            except Exception as e:
                logger.error(f"Tool call error for {name}: {e}")
                return [TextContent(type="text", text=f"Error: {str(e)}")]
    
    def setup_resources(self) -> None:
        """Setup MCP resources for the server."""
        
        @self.server.list_resources()
        async def handle_list_resources() -> List[Resource]:
            """List available resources."""
            return [
                Resource(
                    uri="code-rag://stats",
                    name="Vector Store Statistics",
                    description="Current statistics about the indexed code",
                    mimeType="application/json"
                ),
                Resource(
                    uri="code-rag://repositories",
                    name="Repository List",
                    description="List of configured repositories",
                    mimeType="application/json"
                )
            ]
        
        @self.server.read_resource()
        async def handle_read_resource(uri: str) -> str:
            """Handle resource reads."""
            if uri == "code-rag://stats":
                stats = self.vector_store.get_stats()
                return json.dumps(stats, indent=2)
            elif uri == "code-rag://repositories":
                config = self.ingestion_service.load_repositories_config()
                repos = [{"name": repo.name, "url": repo.url, "enabled": repo.enabled} 
                        for repo in config.repositories]
                return json.dumps(repos, indent=2)
            else:
                raise ValueError(f"Unknown resource: {uri}")
    
    async def _search_code(
        self, 
        query: str, 
        repo_names: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
        top_k: int = 5
    ) -> List[TextContent]:
        """Search for code using semantic similarity."""
        search_query = SearchQuery(
            query=query,
            repo_names=repo_names,
            languages=languages,
            top_k=top_k
        )
        
        results = self.vector_store.search(
            query=search_query.query,
            top_k=search_query.top_k,
            repo_names=search_query.repo_names,
            languages=search_query.languages
        )
        
        if not results:
            return [TextContent(type="text", text="No code found matching your query.")]
        
        response_parts = [f"Found {len(results)} code chunks:\n"]
        
        for i, result in enumerate(results, 1):
            chunk = result.chunk
            response_parts.append(
                f"## Result {i} (Score: {result.score:.3f})\n"
                f"**File**: {chunk.file_path} (lines {chunk.start_line}-{chunk.end_line})\n"
                f"**Repository**: {chunk.repo_name}\n"
                f"**Language**: {chunk.language.value}\n"
                f"**Type**: {chunk.chunk_type}\n"
                f"**Name**: {chunk.metadata.get('name', 'N/A')}\n\n"
                f"```{chunk.language.value}\n{chunk.content}\n```\n"
            )
        
        return [TextContent(type="text", text="\n".join(response_parts))]
    
    async def _chat_with_code(
        self,
        message: str,
        repo_names: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
        max_context_chunks: int = 5,
        model: str = "claude-sonnet-4-5"
    ) -> List[TextContent]:
        """Ask questions about the codebase with RAG context."""
        request = ChatRequest(
            message=message,
            repo_names=repo_names,
            languages=languages,
            max_context_chunks=max_context_chunks,
            model=model
        )
        
        response = self.llm_service.chat(request)
        
        response_parts = [
            f"**Assistant ({response.model_used})**:\n",
            response.response
        ]
        
        if response.sources:
            response_parts.append(f"\n\n**Sources** ({len(response.sources)} code chunks):")
            for i, result in enumerate(response.sources, 1):
                chunk = result.chunk
                response_parts.append(
                    f"{i}. {chunk.file_path} (lines {chunk.start_line}-{chunk.end_line}) - Score: {result.score:.3f}"
                )
        
        return [TextContent(type="text", text="\n".join(response_parts))]
    
    async def _ingest_repository(self, repo_name: str, force: bool = False) -> List[TextContent]:
        """Ingest or update a repository."""
        try:
            config = self.ingestion_service.load_repositories_config()
            repo_config = None
            
            for repo in config.repositories:
                if repo.name == repo_name:
                    repo_config = repo
                    break
            
            if not repo_config:
                return [TextContent(type="text", text=f"Repository '{repo_name}' not found in configuration.")]
            
            stats = self.ingestion_service.process_repository(repo_config, force_full_reindex=force)
            
            result = (
                f"Successfully processed repository '{repo_name}':\n"
                f"- Files processed: {stats['files_processed']}\n"
                f"- Files added: {stats['files_added']}\n"
                f"- Files modified: {stats['files_modified']}\n"
                f"- Files deleted: {stats['files_deleted']}\n"
                f"- Chunks added: {stats['chunks_added']}\n"
                f"- Chunks deleted: {stats['chunks_deleted']}"
            )
            
            return [TextContent(type="text", text=result)]
            
        except Exception as e:
            logger.error(f"Error ingesting repository {repo_name}: {e}")
            return [TextContent(type="text", text=f"Error ingesting repository: {str(e)}")]
    
    async def _get_repository_stats(self) -> List[TextContent]:
        """Get statistics about indexed repositories."""
        stats = self.vector_store.get_stats()
        
        result = (
            "**Vector Store Statistics:**\n"
            f"- Total chunks: {stats.get('total_chunks', 0)}\n"
            f"- Total files: {stats.get('total_files', 0)}\n"
            f"- Total repositories: {stats.get('total_repositories', 0)}\n"
            f"- Languages: {', '.join(stats.get('languages', []))}\n"
            f"- Last updated: {stats.get('last_updated', 'Unknown')}"
        )
        
        return [TextContent(type="text", text=result)]


async def main():
    """Run the MCP server."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create and run server
    code_rag_server = CodeRAGMCPServer()
    
    # Run server with stdio transport
    async with stdio_server() as (read_stream, write_stream):
        await code_rag_server.server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="code-rag",
                server_version="1.0.0",
                capabilities=code_rag_server.server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                )
            )
        )


if __name__ == "__main__":
    # Configure logging to be less verbose
    logging.basicConfig(level=logging.WARNING)
    # Suppress specific loggers that are too verbose
    logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.ERROR)
    logging.getLogger("src.vector_store").setLevel(logging.ERROR)
    logging.getLogger("mcp.server").setLevel(logging.ERROR)
    
    asyncio.run(main())
