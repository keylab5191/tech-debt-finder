// Tech Debt Dashboard - Main Alpine.js Application
document.addEventListener('alpine:init', () => {
    Alpine.data('techDebtApp', () => ({
        // State
        issues: [],
        activeScans: [],
        scanning: false,
        viewMode: 'kanban',
        selectedIssue: null,
        showScanModal: false,
        
        // Filters
        filters: {
            search: '',
            severity: '',
            category: '',
            status: ''
        },
        
        // Scan Form
        scanForm: {
            target_directory: '',
            model: 'qwen2.5-coder:3b',
            categories: ['code_smell', 'complexity', 'naming', 'structure', 'duplication', 'error_handling', 'security', 'performance', 'readability', 'best_practices'],
            max_file_size_kb: 100
        },
        
        // Available categories
        availableCategories: [
            { value: 'code_smell', label: 'Code Smell' },
            { value: 'complexity', label: 'Complexity' },
            { value: 'naming', label: 'Naming' },
            { value: 'structure', label: 'Structure' },
            { value: 'duplication', label: 'Duplication' },
            { value: 'error_handling', label: 'Error Handling' },
            { value: 'security', label: 'Security' },
            { value: 'performance', label: 'Performance' },
            { value: 'readability', label: 'Readability' },
            { value: 'best_practices', label: 'Best Practices' }
        ],
        
        // WebSocket instance
        ws: null,
        
        // Base URL for API
        apiUrl: '/api',
        
        /**
         * Initialize the application
         */
        init() {
            console.log('Tech Debt Dashboard initializing...');
            
            // Load initial data
            this.fetchIssues();
            this.fetchActiveScans();
            
            // Connect to WebSocket for real-time updates
            this.connectWebSocket();
            
            // Listen for custom events from other components
            window.addEventListener('issue-moved', (event) => {
                this.handleIssueMoved(event.detail);
            });
        },
        
        /**
         * Fetch issues from the API with current filters
         */
        async fetchIssues() {
            try {
                const params = new URLSearchParams();
                
                if (this.filters.search) {
                    params.append('search', this.filters.search);
                }
                if (this.filters.severity) {
                    params.append('severity', this.filters.severity);
                }
                if (this.filters.category) {
                    params.append('category', this.filters.category);
                }
                if (this.filters.status) {
                    params.append('status', this.filters.status);
                }
                
                const response = await fetch(`${this.apiUrl}/issues?${params}`);
                
                if (!response.ok) {
                    throw new Error(`Failed to fetch issues: ${response.statusText}`);
                }
                
                const data = await response.json();
                this.issues = data.issues || [];
                
                console.log(`Loaded ${this.issues.length} issues`);
            } catch (error) {
                console.error('Error fetching issues:', error);
                // In development/demo mode, use mock data
                this.loadMockData();
            }
        },
        
        /**
         * Fetch active scans
         */
        async fetchActiveScans() {
            try {
                const response = await fetch(`${this.apiUrl}/scans/active`);
                
                if (!response.ok) {
                    throw new Error(`Failed to fetch active scans: ${response.statusText}`);
                }
                
                const data = await response.json();
                this.activeScans = data || [];
                this.scanning = this.activeScans.length > 0;
                
                // Subscribe to each active scan via WebSocket
                if (this.ws && this.ws.isConnected) {
                    this.activeScans.forEach(scan => {
                        this.ws.send({
                            type: 'subscribe',
                            scan_id: scan.id
                        });
                    });
                }
                
            } catch (error) {
                console.error('Error fetching active scans:', error);
                this.activeScans = [];
            }
        },
        
        /**
         * Open the new scan modal
         */
        openScanModal() {
            // Reset form with defaults
            this.scanForm = {
                target_directory: '',
                model: 'qwen2.5-coder:7b',
                categories: ['code_smell', 'complexity', 'naming', 'structure', 'duplication', 'error_handling', 'security', 'performance', 'readability', 'best_practices'],
                max_file_size_kb: 100
            };
            this.showScanModal = true;
        },
        
        /**
         * Submit the new scan form
         */
        async submitNewScan() {
            if (this.scanning || !this.scanForm.target_directory || this.scanForm.categories.length === 0) {
                return;
            }
            
            this.scanning = true;
            
            try {
                const response = await fetch(`${this.apiUrl}/scans`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        target_directory: this.scanForm.target_directory,
                        model: this.scanForm.model,
                        categories: this.scanForm.categories,
                        max_file_size_kb: parseInt(this.scanForm.max_file_size_kb)
                    })
                });
                
                if (!response.ok) {
                    throw new Error(`Failed to create scan: ${response.statusText}`);
                }
                
                const data = await response.json();
                console.log('Scan created:', data);
                
                // Close modal
                this.showScanModal = false;
                
                // Add new scan to active scans list immediately
                this.activeScans.push({
                    id: data.id,
                    target_directory: data.target_directory,
                    files_scanned: 0,
                    total_files: data.total_files || 0,
                    status: data.status
                });
                this.scanning = true;
                
                // Subscribe to new scan via WebSocket
                if (this.ws && this.ws.send) {
                    this.ws.send({
                        type: 'subscribe',
                        scan_id: data.id
                    });
                }
                
                // Refresh active scans after a moment
                setTimeout(() => this.fetchActiveScans(), 500);
                
            } catch (error) {
                console.error('Error creating scan:', error);
                alert('Failed to start scan: ' + error.message);
                this.scanning = false;
            }
        },
        
        /**
         * Create a new scan (legacy method for direct calls)
         */
        async createScan() {
            if (this.scanning) return;
            this.openScanModal();
        },
        
        /**
         * Update issue status
         */
        async updateIssueStatus(issueId, newStatus) {
            try {
                const response = await fetch(`${this.apiUrl}/issues/${issueId}`, {
                    method: 'PATCH',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        status: newStatus,
                        updated_at: new Date().toISOString()
                    })
                });
                
                if (!response.ok) {
                    throw new Error(`Failed to update issue: ${response.statusText}`);
                }
                
                const data = await response.json();
                console.log('Issue updated:', data);
                
                // Update local state
                const issueIndex = this.issues.findIndex(i => i.id === issueId);
                if (issueIndex !== -1) {
                    this.issues[issueIndex].status = newStatus;
                }
                
                // Close modal if open
                if (this.selectedIssue && this.selectedIssue.id === issueId) {
                    this.selectedIssue.status = newStatus;
                }
                
            } catch (error) {
                console.error('Error updating issue:', error);
                // Update local state anyway for demo
                const issueIndex = this.issues.findIndex(i => i.id === issueId);
                if (issueIndex !== -1) {
                    this.issues[issueIndex].status = newStatus;
                }
            }
        },
        
        /**
         * Handle issue moved event from kanban
         */
        handleIssueMoved({ issueId, newStatus }) {
            this.updateIssueStatus(issueId, newStatus);
        },
        
        /**
         * Open issue detail modal
         */
        openIssueModal(issue) {
            this.selectedIssue = { ...issue };
            document.body.style.overflow = 'hidden';
        },
        
        /**
         * Close issue detail modal
         */
        closeModal() {
            this.selectedIssue = null;
            document.body.style.overflow = '';
        },
        
        /**
         * Connect to WebSocket for real-time updates
         */
        connectWebSocket() {
            // WebSocket connection is handled by websocket.js
            if (window.initWebSocket) {
                this.ws = window.initWebSocket(this.handleWebSocketMessage.bind(this));
                
                // After WebSocket connects, subscribe to active scans
                setTimeout(() => {
                    if (this.activeScans.length > 0 && this.ws && this.ws.send) {
                        this.activeScans.forEach(scan => {
                            this.ws.send({
                                type: 'subscribe',
                                scan_id: scan.id
                            });
                        });
                    }
                }, 1000);
            }
        },
        
        /**
         * Handle WebSocket messages
         */
        handleWebSocketMessage(message) {
            console.log('WebSocket message received:', message);
            
            switch (message.type) {
                case 'scan_progress':
                case 'progress':
                    // Update scan progress
                    const scanIndex = this.activeScans.findIndex(s => s.id === message.scan_id);
                    if (scanIndex !== -1) {
                        this.activeScans[scanIndex].files_scanned = message.files_scanned;
                        this.activeScans[scanIndex].total_files = message.total_files;
                    } else {
                        // Scan not in list, refresh active scans
                        this.fetchActiveScans();
                    }
                    break;
                    
                case 'new_issue':
                    // Add new issue to the list
                    this.issues.unshift(message.issue);
                    break;
                    
                case 'scan_complete':
                case 'scan_completed':
                    // Remove completed scan from active list
                    this.activeScans = this.activeScans.filter(s => s.id !== message.scan_id);
                    this.scanning = this.activeScans.length > 0;
                    // Refresh issues list
                    this.fetchIssues();
                    break;
                    
                case 'scan_error':
                case 'scan_failed':
                    console.error('Scan error:', message.error);
                    this.activeScans = this.activeScans.filter(s => s.id !== message.scan_id);
                    this.scanning = false;
                    break;
            }
        },
        
        /**
         * Load mock data for development/demo
         */
        loadMockData() {
            const mockIssues = [
                {
                    id: 'issue-001',
                    title: 'Large function detected in api/routes.py',
                    description: 'Function \`handle_user_request\` has 150 lines which exceeds the recommended 50 lines maximum. Consider breaking it down into smaller functions.',
                    severity: 'high',
                    category: 'maintainability',
                    status: 'open',
                    file: 'api/routes.py',
                    line: 45,
                    code_snippet: 'def handle_user_request(user_id, data):\n    # ... 150 lines ...',
                    tags: ['refactor', 'complexity'],
                    created_at: '2026-02-14T10:30:00Z'
                },
                {
                    id: 'issue-002',
                    title: 'Security vulnerability in user input validation',
                    description: 'SQL injection risk detected in database queries. Use parameterized queries instead of string concatenation.',
                    severity: 'critical',
                    category: 'security',
                    status: 'in_progress',
                    file: 'db/queries.py',
                    line: 23,
                    code_snippet: 'query = f"SELECT * FROM users WHERE id = {user_id}"',
                    tags: ['security', 'sql-injection'],
                    created_at: '2026-02-13T15:20:00Z'
                },
                {
                    id: 'issue-003',
                    title: 'Missing error handling in async operations',
                    description: 'Multiple async functions lack try-catch blocks which could lead to unhandled promise rejections.',
                    severity: 'medium',
                    category: 'code_smell',
                    status: 'open',
                    file: 'services/data.py',
                    line: 89,
                    code_snippet: 'async def fetch_data():\n    data = await api.get()',
                    tags: ['error-handling', 'async'],
                    created_at: '2026-02-12T09:15:00Z'
                },
                {
                    id: 'issue-004',
                    title: 'Duplicate code in authentication modules',
                    description: 'Similar authentication logic found in auth/jwt.py and auth/oauth.py. Consider extracting common logic into a shared utility.',
                    severity: 'low',
                    category: 'code_smell',
                    status: 'resolved',
                    file: 'auth/jwt.py',
                    line: 12,
                    code_snippet: 'def verify_token(token):\n    # ... duplicate logic ...',
                    tags: ['refactor', 'duplication'],
                    created_at: '2026-02-10T14:00:00Z'
                },
                {
                    id: 'issue-005',
                    title: 'Performance bottleneck in data processing',
                    description: 'O(n²) complexity detected in data transformation pipeline. Consider using more efficient algorithms or caching.',
                    severity: 'high',
                    category: 'performance',
                    status: 'in_progress',
                    file: 'processing/transform.py',
                    line: 156,
                    code_snippet: 'for item in items:\n    for other in items:\n        process(item, other)',
                    tags: ['performance', 'optimization'],
                    created_at: '2026-02-11T11:30:00Z'
                },
                {
                    id: 'issue-006',
                    title: 'Inconsistent error response format',
                    description: 'API endpoints return different error formats. Standardize on a consistent error response schema.',
                    severity: 'medium',
                    category: 'architecture',
                    status: 'open',
                    file: 'api/handlers.py',
                    line: 34,
                    code_snippet: 'return {"error": message}  # vs {"error": {"message": msg}}',
                    tags: ['api', 'consistency'],
                    created_at: '2026-02-09T16:45:00Z'
                }
            ];
            
            this.issues = mockIssues;
            console.log('Loaded mock data with', this.issues.length, 'issues');
        },
        
        /**
         * Mock scan for demo purposes
         */
        mockScan() {
            const scanId = 'scan-' + Date.now();
            this.activeScans.push({
                id: scanId,
                path: '.',
                progress: 0
            });
            
            // Simulate progress
            const interval = setInterval(() => {
                const scan = this.activeScans.find(s => s.id === scanId);
                if (scan) {
                    scan.progress += Math.random() * 20;
                    if (scan.progress >= 100) {
                        scan.progress = 100;
                        clearInterval(interval);
                        setTimeout(() => {
                            this.activeScans = this.activeScans.filter(s => s.id !== scanId);
                            this.scanning = false;
                            // Add a mock new issue
                            this.issues.unshift({
                                id: 'issue-' + Date.now(),
                                title: 'New issue found during scan',
                                description: 'Auto-generated issue from scan',
                                severity: ['low', 'medium', 'high'][Math.floor(Math.random() * 3)],
                                category: ['code_smell', 'security', 'performance'][Math.floor(Math.random() * 3)],
                                status: 'open',
                                file: 'src/example.py',
                                line: 1,
                                created_at: new Date().toISOString()
                            });
                        }, 500);
                    }
                }
            }, 500);
        },
        
        /**
         * Calculate elapsed time since scan started
         */
        getElapsedTime(startedAt) {
            if (!startedAt) return '0s';
            const start = new Date(startedAt);
            const now = new Date();
            const diff = Math.floor((now - start) / 1000); // seconds
            
            if (diff < 60) return diff + 's';
            if (diff < 3600) return Math.floor(diff / 60) + 'm ' + (diff % 60) + 's';
            const hours = Math.floor(diff / 3600);
            const mins = Math.floor((diff % 3600) / 60);
            return hours + 'h ' + mins + 'm';
        },
        
        /**
         * Cancel an active scan
         */
        async cancelScan(scanId) {
            if (!confirm('Are you sure you want to cancel this scan?')) return;
            
            try {
                const response = await fetch(`${this.apiUrl}/scans/${scanId}`, {
                    method: 'DELETE'
                });
                
                if (!response.ok) {
                    throw new Error(`Failed to cancel scan: ${response.statusText}`);
                }
                
                // Remove from active scans
                this.activeScans = this.activeScans.filter(s => s.id !== scanId);
                this.scanning = this.activeScans.length > 0;
                
                console.log('Scan cancelled:', scanId);
            } catch (error) {
                console.error('Error cancelling scan:', error);
                alert('Failed to cancel scan: ' + error.message);
            }
        },
        
        /**
         * Computed property: filtered issues based on current filters
         */
        get filteredIssues() {
            return this.issues.filter(issue => {
                // Search filter
                if (this.filters.search) {
                    const searchTerm = this.filters.search.toLowerCase();
                    const matchSearch = issue.title.toLowerCase().includes(searchTerm) ||
                                       issue.description?.toLowerCase().includes(searchTerm) ||
                                       issue.file.toLowerCase().includes(searchTerm);
                    if (!matchSearch) return false;
                }
                
                // Severity filter
                if (this.filters.severity && issue.severity !== this.filters.severity) {
                    return false;
                }
                
                // Category filter
                if (this.filters.category && issue.category !== this.filters.category) {
                    return false;
                }
                
                // Status filter
                if (this.filters.status && issue.status !== this.filters.status) {
                    return false;
                }
                
                return true;
            });
        },
        
        /**
         * Computed property: issues grouped by status
         */
        get issuesByStatus() {
            return {
                open: this.filteredIssues.filter(i => i.status === 'open'),
                in_progress: this.filteredIssues.filter(i => i.status === 'in_progress'),
                resolved: this.filteredIssues.filter(i => i.status === 'resolved')
            };
        }
    }));
});
