"""Tests for code parser."""
import pytest
from pathlib import Path
from src.code_parser import CodeParser
from src.models import Language


@pytest.fixture
def parser():
    return CodeParser()


def test_csharp_class_parsing(parser):
    """Test parsing a simple C# class."""
    code = """
using System;

namespace MyApp
{
    public class Calculator
    {
        public int Add(int a, int b)
        {
            return a + b;
        }
        
        public int Subtract(int a, int b)
        {
            return a - b;
        }
    }
}
"""
    
    chunks = parser.parse_file(
        content=code,
        file_path=Path("Calculator.cs"),
        repo_name="test-repo",
        commit_hash="abc123",
        language=Language.CSHARP
    )
    
    assert len(chunks) > 0
    # Should extract namespace, class, and methods
    chunk_types = [chunk.chunk_type for chunk in chunks]
    assert any('class' in ct or 'method' in ct for ct in chunk_types)


def test_simple_chunking_fallback(parser):
    """Test fallback to simple chunking."""
    code = "x" * 2000  # Long code without structure
    
    chunks = parser.parse_file(
        content=code,
        file_path=Path("test.cs"),
        repo_name="test-repo",
        commit_hash="abc123",
        language=Language.CSHARP
    )
    
    assert len(chunks) > 0
    # Should create multiple chunks due to size
    assert all(chunk.chunk_type == "simple_chunk" for chunk in chunks)


def test_chunk_id_generation(parser):
    """Test that chunk IDs are unique and consistent."""
    code = "public class Test { }"
    
    chunks1 = parser.parse_file(
        content=code,
        file_path=Path("Test.cs"),
        repo_name="repo1",
        commit_hash="abc123",
        language=Language.CSHARP
    )
    
    chunks2 = parser.parse_file(
        content=code,
        file_path=Path("Test.cs"),
        repo_name="repo1",
        commit_hash="abc123",
        language=Language.CSHARP
    )
    
    # Same input should generate same IDs
    assert chunks1[0].id == chunks2[0].id
    
    # Different repo should generate different IDs
    chunks3 = parser.parse_file(
        content=code,
        file_path=Path("Test.cs"),
        repo_name="repo2",
        commit_hash="abc123",
        language=Language.CSHARP
    )
    
    assert chunks1[0].id != chunks3[0].id
