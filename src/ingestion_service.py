"""Ingestion service for processing repositories and updating vector store."""
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from src.config import settings
from src.models import (
    RepositoriesConfig,
    RepositoryConfig,
    RepositoryState,
    Language as LangEnum
)
from src.git_manager import GitManager
from src.code_parser import CodeParser
from src.vector_store import VectorStore

logger = logging.getLogger(__name__)


class IngestionService:
    """Orchestrates the ingestion of code repositories into the vector store."""
    
    def __init__(self):
        self.vector_store = VectorStore()
        self.code_parser = CodeParser()
        self.state_file = settings.repos_base_path / "ingestion_state.json"
        self.states: Dict[str, RepositoryState] = self._load_states()
    
    def _load_states(self) -> Dict[str, RepositoryState]:
        """Load repository states from disk."""
        if not self.state_file.exists():
            return {}
        
        try:
            with open(self.state_file, 'r') as f:
                data = json.load(f)
                return {
                    name: RepositoryState(**state_data)
                    for name, state_data in data.items()
                }
        except Exception as e:
            logger.error(f"Error loading states: {e}")
            return {}
    
    def _save_states(self):
        """Save repository states to disk."""
        try:
            data = {
                name: state.model_dump(mode='json')
                for name, state in self.states.items()
            }
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving states: {e}")
    
    def load_repositories_config(self) -> RepositoriesConfig:
        """Load repositories configuration from JSON file."""
        if not settings.repos_config_path.exists():
            logger.error(f"Config file not found: {settings.repos_config_path}")
            raise FileNotFoundError(f"Config file not found: {settings.repos_config_path}")
        
        try:
            with open(settings.repos_config_path, 'r') as f:
                data = json.load(f)
                return RepositoriesConfig(**data)
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            raise
    
    def process_repository(
        self,
        repo_config: RepositoryConfig,
        force_full_reindex: bool = False
    ) -> Dict[str, int]:
        """
        Process a single repository.
        
        Args:
            repo_config: Repository configuration
            force_full_reindex: If True, reprocess all files regardless of changes
        
        Returns:
            Dictionary with statistics (files_processed, chunks_added, etc.)
        """
        logger.info(f"Processing repository: {repo_config.name}")
        
        stats = {
            "files_processed": 0,
            "files_added": 0,
            "files_modified": 0,
            "files_deleted": 0,
            "chunks_added": 0,
            "chunks_deleted": 0
        }
        
        # Initialize Git manager
        git_manager = GitManager(repo_config)
        
        try:
            # Clone or open repository
            git_manager.clone_or_open()
            
            # Pull latest changes
            has_changes = git_manager.pull_latest()
            
            # Get current state
            current_commit = git_manager.get_current_commit()
            state = self.states.get(repo_config.name)
            
            # Determine if we need to process
            if not force_full_reindex and state and not has_changes:
                logger.info(f"No changes in {repo_config.name}, skipping")
                return stats
            
            # Get changed files
            old_commit = state.last_commit_hash if state and not force_full_reindex else None
            added_files, modified_files, deleted_files = git_manager.get_changed_files(old_commit)
            
            # Process deleted files
            for file_path in deleted_files:
                deleted_count = self.vector_store.delete_chunks_by_file(
                    repo_config.name,
                    str(file_path)
                )
                stats["chunks_deleted"] += deleted_count
                stats["files_deleted"] += 1
            
            # Process added and modified files
            files_to_process = list(added_files) + list(modified_files)
            
            for file_path in files_to_process:
                try:
                    # Determine language
                    language = self._detect_language(file_path)
                    if not language:
                        continue
                    
                    # Get file content
                    content = git_manager.get_file_content(file_path)
                    if not content:
                        logger.warning(f"Could not read file: {file_path}")
                        continue
                    
                    # If file was modified, delete old chunks first
                    if file_path in modified_files:
                        deleted_count = self.vector_store.delete_chunks_by_file(
                            repo_config.name,
                            str(file_path)
                        )
                        stats["chunks_deleted"] += deleted_count
                        stats["files_modified"] += 1
                    else:
                        stats["files_added"] += 1
                    
                    # Parse file and create chunks
                    chunks = self.code_parser.parse_file(
                        content=content,
                        file_path=file_path,
                        repo_name=repo_config.name,
                        commit_hash=current_commit,
                        language=language
                    )
                    
                    # Add chunks to vector store
                    if chunks:
                        added_count = self.vector_store.add_chunks(chunks)
                        stats["chunks_added"] += added_count
                        stats["files_processed"] += 1
                    
                except Exception as e:
                    logger.error(f"Error processing file {file_path}: {e}")
                    continue
            
            # Update state
            self.states[repo_config.name] = RepositoryState(
                repo_name=repo_config.name,
                last_commit_hash=current_commit,
                last_processed_at=datetime.utcnow(),
                total_chunks=stats["chunks_added"] - stats["chunks_deleted"],
                total_files=stats["files_processed"]
            )
            self._save_states()
            
            logger.info(
                f"Completed {repo_config.name}: "
                f"{stats['files_processed']} files, "
                f"{stats['chunks_added']} chunks added, "
                f"{stats['chunks_deleted']} chunks deleted"
            )
            
        except Exception as e:
            logger.error(f"Error processing repository {repo_config.name}: {e}")
            raise
        
        return stats
    
    def process_all_repositories(self, force_full_reindex: bool = False) -> Dict[str, Dict[str, int]]:
        """
        Process all enabled repositories.
        
        Returns:
            Dictionary mapping repository names to their processing statistics
        """
        config = self.load_repositories_config()
        results = {}
        
        for repo_config in config.repositories:
            if not repo_config.enabled:
                logger.info(f"Skipping disabled repository: {repo_config.name}")
                continue
            
            try:
                stats = self.process_repository(repo_config, force_full_reindex)
                results[repo_config.name] = stats
            except Exception as e:
                logger.error(f"Failed to process {repo_config.name}: {e}")
                results[repo_config.name] = {"error": str(e)}
        
        return results
    
    def _detect_language(self, file_path: Path) -> Optional[LangEnum]:
        """Detect programming language from file extension."""
        suffix = file_path.suffix.lower()
        
        language_map = {
            ".cs": LangEnum.CSHARP,
            ".py": LangEnum.PYTHON,
            ".js": LangEnum.JAVASCRIPT,
            ".jsx": LangEnum.JAVASCRIPT,
            ".ts": LangEnum.TYPESCRIPT,
            ".tsx": LangEnum.TYPESCRIPT,
            ".java": LangEnum.JAVA,
            ".go": LangEnum.GO,
        }
        
        return language_map.get(suffix)
    
    def get_repository_state(self, repo_name: str) -> Optional[RepositoryState]:
        """Get the current state of a repository."""
        return self.states.get(repo_name)
    
    def get_all_states(self) -> Dict[str, RepositoryState]:
        """Get states for all repositories."""
        return self.states
    
    def reset_repository(self, repo_name: str):
        """
        Reset a repository by deleting all its chunks and state.
        Useful for forcing a complete reindex.
        """
        logger.info(f"Resetting repository: {repo_name}")
        
        # Delete all chunks
        deleted_count = self.vector_store.delete_chunks_by_repo(repo_name)
        logger.info(f"Deleted {deleted_count} chunks")
        
        # Remove state
        if repo_name in self.states:
            del self.states[repo_name]
            self._save_states()
        
        logger.info(f"Reset complete for {repo_name}")
