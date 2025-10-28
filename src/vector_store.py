"""Vector store management with ChromaDB and OpenAI embeddings."""
import logging
from typing import List, Optional, Dict, Any
import chromadb
from chromadb.config import Settings as ChromaSettings
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings
from src.models import CodeChunk, SearchResult

logger = logging.getLogger(__name__)


class VectorStore:
    """Manages vector embeddings and similarity search with ChromaDB."""
    
    def __init__(self):
        self.client = chromadb.Client(
            ChromaSettings(
                persist_directory=str(settings.chroma_persist_directory),
                anonymized_telemetry=False
            )
        )
        self.openai_client = OpenAI(api_key=settings.openai_api_key)
        self.collection = self._get_or_create_collection()
    
    def _get_or_create_collection(self):
        """Get or create the main collection for code chunks."""
        collection_name = "code_chunks"
        
        try:
            collection = self.client.get_collection(name=collection_name)
            logger.info(f"Loaded existing collection: {collection_name}")
        except Exception:
            collection = self.client.create_collection(
                name=collection_name,
                metadata={"description": "Code chunks with embeddings"}
            )
            logger.info(f"Created new collection: {collection_name}")
        
        return collection
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def _get_embedding(self, text: str) -> List[float]:
        """Get embedding from OpenAI with retry logic."""
        try:
            response = self.openai_client.embeddings.create(
                model=settings.embedding_model,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error getting embedding: {e}")
            raise
    
    def _prepare_chunk_text(self, chunk: CodeChunk) -> str:
        """
        Prepare chunk text for embedding.
        Include context and metadata to improve search quality.
        """
        parts = [
            f"Repository: {chunk.repo_name}",
            f"File: {chunk.file_path}",
            f"Language: {chunk.language.value}",
            f"Type: {chunk.chunk_type}",
        ]
        
        if "name" in chunk.metadata:
            parts.append(f"Name: {chunk.metadata['name']}")
        
        if "context" in chunk.metadata:
            parts.append(f"Context: {chunk.metadata['context']}")
        
        parts.append(f"\nCode:\n{chunk.content}")
        
        return "\n".join(parts)
    
    def add_chunks(self, chunks: List[CodeChunk]) -> int:
        """
        Add code chunks to the vector store.
        Returns the number of chunks successfully added.
        """
        if not chunks:
            return 0
        
        logger.info(f"Adding {len(chunks)} chunks to vector store...")
        
        # Prepare data for ChromaDB
        ids = []
        embeddings = []
        documents = []
        metadatas = []
        
        for chunk in chunks:
            try:
                # Prepare text for embedding
                text = self._prepare_chunk_text(chunk)
                
                # Get embedding
                embedding = self._get_embedding(text)
                
                # Prepare metadata (ChromaDB requires flat dict)
                metadata = {
                    "repo_name": chunk.repo_name,
                    "file_path": chunk.file_path,
                    "language": chunk.language.value,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "commit_hash": chunk.commit_hash,
                    "chunk_type": chunk.chunk_type,
                    "created_at": chunk.created_at.isoformat(),
                }
                
                # Add custom metadata fields
                if "name" in chunk.metadata:
                    metadata["name"] = chunk.metadata["name"]
                if "context" in chunk.metadata:
                    metadata["context"] = chunk.metadata["context"]
                
                ids.append(chunk.id)
                embeddings.append(embedding)
                documents.append(chunk.content)
                metadatas.append(metadata)
                
            except Exception as e:
                logger.error(f"Error processing chunk {chunk.id}: {e}")
                continue
        
        if not ids:
            logger.warning("No chunks were successfully processed")
            return 0
        
        # Add to ChromaDB
        try:
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )
            logger.info(f"Successfully added {len(ids)} chunks to vector store")
            return len(ids)
        except Exception as e:
            logger.error(f"Error adding chunks to ChromaDB: {e}")
            return 0
    
    def search(
        self,
        query: str,
        top_k: int = 10,
        repo_names: Optional[List[str]] = None,
        languages: Optional[List[str]] = None
    ) -> List[SearchResult]:
        """
        Search for similar code chunks.
        
        Args:
            query: Natural language or code search query
            top_k: Number of results to return
            repo_names: Filter by repository names
            languages: Filter by programming languages
        
        Returns:
            List of SearchResult objects with chunks and similarity scores
        """
        logger.info(f"Searching for: {query}")
        
        # Get query embedding
        try:
            query_embedding = self._get_embedding(query)
        except Exception as e:
            logger.error(f"Error getting query embedding: {e}")
            return []
        
        # Build where filter
        where_filter = None
        if repo_names or languages:
            where_filter = {}
            
            if repo_names and languages:
                where_filter = {
                    "$and": [
                        {"repo_name": {"$in": repo_names}},
                        {"language": {"$in": languages}}
                    ]
                }
            elif repo_names:
                where_filter = {"repo_name": {"$in": repo_names}}
            elif languages:
                where_filter = {"language": {"$in": languages}}
        
        # Query ChromaDB
        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where_filter
            )
            
            # Parse results
            search_results = []
            
            if results['ids'] and results['ids'][0]:
                for i, chunk_id in enumerate(results['ids'][0]):
                    metadata = results['metadatas'][0][i]
                    document = results['documents'][0][i]
                    distance = results['distances'][0][i]
                    
                    # Convert distance to similarity score (0-1)
                    # ChromaDB uses L2 distance, convert to similarity
                    similarity = 1 / (1 + distance)
                    
                    # Reconstruct CodeChunk
                    chunk = CodeChunk(
                        id=chunk_id,
                        repo_name=metadata['repo_name'],
                        file_path=metadata['file_path'],
                        language=metadata['language'],
                        content=document,
                        start_line=metadata['start_line'],
                        end_line=metadata['end_line'],
                        commit_hash=metadata['commit_hash'],
                        chunk_type=metadata['chunk_type'],
                        metadata={
                            k: v for k, v in metadata.items()
                            if k not in ['repo_name', 'file_path', 'language', 
                                       'start_line', 'end_line', 'commit_hash', 
                                       'chunk_type', 'created_at']
                        }
                    )
                    
                    search_results.append(
                        SearchResult(chunk=chunk, score=similarity)
                    )
            
            logger.info(f"Found {len(search_results)} results")
            return search_results
            
        except Exception as e:
            logger.error(f"Error searching vector store: {e}")
            return []
    
    def delete_chunks_by_file(self, repo_name: str, file_path: str) -> int:
        """
        Delete all chunks for a specific file.
        Used when a file is deleted or needs to be reprocessed.
        
        Returns the number of chunks deleted.
        """
        try:
            # Query for chunks matching the file
            results = self.collection.get(
                where={
                    "$and": [
                        {"repo_name": repo_name},
                        {"file_path": file_path}
                    ]
                }
            )
            
            if results['ids']:
                self.collection.delete(ids=results['ids'])
                logger.info(f"Deleted {len(results['ids'])} chunks for {file_path}")
                return len(results['ids'])
            
            return 0
        except Exception as e:
            logger.error(f"Error deleting chunks for {file_path}: {e}")
            return 0
    
    def delete_chunks_by_repo(self, repo_name: str) -> int:
        """
        Delete all chunks for a repository.
        
        Returns the number of chunks deleted.
        """
        try:
            results = self.collection.get(
                where={"repo_name": repo_name}
            )
            
            if results['ids']:
                self.collection.delete(ids=results['ids'])
                logger.info(f"Deleted {len(results['ids'])} chunks for repo {repo_name}")
                return len(results['ids'])
            
            return 0
        except Exception as e:
            logger.error(f"Error deleting chunks for repo {repo_name}: {e}")
            return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the vector store."""
        try:
            count = self.collection.count()
            return {
                "total_chunks": count,
                "collection_name": self.collection.name
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {"total_chunks": 0, "error": str(e)}
