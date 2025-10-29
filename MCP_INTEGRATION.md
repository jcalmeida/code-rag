# MCP Integration Guide

This document explains how the Code RAG system integrates with AI assistants through the Model Context Protocol (MCP) and how the ingestion, vector storage, and assistant workflows work together.

## Overview

The Code RAG system provides three main integration points:

1. **🔄 Ingestion Pipeline**: Processes code repositories into searchable chunks
2. **🔍 Vector Store**: Enables semantic search across code
3. **🤖 MCP Server**: Exposes functionality to AI assistants

## Architecture Flow

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Git Repos     │───▶│  Ingestion       │───▶│  Vector Store   │
│                 │    │  Pipeline        │    │  (ChromaDB)     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │                          │
                              ▼                          ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Git Changes    │───▶│  Incremental     │───▶│  Updated Index  │
│  (Webhooks)     │    │  Updates         │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                         │
                                                         ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  AI Assistant   │◄───│  MCP Server      │◄───│  Search Engine  │
│  (Claude/GPT)   │    │  (Tools/Res.)    │    │  + LLM Chat     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## 1. Ingestion Pipeline

### How It Works

The ingestion pipeline transforms raw code repositories into searchable vector embeddings:

1. **Repository Cloning**: Git repositories are cloned/updated locally
2. **Change Detection**: Git diff analysis identifies modified files
3. **Code Parsing**: Tree-sitter parses code into structured chunks (methods, classes, etc.)
4. **Embedding Generation**: OpenAI creates vector embeddings for each chunk
5. **Vector Storage**: ChromaDB stores embeddings with metadata

### Triggering Ingestion

```bash
# Manual ingestion
python cli.py ingest

# Force full re-index
python cli.py ingest --force

# Via API
curl -X POST "http://localhost:8000/ingest"

# Via MCP (from assistant)
mcp_client.call_tool("ingest_repository", {"repo_name": "my-project"})

# Automatic via webhook
# GitHub/GitLab pushes trigger auto-ingestion
```

### Incremental Updates

The system efficiently handles code changes:

- **Git-based tracking**: Only processes changed files
- **Chunk-level updates**: Replaces only modified code chunks
- **Metadata preservation**: Maintains file structure and context
- **Atomic operations**: Ensures consistency during updates

## 2. Vector Store & Search

### Storage Structure

Each code chunk contains:

```json
{
  "id": "unique_chunk_id",
  "repo_name": "example-project",
  "file_path": "src/auth/middleware.py",
  "language": "python",
  "content": "def authenticate_user(request):\n    # code here",
  "start_line": 15,
  "end_line": 25,
  "chunk_type": "method_declaration",
  "metadata": {
    "name": "authenticate_user",
    "context": "AuthMiddleware"
  },
  "embedding": [0.1, 0.2, ...],  // 1536-dimensional vector
  "created_at": "2024-01-01T00:00:00Z"
}
```

### Search Capabilities

- **Semantic Search**: Natural language queries find relevant code
- **Filtering**: By repository, language, file type
- **Ranking**: Cosine similarity scoring
- **Context**: Preserves code structure and relationships

## 3. MCP Server Integration

### Available Tools

#### `search_code`
Semantic code search with filtering options.

```json
{
  "name": "search_code",
  "arguments": {
    "query": "authentication middleware",
    "repo_names": ["backend-service"],
    "languages": ["python", "javascript"],
    "top_k": 5
  }
}
```

**Returns**: Ranked list of code chunks with metadata and similarity scores.

#### `chat_with_code`
Ask questions about code with RAG context.

```json
{
  "name": "chat_with_code", 
  "arguments": {
    "message": "How does user authentication work?",
    "repo_names": ["backend-service"],
    "max_context_chunks": 5,
    "model": "claude-3-5-sonnet-latest"
  }
}
```

**Returns**: LLM response with relevant code context and source citations.

#### `ingest_repository`
Trigger repository ingestion or updates.

```json
{
  "name": "ingest_repository",
  "arguments": {
    "repo_name": "backend-service",
    "force": false
  }
}
```

**Returns**: Ingestion statistics (files processed, chunks added/updated).

#### `get_repository_stats`
Get current vector store statistics.

```json
{
  "name": "get_repository_stats",
  "arguments": {}
}
```

**Returns**: Total chunks, files, repositories, languages, last update time.

### Available Resources

#### `code-rag://stats`
Real-time vector store statistics in JSON format.

#### `code-rag://repositories`
List of configured repositories with status.

## 4. Assistant Integration Workflows

### Workflow 1: Code Discovery
```
1. Assistant receives user query: "Find authentication code"
2. Assistant calls search_code tool
3. System searches vector store semantically
4. Returns ranked code chunks with context
5. Assistant presents formatted results to user
```

### Workflow 2: Code Q&A
```
1. User asks: "How does login work in this project?"
2. Assistant calls chat_with_code tool
3. System searches for relevant code chunks
4. LLM (Claude/GPT) generates response with code context
5. Assistant presents answer with source citations
```

### Workflow 3: Code Updates
```
1. Developer pushes code changes to Git
2. Webhook triggers ingestion pipeline
3. System processes only changed files
4. Vector store updated with new embeddings
5. Assistant has access to latest code immediately
```

### Workflow 4: Repository Management
```
1. Assistant calls get_repository_stats
2. Identifies outdated repositories
3. Calls ingest_repository for updates
4. Monitors ingestion progress
5. Notifies user when complete
```

## 5. Setting Up AI Assistants

### Claude Desktop Integration

1. **Install Claude Desktop** with MCP support

