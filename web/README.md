# Tech Debt Finder - Web Interface

A modern web interface for the Tech Debt Finder tool, providing a dashboard for scanning codebases, viewing issues, and managing technical debt.

## Features

- 🔍 **Scan Management**: Create and monitor code scans in real-time
- 📊 **Dashboard**: View scan statistics and issue summaries
- 🐛 **Issue Tracking**: Browse, filter, and manage technical debt issues
- 🔔 **Real-time Updates**: WebSocket-powered live progress updates
- 📁 **Report Sync**: Import existing JSON reports into the database
- 🎨 **Modern UI**: Clean, responsive web interface

## Prerequisites

- Python 3.9+
- Ollama running locally (for AI-powered code analysis)
- A code model pulled in Ollama (default: `qwen2.5-coder:7b`)

## Installation

### 1. Clone and Setup

```bash
# Navigate to the project directory
cd tech-debt-finder

# Install all dependencies (CLI + Web)
pip install -r requirements.txt

# Or install web dependencies only
pip install -r web/requirements-web.txt
```

### 2. Configure Ollama

Make sure Ollama is running and the model is available:

```bash
# Start Ollama
ollama serve

# Pull the default model (if not already available)
ollama pull qwen2.5-coder:7b
```

### 3. Initialize Database

The database will be automatically created on first startup at `web/tech_debt.db`.

## Running the Web Interface

### Option 1: Using the startup script

```bash
python web/run.py
```

### Option 2: Using uvicorn directly

```bash
uvicorn web.backend.main:app --reload --host 127.0.0.1 --port 8000
```

### Option 3: From the project root

```bash
cd web
python -m uvicorn backend.main:app --reload
```

## Accessing the Application

Once running, access the web interface at:

- **Web Interface**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Alternative API Docs**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

## API Endpoints

### Scans

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/scans` | Create a new scan |
| `GET` | `/api/scans` | List all scans |
| `GET` | `/api/scans/active` | Get running scans |
| `GET` | `/api/scans/{id}` | Get scan details |
| `DELETE` | `/api/scans/{id}` | Delete a scan |

### Issues

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/issues` | List all issues |
| `GET` | `/api/issues?scan_id={id}` | List issues for a scan |
| `GET` | `/api/issues/{id}` | Get issue details |
| `PATCH` | `/api/issues/{id}` | Update issue status |
| `DELETE` | `/api/issues/{id}` | Delete an issue |

### WebSocket

Connect to `ws://localhost:8000/ws/scans` for real-time updates.

## WebSocket Events

### Client → Server Messages

```json
// Subscribe to scan updates
{
  "type": "subscribe",
  "scan_id": "uuid-of-scan"
}

// Unsubscribe from scan updates
{
  "type": "unsubscribe",
  "scan_id": "uuid-of-scan"
}

// Ping to keep connection alive
{
  "type": "ping"
}
```

### Server → Client Messages

```json
// Connection confirmed
{
  "type": "connected",
  "message": "WebSocket connection established"
}

// Scan status update
{
  "type": "scan_update",
  "scan_id": "uuid-of-scan",
  "status": "running"
}

// Scan progress update
{
  "type": "scan_progress",
  "scan_id": "uuid-of-scan",
  "files_scanned": 42,
  "total_files": 100,
  "progress_percent": 42.0
}

// New issue found
{
  "type": "new_issue",
  "scan_id": "uuid-of-scan",
  "issue_id": "uuid-of-issue"
}

// Scan completed
{
  "type": "scan_completed",
  "scan_id": "uuid-of-scan",
  "total_issues": 15
}

// Scan failed
{
  "type": "scan_failed",
  "scan_id": "uuid-of-scan",
  "error": "Error message"
}

// Issue updated
{
  "type": "issue_updated",
  "scan_id": "uuid-of-scan",
  "issue_id": "uuid-of-issue"
}
```

## Creating a New Scan

### Using curl

```bash
curl -X POST http://localhost:8000/api/scans \
  -H "Content-Type: application/json" \
  -d '{
    "target_directory": "/path/to/your/code",
    "model": "qwen2.5-coder:7b",
    "config": {
      "extensions": [".py", ".js", ".ts"],
      "max_file_size_kb": 100
    }
  }'
```

### Using Python

```python
import httpx

response = httpx.post("http://localhost:8000/api/scans", json={
    "target_directory": "/path/to/your/code",
    "model": "qwen2.5-coder:7b",
    "config": {
        "extensions": [".py", ".js", ".ts"],
        "max_file_size_kb": 100
    }
})

scan = response.json()
print(f"Scan created: {scan['id']}")
```

## Importing Existing Reports

If you have existing JSON reports from the CLI, you can import them:

```python
from web.backend.database import SessionLocal
from web.backend.services import sync_json_report

# Create a database session
db = SessionLocal()

try:
    # Import the report
    stats = sync_json_report("path/to/tech_debt_report.json", db)
    print(f"Created {stats['scans_created']} scan(s)")
    print(f"Created {stats['issues_created']} issue(s)")
    print(f"Processed {stats['files_processed']} file(s)")
finally:
    db.close()
```

## Project Structure

```
web/
├── backend/
│   ├── api/
│   │   ├── scans.py          # Scan REST API endpoints
│   │   ├── issues.py         # Issue REST API endpoints
│   │   └── websocket.py      # WebSocket connection handler
│   ├── models/
│   │   ├── scan.py           # Scan database model
│   │   └── issue.py          # Issue database model
│   ├── schemas/
│   │   ├── scan.py           # Scan Pydantic schemas
│   │   └── issue.py          # Issue Pydantic schemas
│   ├── services/
│   │   ├── scan_manager.py   # Background scan runner
│   │   └── sync_service.py   # JSON report importer
│   ├── database.py           # SQLAlchemy configuration
│   └── main.py               # FastAPI application
├── run.py                    # Startup script
└── README.md                 # This file
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API endpoint |
| `DATABASE_URL` | `sqlite:///web/tech_debt.db` | Database connection string |

## Troubleshooting

### Ollama Connection Issues

If you see "Cannot connect to Ollama" errors:

1. Verify Ollama is running: `ollama serve`
2. Check the URL is correct (default: http://localhost:11434)
3. Test with: `curl http://localhost:11434/api/tags`

### Database Issues

If you encounter database errors:

1. Check file permissions for `web/tech_debt.db`
2. Delete the database file to start fresh (will be recreated)
3. Verify SQLite is installed: `python -c "import sqlite3; print(sqlite3.version)"`

### Port Already in Use

If port 8000 is taken:

```bash
# Use a different port
python web/run.py --port 8080

# Or with uvicorn
uvicorn web.backend.main:app --port 8080
```

## Development

### Adding New API Endpoints

1. Add routes to `web/backend/api/` modules
2. Update schemas in `web/backend/schemas/` if needed
3. Add WebSocket events to `websocket.py` for real-time updates

### Database Migrations

The application uses SQLAlchemy's auto-create on startup. For production, consider using Alembic for migrations.

## License

Same as the main Tech Debt Finder project.
