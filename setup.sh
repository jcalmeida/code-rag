#!/bin/bash
# Setup script for Code RAG System

set -e

echo "🚀 Setting up Code RAG System..."

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python version: $python_version"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
else
    echo "✓ Virtual environment already exists"
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "📚 Installing dependencies..."
pip install -r requirements.txt

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p data/repos
mkdir -p data/chroma
mkdir -p config

# Copy .env.example if .env doesn't exist
if [ ! -f ".env" ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env and add your API keys!"
else
    echo "✓ .env file already exists"
fi

# Copy repos.json example if it doesn't exist
if [ ! -f "config/repos.json" ]; then
    echo "📝 repos.json already exists in config/"
else
    echo "✓ config/repos.json already exists"
fi

# Make CLI executable
chmod +x cli.py

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env and add your OPENAI_API_KEY and GIT_TOKEN"
echo "2. Edit config/repos.json to add your repositories"
echo "3. Run: source venv/bin/activate"
echo "4. Run: python cli.py ingest"
echo "5. Run: python cli.py search 'your query'"
echo ""
echo "Or start the API server:"
echo "  python -m uvicorn src.api:app --reload"
echo ""
