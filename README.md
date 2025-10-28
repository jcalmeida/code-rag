# Code RAG System

A powerful Retrieval-Augmented Generation (RAG) system for code repositories. Ingest multiple repositories from GitHub/GitLab, parse code with structure awareness, and search using natural language or code queries.

## Features

- 🔍 **Semantic Code Search**: Search across multiple repositories using natural language
- 🌳 **Structure-Aware Parsing**: Uses tree-sitter to understand code structure (classes, methods, etc.)
- 🔄 **Incremental Updates**: Only processes changed files using Git diff tracking
- 🪝 **Webhook Support**: Automatic ingestion on push events (GitHub/GitLab)
- 🐳 **Docker Ready**: Easy deployment with Docker and docker-compose
- 🎯 **Multi-Language**: Extensible to support multiple programming languages (C# implemented)
- 💾 **Local Vector Store**: Uses ChromaDB for efficient local vector storage
- 🔐 **Private Repo Support**: Works with private repositories using access tokens

## Architecture

```
┌─────────────────┐
│  GitHub/GitLab  │
│   Repositories  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Git Manager    │  ← Clone, pull, diff tracking
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Code Parser    │  ← Tree-sitter structure-aware parsing
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Vector Store   │  ← ChromaDB + OpenAI embeddings
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   FastAPI       │  ← Search, ingest, webhook endpoints
└─────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- OpenAI API key
- Git
- (Optional) Docker and docker-compose

### Installation

1. **Clone the repository**:
```bash
git clone <your-repo-url>
cd windsurf-project
```

2. **Create virtual environment**:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**:
```bash
pip install -r requirements.txt
```

4. **Configure environment**:
```bash
cp .env.example .env
# Edit .env and add your credentials
```

Required environment variables:
- `OPENAI_API_KEY`: Your OpenAI API key
- `GIT_TOKEN`: GitHub/GitLab personal access token (for private repos)

5. **Configure repositories**:

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

### Usage

#### Using the CLI

**Ingest all repositories**:
```bash
python cli.py ingest
```

**Ingest a specific repository**:
```bash
python cli.py ingest --repo-name my-csharp-project
```

**Force full reindex**:
```bash
python cli.py ingest --force
```

**Search for code**:
```bash
python cli.py search "authentication middleware"
python cli.py search "how to connect to database" --top-k 5
python cli.py search "user validation" --repos my-csharp-project
```

**Check repository states**:
```bash
python cli.py state
python cli.py state --repo-name my-csharp-project
```

**Reset a repository** (forces complete reindex):
```bash
python cli.py reset my-csharp-project
```

**View statistics**:
```bash
python cli.py stats
```

#### Using the API

**Start the API server**:
```bash
python -m uvicorn src.api:app --reload
```

The API will be available at `http://localhost:8000`

**API Documentation**: Visit `http://localhost:8000/docs` for interactive API documentation

**Key Endpoints**:

- `GET /` - Health check
- `POST /search` - Search for code
- `POST /ingest` - Trigger ingestion of all repositories
- `POST /ingest/{repo_name}` - Trigger ingestion of specific repository
- `POST /webhook/github` - GitHub webhook endpoint
- `POST /webhook/gitlab` - GitLab webhook endpoint
- `GET /state` - Get all repository states
- `GET /state/{repo_name}` - Get specific repository state
- `DELETE /reset/{repo_name}` - Reset a repository

**Example API calls**:

```bash
# Search
curl -X POST "http://localhost:8000/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "authentication logic",
    "top_k": 10
  }'

# Trigger ingestion
curl -X POST "http://localhost:8000/ingest"

# Get state
curl "http://localhost:8000/state"
```

### Docker Deployment

**Build and run with docker-compose**:
```bash
docker-compose up -d
```

**View logs**:
```bash
docker-compose logs -f
```

**Stop**:
```bash
docker-compose down
```

The API will be available at `http://localhost:8000`

## Configuration

### Environment Variables

See `.env.example` for all available configuration options:

- **OpenAI Settings**:
  - `OPENAI_API_KEY`: Your OpenAI API key
  - `EMBEDDING_MODEL`: Model to use (default: text-embedding-3-small)
  - `EMBEDDING_DIMENSION`: Embedding dimension (default: 1536)

- **Git Settings**:
  - `GIT_TOKEN`: Personal access token for GitHub/GitLab

- **Storage Settings**:
  - `CHROMA_PERSIST_DIRECTORY`: ChromaDB data directory
  - `REPOS_BASE_PATH`: Base directory for cloned repos
  - `REPOS_CONFIG_PATH`: Path to repos.json

- **Chunking Settings**:
  - `MAX_CHUNK_SIZE`: Maximum chunk size in characters
  - `CHUNK_OVERLAP`: Overlap between chunks

### Repository Configuration

The `config/repos.json` file defines which repositories to process:

```json
{
  "repositories": [
    {
      "name": "unique-repo-name",
      "url": "https://github.com/user/repo.git",
      "branch": "master",
      "local_path": "local-directory-name",
      "enabled": true,
      "languages": ["csharp"],
      "exclude_patterns": [
        "*/bin/*",
        "*/obj/*",
        "*.dll"
      ]
    }
  ]
}
```

**Fields**:
- `name`: Unique identifier for the repository
- `url`: Git clone URL (HTTPS or SSH)
- `branch`: Branch to track (default: "master")
- `local_path`: Local directory name for cloning
- `enabled`: Whether to process this repository
- `languages`: Programming languages to process
- `exclude_patterns`: Glob patterns for files/directories to exclude

## Webhook Setup

### GitHub

1. Go to your repository settings → Webhooks → Add webhook
2. Set Payload URL: `http://your-server:8000/webhook/github`
3. Content type: `application/json`
4. Select events: `Push`
5. (Optional) Set a secret and add it to `WEBHOOK_SECRET` in `.env`

### GitLab

1. Go to your repository settings → Webhooks
2. Set URL: `http://your-server:8000/webhook/gitlab`
3. Select trigger: `Push events`
4. (Optional) Set a secret token matching `WEBHOOK_SECRET` in `.env`

## How It Works

### Ingestion Pipeline

1. **Git Operations**: Clone or pull latest changes from repositories
2. **Diff Detection**: Compare with last processed commit to find changed files
3. **Code Parsing**: Use tree-sitter to parse code into structural chunks (classes, methods, etc.)
4. **Embedding Generation**: Generate embeddings using OpenAI's API
5. **Vector Storage**: Store chunks and embeddings in ChromaDB
6. **State Tracking**: Save commit hash and metadata for incremental updates

### Search Process

1. **Query Embedding**: Convert search query to embedding
2. **Similarity Search**: Find most similar code chunks using vector similarity
3. **Ranking**: Return top-k results with similarity scores
4. **Context**: Include file path, repository, and code structure information

## Supported Languages

Currently implemented:
- ✅ C# (with tree-sitter)

Easily extensible to:
- Python
- JavaScript/TypeScript
- Java
- Go
- And more...

To add a new language, update:
1. `requirements.txt` - Add tree-sitter language package
2. `src/code_parser.py` - Initialize parser and add parsing logic
3. `src/models.py` - Add language to `Language` enum

## Performance Tips

1. **Chunking**: Adjust `MAX_CHUNK_SIZE` and `CHUNK_OVERLAP` based on your needs
2. **Embedding Model**: Use `text-embedding-3-small` for cost efficiency, `text-embedding-3-large` for better quality
3. **Exclude Patterns**: Exclude build artifacts, dependencies, and generated code
4. **Incremental Updates**: Webhooks enable real-time updates without full reindexing
5. **Batch Processing**: Process multiple files in parallel (future enhancement)

## Troubleshooting

**Issue**: Git clone fails with authentication error
- **Solution**: Ensure `GIT_TOKEN` is set correctly in `.env`
- For GitHub: Use a Personal Access Token with `repo` scope
- For GitLab: Use a Personal Access Token with `read_repository` scope

**Issue**: OpenAI API rate limits
- **Solution**: Implement exponential backoff (already included via `tenacity`)
- Consider using a higher rate limit tier

**Issue**: Tree-sitter parsing fails
- **Solution**: Falls back to simple chunking automatically
- Check if the language parser is properly installed

**Issue**: ChromaDB persistence issues
- **Solution**: Ensure `CHROMA_PERSIST_DIRECTORY` has write permissions
- Check disk space availability

## Development

**Run tests**:
```bash
pytest
```

**Format code**:
```bash
black src/
```

**Lint code**:
```bash
ruff check src/
```

## Future Enhancements

- [ ] Support for more programming languages
- [ ] Parallel processing for faster ingestion
- [ ] Advanced query features (filters, facets)
- [ ] Code-to-code search (find similar implementations)
- [ ] Integration with LLMs for code explanation
- [ ] Web UI for search and management
- [ ] Support for other vector databases (Pinecone, Weaviate)
- [ ] Caching layer for frequently accessed chunks

## License

MIT License - See LICENSE file for details

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## Support

For issues, questions, or contributions, please open an issue on GitHub.
