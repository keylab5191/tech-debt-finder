from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List, Dict, Set
import json

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Manage WebSocket connections for real-time updates."""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.scan_subscriptions: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        
        # Remove from all scan subscriptions
        for scan_id, connections in self.scan_subscriptions.items():
            connections.discard(websocket)
    
    def subscribe_to_scan(self, websocket: WebSocket, scan_id: str):
        """Subscribe a connection to scan updates."""
        if scan_id not in self.scan_subscriptions:
            self.scan_subscriptions[scan_id] = set()
        self.scan_subscriptions[scan_id].add(websocket)
    
    def unsubscribe_from_scan(self, websocket: WebSocket, scan_id: str):
        """Unsubscribe a connection from scan updates."""
        if scan_id in self.scan_subscriptions:
            self.scan_subscriptions[scan_id].discard(websocket)
    
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send a message to a specific client."""
        try:
            await websocket.send_json(message)
        except Exception:
            # Client disconnected
            self.disconnect(websocket)
    
    async def broadcast(self, message: dict):
        """Broadcast a message to all connected clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)
    
    async def broadcast_to_scan(self, scan_id: str, message: dict):
        """Broadcast a message to all clients subscribed to a scan."""
        if scan_id not in self.scan_subscriptions:
            return
        
        disconnected = []
        for connection in self.scan_subscriptions[scan_id]:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)
    
    # Specific message types for scan updates
    async def broadcast_scan_update(self, scan_id: str, status: str):
        """Broadcast scan status update."""
        await self.broadcast({
            "type": "scan_update",
            "scan_id": scan_id,
            "status": status
        })
    
    async def broadcast_scan_progress(self, scan_id: str, files_scanned: int, total_files: int):
        """Broadcast scan progress update."""
        progress = (files_scanned / total_files * 100) if total_files > 0 else 0
        await self.broadcast_to_scan(scan_id, {
            "type": "scan_progress",
            "scan_id": scan_id,
            "files_scanned": files_scanned,
            "total_files": total_files,
            "progress_percent": round(progress, 1)
        })
        
        # Also broadcast to all clients
        await self.broadcast({
            "type": "scan_progress",
            "scan_id": scan_id,
            "files_scanned": files_scanned,
            "total_files": total_files,
            "progress_percent": round(progress, 1)
        })
    
    async def broadcast_scan_completed(self, scan_id: str, total_issues: int):
        """Broadcast scan completion."""
        message = {
            "type": "scan_completed",
            "scan_id": scan_id,
            "total_issues": total_issues
        }
        await self.broadcast_to_scan(scan_id, message)
        await self.broadcast(message)
    
    async def broadcast_scan_failed(self, scan_id: str, error: str):
        """Broadcast scan failure."""
        message = {
            "type": "scan_failed",
            "scan_id": scan_id,
            "error": error
        }
        await self.broadcast_to_scan(scan_id, message)
        await self.broadcast(message)
    
    async def broadcast_scan_deleted(self, scan_id: str):
        """Broadcast scan deletion."""
        await self.broadcast({
            "type": "scan_deleted",
            "scan_id": scan_id
        })
    
    async def broadcast_new_issue(self, scan_id: str, issue_id: str):
        """Broadcast new issue found."""
        message = {
            "type": "new_issue",
            "scan_id": scan_id,
            "issue_id": issue_id
        }
        await self.broadcast_to_scan(scan_id, message)
        await self.broadcast(message)
    
    async def broadcast_issue_updated(self, scan_id: str, issue_id: str):
        """Broadcast issue update."""
        message = {
            "type": "issue_updated",
            "scan_id": scan_id,
            "issue_id": issue_id
        }
        await self.broadcast_to_scan(scan_id, message)
        await self.broadcast(message)


# Global connection manager instance
manager = ConnectionManager()


@router.websocket("/ws/scans")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time scan updates."""
    await manager.connect(websocket)
    
    try:
        # Send initial connection confirmation
        await manager.send_personal_message({
            "type": "connected",
            "message": "WebSocket connection established"
        }, websocket)
        
        while True:
            # Wait for messages from client
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                msg_type = message.get("type")
                
                if msg_type == "subscribe":
                    scan_id = message.get("scan_id")
                    if scan_id:
                        manager.subscribe_to_scan(websocket, scan_id)
                        await manager.send_personal_message({
                            "type": "subscribed",
                            "scan_id": scan_id
                        }, websocket)
                
                elif msg_type == "unsubscribe":
                    scan_id = message.get("scan_id")
                    if scan_id:
                        manager.unsubscribe_from_scan(websocket, scan_id)
                        await manager.send_personal_message({
                            "type": "unsubscribed",
                            "scan_id": scan_id
                        }, websocket)
                
                elif msg_type == "ping":
                    await manager.send_personal_message({
                        "type": "pong"
                    }, websocket)
                
                else:
                    await manager.send_personal_message({
                        "type": "error",
                        "message": f"Unknown message type: {msg_type}"
                    }, websocket)
                    
            except json.JSONDecodeError:
                await manager.send_personal_message({
                    "type": "error",
                    "message": "Invalid JSON"
                }, websocket)
    
    except WebSocketDisconnect:
        manager.disconnect(websocket)
