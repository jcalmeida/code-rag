"""Git repository management with diff tracking."""
import logging
from pathlib import Path
from typing import List, Optional, Set, Tuple
from git import Repo, GitCommandError
from git.objects.commit import Commit

from src.config import settings
from src.models import RepositoryConfig

logger = logging.getLogger(__name__)


class GitManager:
    """Manages Git operations for repositories."""
    
    def __init__(self, repo_config: RepositoryConfig):
        self.config = repo_config
        self.local_path = settings.repos_base_path / repo_config.local_path
        self.repo: Optional[Repo] = None
        
    def _get_authenticated_url(self) -> str:
        """Get Git URL with authentication token if available."""
        url = self.config.url
        
        if settings.git_token and url.startswith("https://"):
            # Insert token into URL: https://token@github.com/user/repo.git
            parts = url.split("://", 1)
            if len(parts) == 2:
                url = f"{parts[0]}://{settings.git_token}@{parts[1]}"
        
        return url
    
    def clone_or_open(self) -> Repo:
        """Clone repository if it doesn't exist, otherwise open it."""
        if self.local_path.exists():
            logger.info(f"Opening existing repository: {self.config.name}")
            try:
                self.repo = Repo(self.local_path)
                return self.repo
            except Exception as e:
                logger.warning(f"Failed to open repo, will re-clone: {e}")
                # If repo is corrupted, remove and re-clone
                import shutil
                shutil.rmtree(self.local_path)
        
        logger.info(f"Cloning repository: {self.config.name}")
        url = self._get_authenticated_url()
        
        try:
            self.repo = Repo.clone_from(
                url,
                self.local_path,
                branch=self.config.branch,
                depth=1  # Shallow clone for efficiency
            )
            logger.info(f"Successfully cloned: {self.config.name}")
            return self.repo
        except GitCommandError as e:
            logger.error(f"Failed to clone repository {self.config.name}: {e}")
            raise
    
    def pull_latest(self) -> bool:
        """Pull latest changes from remote. Returns True if there are new commits."""
        if not self.repo:
            self.clone_or_open()
        
        try:
            # Get current commit before pull
            old_commit = self.repo.head.commit.hexsha
            
            # Fetch and pull
            origin = self.repo.remotes.origin
            origin.fetch()
            origin.pull(self.config.branch)
            
            # Get new commit after pull
            new_commit = self.repo.head.commit.hexsha
            
            has_changes = old_commit != new_commit
            if has_changes:
                logger.info(f"Repository {self.config.name} updated: {old_commit[:7]} -> {new_commit[:7]}")
            else:
                logger.info(f"Repository {self.config.name} is up to date")
            
            return has_changes
        except GitCommandError as e:
            logger.error(f"Failed to pull repository {self.config.name}: {e}")
            raise
    
    def get_current_commit(self) -> str:
        """Get current commit hash."""
        if not self.repo:
            self.clone_or_open()
        return self.repo.head.commit.hexsha
    
    def get_changed_files(self, old_commit: Optional[str] = None) -> Tuple[Set[Path], Set[Path], Set[Path]]:
        """
        Get files that changed between old_commit and current HEAD.
        
        Returns:
            Tuple of (added_files, modified_files, deleted_files)
        """
        if not self.repo:
            self.clone_or_open()
        
        added_files: Set[Path] = set()
        modified_files: Set[Path] = set()
        deleted_files: Set[Path] = set()
        
        if not old_commit:
            # First time processing - get all files
            for item in self.repo.tree().traverse():
                if item.type == 'blob':  # It's a file
                    file_path = Path(item.path)
                    if self._should_process_file(file_path):
                        added_files.add(file_path)
            return added_files, modified_files, deleted_files
        
        try:
            # Get diff between old commit and current HEAD
            old_commit_obj = self.repo.commit(old_commit)
            current_commit_obj = self.repo.head.commit
            
            diff_index = old_commit_obj.diff(current_commit_obj)
            
            for diff_item in diff_index:
                file_path = Path(diff_item.a_path if diff_item.a_path else diff_item.b_path)
                
                if not self._should_process_file(file_path):
                    continue
                
                if diff_item.change_type == 'A':  # Added
                    added_files.add(file_path)
                elif diff_item.change_type == 'M':  # Modified
                    modified_files.add(file_path)
                elif diff_item.change_type == 'D':  # Deleted
                    deleted_files.add(file_path)
                elif diff_item.change_type == 'R':  # Renamed
                    deleted_files.add(Path(diff_item.a_path))
                    added_files.add(Path(diff_item.b_path))
            
            logger.info(
                f"Changes in {self.config.name}: "
                f"+{len(added_files)} ~{len(modified_files)} -{len(deleted_files)}"
            )
            
        except Exception as e:
            logger.error(f"Error getting diff for {self.config.name}: {e}")
            # Fallback: treat everything as new
            for item in self.repo.tree().traverse():
                if item.type == 'blob':
                    file_path = Path(item.path)
                    if self._should_process_file(file_path):
                        added_files.add(file_path)
        
        return added_files, modified_files, deleted_files
    
    def _should_process_file(self, file_path: Path) -> bool:
        """Check if file should be processed based on language and exclude patterns."""
        # Check file extension matches configured languages
        suffix = file_path.suffix.lower()
        
        language_extensions = {
            "csharp": [".cs"],
            "python": [".py"],
            "javascript": [".js", ".jsx"],
            "typescript": [".ts", ".tsx"],
            "java": [".java"],
            "go": [".go"],
        }
        
        valid_extensions = []
        for lang in self.config.languages:
            valid_extensions.extend(language_extensions.get(lang.value, []))
        
        if suffix not in valid_extensions:
            return False
        
        # Check exclude patterns
        file_str = str(file_path)
        for pattern in self.config.exclude_patterns:
            # Simple pattern matching (can be enhanced with fnmatch if needed)
            pattern_clean = pattern.replace("*/", "").replace("/*", "")
            if pattern_clean in file_str:
                return False
        
        return True
    
    def get_file_content(self, file_path: Path) -> Optional[str]:
        """Get content of a file from the repository."""
        full_path = self.local_path / file_path
        
        if not full_path.exists():
            return None
        
        try:
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return None
    
    def get_all_files(self) -> List[Path]:
        """Get all processable files in the repository."""
        if not self.repo:
            self.clone_or_open()
        
        files = []
        for item in self.repo.tree().traverse():
            if item.type == 'blob':
                file_path = Path(item.path)
                if self._should_process_file(file_path):
                    files.append(file_path)
        
        return files