2. **Configure MCP server** in Claude's settings:
```json
{
  "mcpServers": {
    "code-rag": {
      "command": "python",
      "args": ["-m", "src.mcp_server"],
      "env": {
        "OPENAI_API_KEY": "your-openai-key",
        "ANTHROPIC_API_KEY": "your-claude-key"
      }
    }
  }
}
```

3. **Start the MCP server**:
```bash
cd /path/to/code-rag
python -m src.mcp_server
```

4. **Use in Claude**:
   - "Search for authentication code in my project"
   - "How does the database connection work?"
   - "Update the backend-service repository index"

### Custom Assistant Integration

```python
# Example: Custom assistant using MCP client
import asyncio
from mcp.client import Client

class CodeAssistant:
    def __init__(self):
        self.mcp_client = Client()
    
    async def connect(self):
        await self.mcp_client.connect("code-rag", "stdio")
    
    async def search_code(self, query: str, repos: list = None):
        """Search for code using semantic similarity."""
        result = await self.mcp_client.call_tool("search_code", {
            "query": query,
            "repo_names": repos,
            "top_k": 5
        })
        return result
    
    async def ask_about_code(self, question: str):
        """Ask questions about the codebase."""
        result = await self.mcp_client.call_tool("chat_with_code", {
            "message": question,
            "max_context_chunks": 5
        })
        return result
    
    async def analyze_project(self, repo_name: str):
        """Comprehensive project analysis."""
        # Get repository stats
        stats = await self.mcp_client.call_tool("get_repository_stats", {})
        
        # Search for main components
        components = await self.search_code("main class method", [repo_name])
        
        # Ask for architecture overview
        overview = await self.ask_about_code(
            f"What is the overall architecture of {repo_name}?"
        )
        
        return {
            "stats": stats,
            "components": components,
            "overview": overview
        }

# Usage
async def main():
    assistant = CodeAssistant()
    await assistant.connect()
    
    # Interactive code exploration
    analysis = await assistant.analyze_project("my-backend")
    print(analysis)

if __name__ == "__main__":
    asyncio.run(main())
```

## 6. Advanced Use Cases

### Code Review Assistant
```python
async def review_changes(self, repo_name: str, file_path: str):
    """Review code changes and suggest improvements."""
    # Search for similar patterns
    similar = await self.search_code(f"similar to {file_path}", [repo_name])
    
    # Ask for review
    review = await self.ask_about_code(
        f"Review the code in {file_path} and suggest improvements"
    )
    
    return {"similar_code": similar, "review": review}
```

### Documentation Generator
```python
async def generate_docs(self, repo_name: str):
    """Generate documentation for a repository."""
    # Get all public APIs
    apis = await self.search_code("public method function", [repo_name])
    
    # Generate documentation
    docs = await self.ask_about_code(
        f"Generate API documentation for {repo_name}"
    )
    
    return docs
```

### Debugging Assistant
```python
async def debug_issue(self, error_message: str, repo_name: str):
    """Help debug issues by finding relevant code."""
    # Search for error-related code
    related = await self.search_code(f"error handling {error_message}", [repo_name])
    
    # Get debugging suggestions
    suggestions = await self.ask_about_code(
        f"How to debug this error: {error_message}"
    )
    
    return {"related_code": related, "suggestions": suggestions}
```

## 7. Best Practices

### Repository Organization
- **Consistent naming**: Use clear, descriptive repository names
- **Regular updates**: Set up webhooks for automatic ingestion
- **Exclude patterns**: Filter out build artifacts, dependencies
- **Branch strategy**: Index main/master branches for stability

### Query Optimization
- **Specific queries**: "authentication middleware" vs "auth"
- **Context filtering**: Use repo/language filters for precision
- **Iterative refinement**: Start broad, then narrow down
- **Combine tools**: Use search + chat for comprehensive answers

### Performance Considerations
- **Batch ingestion**: Process multiple repositories together
- **Incremental updates**: Leverage Git-based change detection
- **Caching**: Vector embeddings are cached for efficiency
- **Resource limits**: Monitor memory usage with large codebases

### Security
- **API keys**: Store securely in environment variables
- **Access control**: Limit repository access as needed
- **Data privacy**: Embeddings contain code semantics
- **Network security**: Use HTTPS for API endpoints

## 8. Troubleshooting

### Common Issues

**MCP Server Won't Start**
```bash
# Check Python path and dependencies
python -m src.mcp_server --help

# Verify environment variables
echo $OPENAI_API_KEY
```

**Search Returns No Results**
```bash
# Check if repository is ingested
python cli.py stats

# Re-ingest if needed
python cli.py ingest --force
```

**Assistant Can't Connect**
- Verify MCP server is running
- Check network connectivity
- Validate configuration files
- Review server logs for errors

### Debugging Commands

```bash
# Test MCP server locally
python -m src.mcp_server

# Check vector store health
python cli.py stats

# Test search functionality
python cli.py search "test query"

# Validate configuration
python -c "from src.config import settings; print(settings)"
```

## 9. Future Enhancements

### Planned Features
- **Multi-language support**: Python, JavaScript, Java, etc.
- **Advanced parsing**: Function calls, imports, dependencies
- **Code relationships**: Cross-reference analysis
- **Real-time sync**: Live code updates during development
- **Visual interfaces**: Web-based code exploration
- **Team collaboration**: Shared knowledge bases

### Integration Opportunities
- **IDE plugins**: VS Code, IntelliJ extensions
- **CI/CD pipelines**: Automated documentation generation
- **Code review tools**: GitHub/GitLab integration
- **Slack/Teams bots**: Conversational code search
- **Knowledge bases**: Confluence, Notion integration

This MCP integration enables powerful AI-assisted code exploration, making your codebase more accessible and understandable through natural language interaction.
