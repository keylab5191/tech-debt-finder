// Tech Debt Dashboard - Main Alpine.js Application
document.addEventListener('alpine:init', () => {
    Alpine.data('techDebtApp', () => ({
        // State
        issues: [],
        selectedIssues: [],
        activeScans: [],
        activeFixes: [],  // Track active fixes
        scanning: false,
        viewMode: 'list',
        groupByFile: true,
        selectedIssue: null,
        showScanModal: false,
        
        // Scans
        scans: [],
        selectedScanId: null,
        showAllScans: false,
        
        // Filters
        filters: {
            search: '',
            severity: '',
            category: '',
            status: ''
        },
        
        // Pagination
        pagination: {
            currentPage: 1,
            pageSize: 50,
            total: 0
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
            this.fetchScans();
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
            // Fetch all issues by getting all pages
            try {
                const allIssues = [];
                let page = 0;
                const pageSize = 100;
                
                while (true) {
                    const params = new URLSearchParams();
                    params.append('skip', String(page * pageSize));
                    params.append('limit', String(pageSize));
                    
                    // Add scan filter
                    if (this.showAllScans) {
                        params.append('all_scans', 'true');
                    } else if (this.selectedScanId) {
                        params.append('scan_id', this.selectedScanId);
                    }
                    
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
                    const items = data.items || [];
                    allIssues.push(...items);
                    
                    // Update pagination info
                    this.pagination.total = data.total || 0;
                    
                    // Stop if we've fetched all
                    if (items.length < pageSize || allIssues.length >= data.total) {
                        break;
                    }
                    
                    page++;
                    
                    // Safety limit
                    if (page > 10) break;
                }
                
                this.issues = allIssues;
                console.log(`Loaded ${this.issues.length} issues (total: ${this.pagination.total})`);
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
         * Fetch all scans for selector
         */
        async fetchScans() {
            try {
                const response = await fetch(`${this.apiUrl}/scans?limit=20`);
                
                if (!response.ok) {
                    throw new Error(`Failed to fetch scans: ${response.statusText}`);
                }
                
                const data = await response.json();
                this.scans = data.items || [];
                
                // Auto-select latest scan if none selected
                if (!this.selectedScanId && this.scans.length > 0) {
                    this.selectedScanId = this.scans[0].id;
                }
                
            } catch (error) {
                console.error('Error fetching scans:', error);
                this.scans = [];
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
                max_file_size_kb: 100,
                clear_previous: false
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
                        max_file_size_kb: parseInt(this.scanForm.max_file_size_kb),
                        clear_previous: this.scanForm.clear_previous
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
                
                // If clearing previous, select the new scan
                if (this.scanForm.clear_previous) {
                    this.selectedScanId = data.id;
                    this.showAllScans = false;
                }
                
                // Refresh scans list
                this.fetchScans();
                
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
         * Handle scan selector change
         */
        async onScanChange() {
            this.showAllScans = this.selectedScanId === 'all';
            await this.fetchIssues();
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
         * Toggle issue selection
         */
        toggleIssueSelection(issueId) {
            if (this.selectedIssues.includes(issueId)) {
                this.selectedIssues = this.selectedIssues.filter(id => id !== issueId);
            } else {
                this.selectedIssues.push(issueId);
            }
        },
        
        /**
         * Select all visible issues
         */
        selectAllIssues() {
            if (this.selectedIssues.length === this.filteredIssues.length) {
                this.selectedIssues = [];
            } else {
                this.selectedIssues = this.filteredIssues.map(i => i.id);
            }
        },
        
        /**
         * Fix selected issues
         */
        async fixSelectedIssues() {
            if (this.selectedIssues.length === 0) return;
            
            if (!confirm(`Fix ${this.selectedIssues.length} issues? This will modify code files.`)) return;
            
            this.scanning = true; // Reuse scanning state for loading indicator
            
            try {
                const response = await fetch(`${this.apiUrl}/issues/fix`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ issue_ids: this.selectedIssues })
                });
                
                if (!response.ok) {
                    throw new Error(`Failed to fix issues: ${response.statusText}`);
                }
                
                const data = await response.json();
                
                // Clear selection immediately as it's async now
                this.selectedIssues = [];
                
                alert(data.message + ` (Total: ${data.total_issues})`);
                
            } catch (error) {
                console.error('Error fixing issues:', error);
                alert('Failed to fix issues: ' + error.message);
            } finally {
                this.scanning = false;
            }
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
                    // Refresh issues list and scans
                    this.fetchIssues();
                    this.fetchScans();
                    break;
                    
                case 'scan_error':
                case 'scan_failed':
                    console.error('Scan error:', message.error);
                    this.activeScans = this.activeScans.filter(s => s.id !== message.scan_id);
                    this.scanning = false;
                    break;
                    
                case 'fix_progress':
                    this.handleFixProgress(message);
                    break;
            }
        },
        
        /**
         * Handle fix progress updates from WebSocket
         */
        handleFixProgress(message) {
            const { issue_ids, status, message: msg, model, duration, result, cost, input_tokens, output_tokens } = message;
            
            // Find or create fix entry
            let fixEntry = this.activeFixes.find(f => 
                f.issue_ids && f.issue_ids.length === issue_ids.length && 
                f.issue_ids.every(id => issue_ids.includes(id))
            );
            
            if (!fixEntry) {
                fixEntry = {
                    issue_ids: issue_ids,
                    status: status,
                    message: msg,
                    model: model,
                    duration: duration,
                    result: result,
                    cost: cost,
                    input_tokens: input_tokens,
                    output_tokens: output_tokens,
                    startedAt: new Date()
                };
                this.activeFixes.push(fixEntry);
            } else {
                // Update existing
                fixEntry.status = status;
                fixEntry.message = msg;
                if (model) fixEntry.model = model;
                if (duration) fixEntry.duration = duration;
                if (result) fixEntry.result = result;
                if (cost !== undefined) fixEntry.cost = cost;
                if (input_tokens !== undefined) fixEntry.input_tokens = input_tokens;
                if (output_tokens !== undefined) fixEntry.output_tokens = output_tokens;
            }
            
            // Don't auto-remove - keep results visible until page refresh
            // Refresh issues to show updated status
            this.fetchIssues();
            
            // Use scanning indicator if there are active fixes
            this.scanning = this.activeScans.length > 0 || this.activeFixes.length > 0;
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
         * Computed property: issues grouped by file
         */
        get issuesByFile() {
            const grouped = {};
            for (const issue of this.filteredIssues) {
                const file = issue.file_path;
                if (!grouped[file]) {
                    grouped[file] = {
                        file: file,
                        issues: [],
                        severity: 'low', // Will be upgraded to highest severity
                        openCount: 0,
                        inProgressCount: 0,
                        resolvedCount: 0
                    };
                }
                grouped[file].issues.push(issue);
                
                // Update counts
                if (issue.status === 'open') grouped[file].openCount++;
                if (issue.status === 'in_progress') grouped[file].inProgressCount++;
                if (issue.status === 'resolved') grouped[file].resolvedCount++;
                
                // Upgrade severity if needed
                const severityOrder = { 'critical': 4, 'high': 3, 'medium': 2, 'low': 1 };
                const currentSev = severityOrder[grouped[file].severity] || 0;
                const issueSev = severityOrder[issue.severity] || 0;
                if (issueSev > currentSev) {
                    // Find the key for this severity
                    for (const [sev, val] of Object.entries(severityOrder)) {
                        if (val === issueSev) {
                            grouped[file].severity = sev;
                            break;
                        }
                    }
                }
            }
            
            // Convert to array and sort by severity
            const result = Object.values(grouped).sort((a, b) => {
                const severityOrder = { 'critical': 4, 'high': 3, 'medium': 2, 'low': 1 };
                return (severityOrder[b.severity] || 0) - (severityOrder[a.severity] || 0);
            });
            
            // Sort issues within each file by severity
            for (const fileGroup of result) {
                fileGroup.issues.sort((a, b) => {
                    const severityOrder = { 'critical': 4, 'high': 3, 'medium': 2, 'low': 1 };
                    return (severityOrder[b.severity] || 0) - (severityOrder[a.severity] || 0);
                });
            }
            
            return result;
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
                                       issue.file_path.toLowerCase().includes(searchTerm);
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
