// Tech Debt Dashboard - WebSocket Client

/**
 * WebSocket Manager
 * Handles real-time connection to the server for scan updates
 */
(function() {
    'use strict';
    
    // WebSocket configuration
    const WS_CONFIG = {
        url: 'ws://localhost:8000/ws/scans',
        reconnectInterval: 3000,
        maxReconnectAttempts: 10,
        heartbeatInterval: 30000
    };
    
    /**
     * WebSocket Client Class
     */
    class WebSocketClient {
        constructor() {
            this.ws = null;
            this.reconnectAttempts = 0;
            this.reconnectTimer = null;
            this.heartbeatTimer = null;
            this.messageHandlers = [];
            this.connectionState = 'disconnected'; // 'disconnected', 'connecting', 'connected', 'reconnecting'
            this.lastMessageTime = null;
        }
        
        /**
         * Connect to WebSocket server
         */
        connect() {
            if (this.connectionState === 'connected' || this.connectionState === 'connecting') {
                console.log('WebSocket already connected or connecting');
                return;
            }
            
            this.connectionState = 'connecting';
            console.log('Connecting to WebSocket:', WS_CONFIG.url);
            
            try {
                this.ws = new WebSocket(WS_CONFIG.url);
                
                this.ws.onopen = (event) => {
                    this.handleOpen(event);
                };
                
                this.ws.onmessage = (event) => {
                    this.handleMessage(event);
                };
                
                this.ws.onclose = (event) => {
                    this.handleClose(event);
                };
                
                this.ws.onerror = (error) => {
                    this.handleError(error);
                };
                
            } catch (error) {
                console.error('Failed to create WebSocket connection:', error);
                this.scheduleReconnect();
            }
        }
        
        /**
         * Handle connection open
         */
        handleOpen(event) {
            console.log('WebSocket connected successfully');
            this.connectionState = 'connected';
            this.reconnectAttempts = 0;
            this.lastMessageTime = Date.now();
            
            // Start heartbeat
            this.startHeartbeat();
            
            // Notify handlers
            this.notifyHandlers({
                type: 'connection',
                status: 'connected'
            });
        }
        
        /**
         * Handle incoming messages
         */
        handleMessage(event) {
            this.lastMessageTime = Date.now();
            
            try {
                const message = JSON.parse(event.data);
                console.log('WebSocket message received:', message);
                
                // Validate message structure
                if (!message.type) {
                    console.warn('Received message without type:', message);
                    return;
                }
                
                // Notify all registered handlers
                this.notifyHandlers(message);
                
            } catch (error) {
                console.error('Failed to parse WebSocket message:', error);
                console.debug('Raw message:', event.data);
            }
        }
        
        /**
         * Handle connection close
         */
        handleClose(event) {
            console.log('WebSocket closed:', event.code, event.reason);
            this.connectionState = 'disconnected';
            this.stopHeartbeat();
            
            // Notify handlers
            this.notifyHandlers({
                type: 'connection',
                status: 'disconnected',
                code: event.code,
                reason: event.reason
            });
            
            // Attempt to reconnect if not a clean close
            if (!event.wasClean) {
                this.scheduleReconnect();
            }
        }
        
        /**
         * Handle connection error
         */
        handleError(error) {
            console.error('WebSocket error:', error);
            this.notifyHandlers({
                type: 'connection',
                status: 'error',
                error: error
            });
        }
        
        /**
         * Schedule reconnection attempt
         */
        scheduleReconnect() {
            if (this.reconnectAttempts >= WS_CONFIG.maxReconnectAttempts) {
                console.error('Max reconnection attempts reached');
                this.notifyHandlers({
                    type: 'connection',
                    status: 'failed',
                    message: 'Max reconnection attempts reached'
                });
                return;
            }
            
            this.connectionState = 'reconnecting';
            this.reconnectAttempts++;
            
            const delay = Math.min(
                WS_CONFIG.reconnectInterval * Math.pow(1.5, this.reconnectAttempts - 1),
                30000 // Max 30 seconds
            );
            
            console.log(`Scheduling reconnect attempt ${this.reconnectAttempts}/${WS_CONFIG.maxReconnectAttempts} in ${delay}ms`);
            
            this.notifyHandlers({
                type: 'connection',
                status: 'reconnecting',
                attempt: this.reconnectAttempts,
                maxAttempts: WS_CONFIG.maxReconnectAttempts,
                delay: delay
            });
            
            this.reconnectTimer = setTimeout(() => {
                this.connect();
            }, delay);
        }
        
        /**
         * Start heartbeat to keep connection alive
         */
        startHeartbeat() {
            this.heartbeatTimer = setInterval(() => {
                if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                    // Send ping
                    this.send({ type: 'ping' });
                    
                    // Check if we've received messages recently
                    const timeSinceLastMessage = Date.now() - this.lastMessageTime;
                    if (timeSinceLastMessage > WS_CONFIG.heartbeatInterval * 2) {
                        console.warn('No messages received for a while, connection may be stale');
                        // Force reconnection
                        this.ws.close();
                    }
                }
            }, WS_CONFIG.heartbeatInterval);
        }
        
        /**
         * Stop heartbeat
         */
        stopHeartbeat() {
            if (this.heartbeatTimer) {
                clearInterval(this.heartbeatTimer);
                this.heartbeatTimer = null;
            }
        }
        
        /**
         * Send message to server
         */
        send(message) {
            if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
                console.error('Cannot send message, WebSocket is not open');
                return false;
            }
            
            try {
                const messageStr = typeof message === 'string' ? message : JSON.stringify(message);
                this.ws.send(messageStr);
                return true;
            } catch (error) {
                console.error('Failed to send message:', error);
                return false;
            }
        }
        
        /**
         * Register a message handler
         */
        onMessage(handler) {
            if (typeof handler !== 'function') {
                console.error('Message handler must be a function');
                return;
            }
            this.messageHandlers.push(handler);
        }
        
        /**
         * Remove a message handler
         */
        offMessage(handler) {
            const index = this.messageHandlers.indexOf(handler);
            if (index > -1) {
                this.messageHandlers.splice(index, 1);
            }
        }
        
        /**
         * Notify all registered handlers
         */
        notifyHandlers(message) {
            this.messageHandlers.forEach(handler => {
                try {
                    handler(message);
                } catch (error) {
                    console.error('Error in message handler:', error);
                }
            });
        }
        
        /**
         * Disconnect from WebSocket
         */
        disconnect() {
            console.log('Disconnecting WebSocket...');
            
            // Clear any pending reconnect
            if (this.reconnectTimer) {
                clearTimeout(this.reconnectTimer);
                this.reconnectTimer = null;
            }
            
            this.stopHeartbeat();
            
            // Close connection if open
            if (this.ws) {
                this.ws.close(1000, 'Client disconnected');
                this.ws = null;
            }
            
            this.connectionState = 'disconnected';
            this.reconnectAttempts = 0;
        }
        
        /**
         * Check if connected
         */
        isConnected() {
            return this.ws && this.ws.readyState === WebSocket.OPEN;
        }
        
        /**
         * Get connection state
         */
        getState() {
            return this.connectionState;
        }
    }
    
    // Create global WebSocket client instance
    const wsClient = new WebSocketClient();
    
    /**
     * Initialize WebSocket connection
     * @param {Function} messageHandler - Optional handler for messages
     * @returns {WebSocketClient} The WebSocket client instance
     */
    window.initWebSocket = function(messageHandler) {
        // Register handler if provided
        if (messageHandler) {
            wsClient.onMessage(messageHandler);
        }
        
        // Connect if not already connected
        if (!wsClient.isConnected() && wsClient.getState() !== 'connecting') {
            wsClient.connect();
        }
        
        return wsClient;
    };
    
    /**
     * Get the global WebSocket client
     */
    window.getWebSocketClient = function() {
        return wsClient;
    };
    
    /**
     * Message Type Handlers
     * Predefined handlers for common message types
     */
    window.WebSocketMessageTypes = {
        // Scan progress update
        PROGRESS: 'progress',
        
        // New issue discovered
        NEW_ISSUE: 'new_issue',
        
        // Scan completed
        SCAN_COMPLETE: 'scan_complete',
        
        // Scan error
        SCAN_ERROR: 'scan_error',
        
        // Connection status
        CONNECTION: 'connection',
        
        // Heartbeat ping/pong
        PING: 'ping',
        PONG: 'pong'
    };
    
    /**
     * Message Handlers
     * Specific handlers for each message type
     */
    const MessageHandlers = {
        /**
         * Handle progress updates
         */
        handleProgress(message) {
            // Update scan progress UI
            if (window.dispatchEvent) {
                window.dispatchEvent(new CustomEvent('scan-progress', {
                    detail: message
                }));
            }
        },
        
        /**
         * Handle new issues
         */
        handleNewIssue(message) {
            // Add new issue to the board
            if (window.dispatchEvent) {
                window.dispatchEvent(new CustomEvent('new-issue-found', {
                    detail: message
                }));
            }
        },
        
        /**
         * Handle scan completion
         */
        handleScanComplete(message) {
            // Refresh the issues list
            if (window.dispatchEvent) {
                window.dispatchEvent(new CustomEvent('scan-complete', {
                    detail: message
                }));
            }
        },
        
        /**
         * Handle scan errors
         */
        handleScanError(message) {
            // Show error notification
            if (window.dispatchEvent) {
                window.dispatchEvent(new CustomEvent('scan-error', {
                    detail: message
                }));
            }
        },
        
        /**
         * Handle connection status changes
         */
        handleConnection(message) {
            // Update connection status indicator
            if (window.dispatchEvent) {
                window.dispatchEvent(new CustomEvent('ws-connection-status', {
                    detail: message
                }));
            }
        }
    };
    
    // Register default message handlers
    wsClient.onMessage((message) => {
        switch (message.type) {
            case 'progress':
                MessageHandlers.handleProgress(message);
                break;
            case 'new_issue':
                MessageHandlers.handleNewIssue(message);
                break;
            case 'scan_complete':
                MessageHandlers.handleScanComplete(message);
                break;
            case 'scan_error':
                MessageHandlers.handleScanError(message);
                break;
            case 'connection':
            case 'ping':
            case 'pong':
                MessageHandlers.handleConnection(message);
                break;
            default:
                // Unknown message type - can be handled by custom handlers
                break;
        }
    });
    
    // Cleanup on page unload
    window.addEventListener('beforeunload', () => {
        wsClient.disconnect();
    });
    
    // Auto-connect when DOM is ready
    document.addEventListener('DOMContentLoaded', () => {
        // Only auto-connect if not already connected
        if (!wsClient.isConnected()) {
            console.log('Auto-connecting WebSocket...');
            wsClient.connect();
        }
    });
    
    // Handle visibility change - reconnect when tab becomes visible
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden && !wsClient.isConnected() && wsClient.getState() !== 'connecting') {
            console.log('Tab visible, reconnecting WebSocket...');
            wsClient.connect();
        }
    });
    
})();
