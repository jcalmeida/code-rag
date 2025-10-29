#!/usr/bin/env python3
"""Command-line interface for the code RAG system."""
import argparse
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.ingestion_service import IngestionService
from src.vector_store import VectorStore
from src.models import SearchQuery
from src.llm_chat import LLMChatService, ChatRequest

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def cmd_ingest(args):
    """Ingest repositories."""
    service = IngestionService()
    
    if args.repo_name:
        # Ingest specific repository
        config = service.load_repositories_config()
        repo_config = None
        
        for repo in config.repositories:
            if repo.name == args.repo_name:
                repo_config = repo
                break
        
        if not repo_config:
            logger.error(f"Repository '{args.repo_name}' not found in config")
            return 1
        
        logger.info(f"Ingesting repository: {args.repo_name}")
        stats = service.process_repository(repo_config, args.force)
        logger.info(f"Results: {stats}")
    else:
        # Ingest all repositories
        logger.info("Ingesting all enabled repositories")
        results = service.process_all_repositories(args.force)
        
        for repo_name, stats in results.items():
            logger.info(f"{repo_name}: {stats}")
    
    return 0


def cmd_search(args):
    """Search for code."""
    vector_store = VectorStore()
    
    query = SearchQuery(
        query=args.query,
        top_k=args.top_k,
        repo_names=args.repos.split(',') if args.repos else None,
        languages=args.languages.split(',') if args.languages else None
    )
    
    logger.info(f"Searching for: {args.query}")
    results = vector_store.search(
        query=query.query,
        top_k=query.top_k,
        repo_names=query.repo_names,
        languages=query.languages
    )
    
    if not results:
        print("No results found.")
        return 0
    
    print(f"\nFound {len(results)} results:\n")
    
    for i, result in enumerate(results, 1):
        chunk = result.chunk
        print(f"{'='*80}")
        print(f"Result #{i} (Score: {result.score:.4f})")
        print(f"Repository: {chunk.repo_name}")
        print(f"File: {chunk.file_path} (lines {chunk.start_line}-{chunk.end_line})")
        print(f"Language: {chunk.language.value}")
        print(f"Type: {chunk.chunk_type}")
        if "name" in chunk.metadata:
            print(f"Name: {chunk.metadata['name']}")
        print(f"\nCode:\n{chunk.content[:500]}...")
        print()
    
    return 0


def cmd_state(args):
    """Show repository states."""
    service = IngestionService()
    
    if args.repo_name:
        state = service.get_repository_state(args.repo_name)
        if not state:
            logger.error(f"No state found for repository '{args.repo_name}'")
            return 1
        
        print(f"\nState for {args.repo_name}:")
        print(f"  Last commit: {state.last_commit_hash}")
        print(f"  Last processed: {state.last_processed_at}")
        print(f"  Total chunks: {state.total_chunks}")
        print(f"  Total files: {state.total_files}")
    else:
        states = service.get_all_states()
        
        if not states:
            print("No repository states found.")
            return 0
        
        print("\nRepository States:")
        for name, state in states.items():
            print(f"\n{name}:")
            print(f"  Last commit: {state.last_commit_hash}")
            print(f"  Last processed: {state.last_processed_at}")
            print(f"  Total chunks: {state.total_chunks}")
            print(f"  Total files: {state.total_files}")
    
    return 0


def cmd_reset(args):
    """Reset a repository."""
    service = IngestionService()
    
    if not args.confirm:
        response = input(f"Are you sure you want to reset '{args.repo_name}'? This will delete all chunks. (yes/no): ")
        if response.lower() != 'yes':
            print("Reset cancelled.")
            return 0
    
    logger.info(f"Resetting repository: {args.repo_name}")
    service.reset_repository(args.repo_name)
    logger.info("Reset complete.")
    
    return 0


def cmd_stats(args):
    """Show vector store statistics."""
    vector_store = VectorStore()
    stats = vector_store.get_stats()
    
    print("\nVector Store Statistics:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    return 0


def cmd_chat(args):
    """Chat with LLM about your codebase."""
    llm_service = LLMChatService()
    
    request = ChatRequest(
        message=args.message,
        repo_names=args.repos.split(',') if args.repos else None,
        languages=args.languages.split(',') if args.languages else None,
        max_context_chunks=args.context_chunks,
        model=args.model
    )
    
    logger.info(f"Asking: {args.message}")
    
    try:
        response = llm_service.chat(request)
        
        print(f"\n🤖 **Assistant ({response.model_used})**:")
        print(response.response)
        
        if response.sources:
            print(f"\n📚 **Sources** ({len(response.sources)} code chunks):")
            for i, result in enumerate(response.sources, 1):
                chunk = result.chunk
                print(f"{i}. {chunk.file_path} (lines {chunk.start_line}-{chunk.end_line}) - Score: {result.score:.3f}")
        
        return 0
        
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Code RAG System CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Ingest command
    ingest_parser = subparsers.add_parser('ingest', help='Ingest repositories')
    ingest_parser.add_argument('--repo-name', help='Specific repository to ingest')
    ingest_parser.add_argument('--force', action='store_true', help='Force full reindex')
    ingest_parser.set_defaults(func=cmd_ingest)
    
    # Search command
    search_parser = subparsers.add_parser('search', help='Search for code')
    search_parser.add_argument('query', help='Search query')
    search_parser.add_argument('--top-k', type=int, default=10, help='Number of results')
    search_parser.add_argument('--repos', help='Comma-separated list of repository names')
    search_parser.add_argument('--languages', help='Comma-separated list of languages')
    search_parser.set_defaults(func=cmd_search)
    
    # State command
    state_parser = subparsers.add_parser('state', help='Show repository states')
    state_parser.add_argument('--repo-name', help='Specific repository')
    state_parser.set_defaults(func=cmd_state)
    
    # Reset command
    reset_parser = subparsers.add_parser('reset', help='Reset a repository')
    reset_parser.add_argument('repo_name', help='Repository to reset')
    reset_parser.add_argument('--confirm', action='store_true', help='Skip confirmation')
    reset_parser.set_defaults(func=cmd_reset)
    
    # Stats command
    stats_parser = subparsers.add_parser('stats', help='Show vector store statistics')
    stats_parser.set_defaults(func=cmd_stats)
    
    # Chat command
    chat_parser = subparsers.add_parser('chat', help='Chat with LLM about your codebase')
    chat_parser.add_argument('message', help='Your question about the code')
    chat_parser.add_argument('--repos', help='Comma-separated list of repository names')
    chat_parser.add_argument('--languages', help='Comma-separated list of languages')
    chat_parser.add_argument('--context-chunks', type=int, default=5, help='Number of code chunks to include as context')
    chat_parser.add_argument('--model', default='claude-3-5-sonnet-latest', help='Model to use (Claude or OpenAI)')
    chat_parser.set_defaults(func=cmd_chat)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    try:
        return args.func(args)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
