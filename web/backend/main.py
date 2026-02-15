from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from web.backend.database import engine, Base
from web.backend.api import scans, issues, websocket


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Tech Debt Finder",
        description="API for analyzing and tracking technical debt in codebases",
        version="1.0.0"
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include API routers
    app.include_router(scans.router, prefix="/api")
    app.include_router(issues.router, prefix="/api")
    app.include_router(websocket.router)
    
    # Get the frontend directories
    frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
    static_dir = os.path.join(frontend_dir, "static")
    templates_dir = os.path.join(frontend_dir, "templates")
    
    # Mount static files if the directory exists
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")
    
    @app.on_event("startup")
    async def startup_event():
        """Create database tables on startup."""
        Base.metadata.create_all(bind=engine)
    
    @app.get("/")
    async def root():
        """Serve the main index.html or API info."""
        index_path = os.path.join(templates_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        
        return {
            "name": "Tech Debt Finder API",
            "version": "1.0.0",
            "documentation": "/docs",
            "endpoints": {
                "scans": "/api/scans",
                "issues": "/api/issues",
                "websocket": "/ws/scans"
            }
        }
    
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy"}
    
    return app


# Create the application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
