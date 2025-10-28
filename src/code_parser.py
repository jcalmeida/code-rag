"""Code parsing with tree-sitter for structure-aware chunking."""
import hashlib
import logging
from pathlib import Path
from typing import List, Optional, Tuple
from tree_sitter import Language, Parser, Node
import tree_sitter_c_sharp as tscsharp

from src.config import settings
from src.models import CodeChunk, Language as LangEnum

logger = logging.getLogger(__name__)


class CodeParser:
    """Parse code files and create structure-aware chunks."""
    
    def __init__(self):
        self.parsers = {}
        self._initialize_parsers()
    
    def _initialize_parsers(self):
        """Initialize tree-sitter parsers for supported languages."""
        try:
            # C# parser
            CSHARP_LANGUAGE = Language(tscsharp.language())
            csharp_parser = Parser(CSHARP_LANGUAGE)
            self.parsers[LangEnum.CSHARP] = csharp_parser
            logger.info("Initialized C# parser")
        except Exception as e:
            logger.error(f"Failed to initialize C# parser: {e}")
    
    def parse_file(
        self,
        content: str,
        file_path: Path,
        repo_name: str,
        commit_hash: str,
        language: LangEnum
    ) -> List[CodeChunk]:
        """
        Parse a file and create structure-aware chunks.
        
        For C#, we'll extract:
        - Classes
        - Methods
        - Properties
        - Interfaces
        - Enums
        """
        if language not in self.parsers:
            # Fallback to simple chunking
            return self._simple_chunking(content, file_path, repo_name, commit_hash, language)
        
        parser = self.parsers[language]
        
        try:
            tree = parser.parse(bytes(content, "utf8"))
            root_node = tree.root_node
            
            chunks = []
            
            if language == LangEnum.CSHARP:
                chunks = self._parse_csharp(
                    root_node, content, file_path, repo_name, commit_hash
                )
            
            # If no chunks were extracted, fall back to simple chunking
            if not chunks:
                chunks = self._simple_chunking(
                    content, file_path, repo_name, commit_hash, language
                )
            
            logger.info(f"Parsed {file_path}: {len(chunks)} chunks")
            return chunks
            
        except Exception as e:
            logger.error(f"Error parsing {file_path}: {e}")
            return self._simple_chunking(content, file_path, repo_name, commit_hash, language)
    
    def _parse_csharp(
        self,
        root_node: Node,
        content: str,
        file_path: Path,
        repo_name: str,
        commit_hash: str
    ) -> List[CodeChunk]:
        """Parse C# code and extract meaningful chunks."""
        chunks = []
        lines = content.split('\n')
        
        # Node types we want to extract
        target_types = {
            'class_declaration',
            'interface_declaration',
            'struct_declaration',
            'enum_declaration',
            'method_declaration',
            'constructor_declaration',
            'property_declaration',
            'namespace_declaration'
        }
        
        def traverse(node: Node, parent_context: str = ""):
            """Recursively traverse the AST."""
            if node.type in target_types:
                # Extract the code for this node
                start_line = node.start_point[0]
                end_line = node.end_point[0]
                
                # Get the actual code content
                node_content = '\n'.join(lines[start_line:end_line + 1])
                
                # Skip if too small or too large
                if len(node_content.strip()) < 10:
                    return
                
                # For large nodes, we might want to split them
                if len(node_content) > settings.max_chunk_size * 2:
                    # For large classes/namespaces, process children instead
                    if node.type in ['class_declaration', 'namespace_declaration']:
                        for child in node.children:
                            traverse(child, parent_context)
                        return
                
                # Create chunk
                chunk_id = self._generate_chunk_id(
                    repo_name, str(file_path), start_line, commit_hash
                )
                
                # Extract name if possible
                name = self._extract_name(node, content)
                context = f"{parent_context}.{name}" if parent_context else name
                
                chunk = CodeChunk(
                    id=chunk_id,
                    repo_name=repo_name,
                    file_path=str(file_path),
                    language=LangEnum.CSHARP,
                    content=node_content,
                    start_line=start_line + 1,  # 1-indexed
                    end_line=end_line + 1,
                    commit_hash=commit_hash,
                    chunk_type=node.type,
                    metadata={
                        "name": name,
                        "context": context,
                        "byte_size": len(node_content)
                    }
                )
                chunks.append(chunk)
                
                # Don't traverse children of methods/properties (they're complete units)
                if node.type in ['method_declaration', 'property_declaration', 'constructor_declaration']:
                    return
            
            # Continue traversing
            for child in node.children:
                traverse(child, parent_context)
        
        traverse(root_node)
        return chunks
    
    def _extract_name(self, node: Node, content: str) -> str:
        """Extract the name of a declaration node."""
        # Look for identifier child
        for child in node.children:
            if child.type == 'identifier':
                start_byte = child.start_byte
                end_byte = child.end_byte
                return content[start_byte:end_byte]
        return "anonymous"
    
    def _simple_chunking(
        self,
        content: str,
        file_path: Path,
        repo_name: str,
        commit_hash: str,
        language: LangEnum
    ) -> List[CodeChunk]:
        """
        Fallback: Simple sliding window chunking with overlap.
        Used when tree-sitter parsing fails or language not supported.
        """
        chunks = []
        lines = content.split('\n')
        
        chunk_size = settings.max_chunk_size
        overlap = settings.chunk_overlap
        
        current_chunk = []
        current_size = 0
        start_line = 0
        
        for i, line in enumerate(lines):
            line_size = len(line) + 1  # +1 for newline
            
            if current_size + line_size > chunk_size and current_chunk:
                # Create chunk
                chunk_content = '\n'.join(current_chunk)
                chunk_id = self._generate_chunk_id(
                    repo_name, str(file_path), start_line, commit_hash
                )
                
                chunk = CodeChunk(
                    id=chunk_id,
                    repo_name=repo_name,
                    file_path=str(file_path),
                    language=language,
                    content=chunk_content,
                    start_line=start_line + 1,
                    end_line=i,
                    commit_hash=commit_hash,
                    chunk_type="simple_chunk",
                    metadata={"byte_size": len(chunk_content)}
                )
                chunks.append(chunk)
                
                # Calculate overlap
                overlap_lines = []
                overlap_size = 0
                for j in range(len(current_chunk) - 1, -1, -1):
                    line_len = len(current_chunk[j]) + 1
                    if overlap_size + line_len <= overlap:
                        overlap_lines.insert(0, current_chunk[j])
                        overlap_size += line_len
                    else:
                        break
                
                current_chunk = overlap_lines
                current_size = overlap_size
                start_line = i - len(overlap_lines)
            
            current_chunk.append(line)
            current_size += line_size
        
        # Add remaining chunk
        if current_chunk:
            chunk_content = '\n'.join(current_chunk)
            chunk_id = self._generate_chunk_id(
                repo_name, str(file_path), start_line, commit_hash
            )
            
            chunk = CodeChunk(
                id=chunk_id,
                repo_name=repo_name,
                file_path=str(file_path),
                language=language,
                content=chunk_content,
                start_line=start_line + 1,
                end_line=len(lines),
                commit_hash=commit_hash,
                chunk_type="simple_chunk",
                metadata={"byte_size": len(chunk_content)}
            )
            chunks.append(chunk)
        
        return chunks
    
    def _generate_chunk_id(
        self,
        repo_name: str,
        file_path: str,
        start_line: int,
        commit_hash: str
    ) -> str:
        """Generate a unique ID for a chunk."""
        content = f"{repo_name}:{file_path}:{start_line}:{commit_hash}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
