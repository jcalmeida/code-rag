# Code RAG System

A Retrieval-Augmented Generation (RAG) system for code repositories that enables semantic search and intelligent querying of your codebase using vector embeddings and language models.

## Features

- **🔍 Semantic Code Search**: Find relevant code snippets using natural language queries
- **🤖 LLM Chat Integration**: Ask questions about your code with RAG context (Claude + OpenAI support)
- **📁 Multi-Repository Support**: Index and search across multiple repositories
- **🔄 Incremental Updates**: Efficient Git-based change detection and updates
- **💻 Language Support**: Currently supports C# with extensible architecture for other languages
- **🌐 REST API**: FastAPI-based web service for integration
- **⚡ CLI Interface**: Command-line tools for direct interaction
- **🔗 MCP Integration**: Model Context Protocol server for AI assistant integration
- **📡 Webhook Integration**: Auto-update on Git push events

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Git Repos     │───▶│  Code Parser     │───▶│  Vector Store   │
│                 │    │  (Tree-sitter)   │    │  (ChromaDB)     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                        │
┌─────────────────┐    ┌──────────────────┐            │
│   REST API      │◄───│  Search Engine   │◄───────────┘
│   (FastAPI)     │    │  (Embeddings)    │
└─────────────────┘    └──────────────────┘
                              │
┌─────────────────┐    ┌──────────────────┐
│  MCP Server     │◄───│   LLM Chat       │
│  (Assistants)   │    │ (Claude/OpenAI)  │
└─────────────────┘    └──────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- OpenAI API key (for embeddings)
- Anthropic API key (optional, for Claude chat)
- Git
- (Optional) Docker and docker-compose

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/jcalmeida/code-rag.git
   cd code-rag
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

4. **Configure repositories:**
   ```bash
   # Edit config/repos.json to add your repositories
   ```

5. **Ingest your first repository:**
   ```bash
   python cli.py ingest
   ```

## Usage

### 🔍 CLI Search
```bash
# Basic search
python cli.py search "authentication middleware"

# Search with filters
python cli.py search "database connection" --repos myproject --languages python

# Get statistics
python cli.py stats
```

### 🤖 CLI Chat (LLM Integration)
```bash
# Ask questions about your code
python cli.py chat "How does authentication work in this project?"

# Use specific model
python cli.py chat "Explain the database schema" --model claude-3-5-sonnet-latest

# Filter by repository
python cli.py chat "Show me the API endpoints" --repos backend-service
```

### 🌐 REST API
```bash
# Start the server
python -m uvicorn src.api:app --reload

# Search via API
curl -X POST "http://localhost:8000/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "user authentication", "top_k": 5}'

# Chat via API
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "How do I add a new API endpoint?"}'
```

### 🔗 MCP Integration (AI Assistants)

The system provides an MCP (Model Context Protocol) server for integration with AI assistants:

```bash
# Run MCP server
python -m src.mcp_server
```

**Available MCP Tools:**
- `search_code`: Semantic code search
- `chat_with_code`: Ask questions with RAG context  
- `ingest_repository`: Update repository index
- `get_repository_stats`: Get indexing statistics

**MCP Resources:**
- `code-rag://stats`: Vector store statistics
- `code-rag://repositories`: Repository configuration

See [MCP_INTEGRATION.md](MCP_INTEGRATION.md) for detailed assistant setup.

## Configuration

### Environment Variables
Required in your `.env` file:
- `OPENAI_API_KEY`: Your OpenAI API key (for embeddings)
- `ANTHROPIC_API_KEY`: Your Anthropic API key (optional, for Claude chat)
- `GIT_TOKEN`: GitHub/GitLab personal access token (for private repos)

### Repository Configuration
Edit `config/repos.json` to add your repositories:

```json
{
  "repositories": [
    {
      "name": "my-csharp-project",
      "url": "https://github.com/username/repo.git",
      "branch": "master",
      "local_path": "my-csharp-project",
      "enabled": true,
      "languages": ["csharp"],
      "exclude_patterns": [
        "*/bin/*",
        "*/obj/*",
        "*.dll",
        "*.exe"
      ]
    }
  ]
}
```

## Development

### Running Tests
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src
```

### Docker Deployment
```bash
# Build and run with docker-compose
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- **Tree-sitter** for code parsing
- **ChromaDB** for vector storage
- **OpenAI** for embeddings
- **Anthropic** for Claude integration
- **FastAPI** for the web framework
