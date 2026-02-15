#!/usr/bin/env python3
"""Simple startup script for the Tech Debt Finder web interface."""

import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import uvicorn


def main():
    """Run the FastAPI application."""
    print("=" * 60)
    print("Tech Debt Finder - Web Interface")
    print("=" * 60)
    print()
    print("Starting server...")
    print()
    print("API Documentation:")
    print("  Swagger UI: http://localhost:8000/docs")
    print("  ReDoc:      http://localhost:8000/redoc")
    print()
    print("WebSocket Endpoint:")
    print("  ws://localhost:8000/ws/scans")
    print()
    print("Health Check:")
    print("  http://localhost:8000/health")
    print()
    print("=" * 60)
    print()
    
    uvicorn.run(
        "web.backend.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=[str(Path(__file__).parent / "backend")],
    )


if __name__ == "__main__":
    main()
