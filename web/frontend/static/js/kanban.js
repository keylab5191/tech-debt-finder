// Tech Debt Dashboard - Kanban Board Component
document.addEventListener('alpine:init', () => {
    
    /**
     * Kanban Column Component
     * Manages drag and drop functionality for a single column
     */
    Alpine.data('kanbanColumn', (columnStatus) => ({
        // Track dragged item
        draggedIssue: null,
        
        /**
         * Handle drag start
         */
        onDragStart(event, issue) {
            this.draggedIssue = issue;
            event.dataTransfer.effectAllowed = 'move';
            event.dataTransfer.setData('application/json', JSON.stringify(issue));
            
            // Add visual feedback
            event.target.classList.add('dragging');
            
            // Set drag image offset
            const rect = event.target.getBoundingClientRect();
            const offsetX = event.clientX - rect.left;
            const offsetY = event.clientY - rect.top;
            
            // Create a custom drag image
            const dragImage = event.target.cloneNode(true);
            dragImage.style.position = 'fixed';
            dragImage.style.top = '-1000px';
            dragImage.style.width = rect.width + 'px';
            document.body.appendChild(dragImage);
            event.dataTransfer.setDragImage(dragImage, offsetX, offsetY);
            
            // Remove drag image element after a delay
            setTimeout(() => {
                document.body.removeChild(dragImage);
            }, 0);
            
            // Emit event to highlight valid drop zones
            window.dispatchEvent(new CustomEvent('drag-started', { detail: { issue } }));
        },
        
        /**
         * Handle drag end
         */
        onDragEnd(event) {
            event.target.classList.remove('dragging');
            this.draggedIssue = null;
            
            // Remove drag-over states from all columns
            document.querySelectorAll('.kanban-column-content').forEach(col => {
                col.classList.remove('drag-over');
            });
            
            // Emit event
            window.dispatchEvent(new CustomEvent('drag-ended'));
        },
        
        /**
         * Handle drag over (required for drop to work)
         */
        onDragOver(event) {
            event.preventDefault();
            event.dataTransfer.dropEffect = 'move';
            
            // Add visual feedback
            const columnContent = event.currentTarget;
            columnContent.classList.add('drag-over');
        },
        
        /**
         * Handle drag leave
         */
        onDragLeave(event) {
            // Remove visual feedback
            const columnContent = event.currentTarget;
            columnContent.classList.remove('drag-over');
        },
        
        /**
         * Handle drop
         */
        onDrop(event, targetStatus) {
            event.preventDefault();
            
            // Remove drag-over state
            const columnContent = event.currentTarget;
            columnContent.classList.remove('drag-over');
            
            // Get the dragged issue data
            const issueData = event.dataTransfer.getData('application/json');
            if (!issueData) return;
            
            const issue = JSON.parse(issueData);
            
            // Check if the issue is being moved to a different column
            if (issue.status === targetStatus) {
                return;
            }
            
            // Update the issue status
            issue.status = targetStatus;
            
            // Emit event for the main app to handle the update
            window.dispatchEvent(new CustomEvent('issue-moved', {
                detail: {
                    issueId: issue.id,
                    newStatus: targetStatus,
                    oldStatus: issue.status
                }
            }));
            
            // Show success feedback
            this.showDropFeedback(event.clientX, event.clientY, targetStatus);
        },
        
        /**
         * Show visual feedback when dropping an issue
         */
        showDropFeedback(x, y, status) {
            const feedback = document.createElement('div');
            feedback.className = 'fixed z-50 pointer-events-none animate-fade-out';
            feedback.style.left = x + 'px';
            feedback.style.top = y + 'px';
            feedback.innerHTML = `
                <div class="flex items-center gap-2 bg-green-500 text-white px-4 py-2 rounded-lg shadow-lg">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                    </svg>
                    <span class="font-medium">Moved to ${status.replace('_', ' ')}</span>
                </div>
            `;
            
            document.body.appendChild(feedback);
            
            // Animate and remove
            setTimeout(() => {
                feedback.style.opacity = '0';
                feedback.style.transform = 'translateY(-20px)';
                feedback.style.transition = 'all 0.3s ease';
                setTimeout(() => {
                    document.body.removeChild(feedback);
                }, 300);
            }, 1000);
        }
    }));
    
    /**
     * Column Definitions
     */
    Alpine.data('kanbanColumns', () => ({
        columns: [
            {
                id: 'open',
                title: 'Open',
                status: 'open',
                color: 'gray',
                icon: 'circle'
            },
            {
                id: 'in_progress',
                title: 'In Progress',
                status: 'in_progress',
                color: 'blue',
                icon: 'clock'
            },
            {
                id: 'resolved',
                title: 'Resolved',
                status: 'resolved',
                color: 'green',
                icon: 'check'
            }
        ],
        
        /**
         * Get column by status
         */
        getColumnByStatus(status) {
            return this.columns.find(col => col.status === status);
        },
        
        /**
         * Get column color classes
         */
        getColumnColorClass(color, type = 'bg') {
            const colors = {
                gray: {
                    bg: 'bg-gray-100',
                    text: 'text-gray-700',
                    border: 'border-gray-200',
                    dot: 'bg-gray-400'
                },
                blue: {
                    bg: 'bg-blue-50',
                    text: 'text-blue-700',
                    border: 'border-blue-200',
                    dot: 'bg-blue-500'
                },
                green: {
                    bg: 'bg-green-50',
                    text: 'text-green-700',
                    border: 'border-green-200',
                    dot: 'bg-green-500'
                }
            };
            
            return colors[color]?.[type] || colors.gray[type];
        }
    }));
    
    /**
     * Issue Card Component
     * Individual card behavior
     */
    Alpine.data('issueCard', () => ({
        /**
         * Get severity color class
         */
        getSeverityColor(severity) {
            const colors = {
                critical: 'border-l-red-500',
                high: 'border-l-orange-500',
                medium: 'border-l-yellow-500',
                low: 'border-l-green-500'
            };
            return colors[severity] || colors.low;
        },
        
        /**
         * Get severity badge classes
         */
        getSeverityBadgeClass(severity) {
            const classes = {
                critical: 'bg-red-100 text-red-800',
                high: 'bg-orange-100 text-orange-800',
                medium: 'bg-yellow-100 text-yellow-800',
                low: 'bg-green-100 text-green-800'
            };
            return classes[severity] || classes.low;
        },
        
        /**
         * Format file path for display
         */
        formatFilePath(path) {
            if (!path) return '';
            const parts = path.split('/');
            return parts[parts.length - 1];
        },
        
        /**
         * Truncate text with ellipsis
         */
        truncate(text, length = 50) {
            if (!text) return '';
            return text.length > length ? text.substring(0, length) + '...' : text;
        }
    }));
    
    /**
     * Drag and Drop Manager
     * Global drag and drop state management
     */
    Alpine.data('dragDropManager', () => ({
        isDragging: false,
        draggedIssue: null,
        
        init() {
            // Listen for drag events
            window.addEventListener('drag-started', (event) => {
                this.isDragging = true;
                this.draggedIssue = event.detail.issue;
            });
            
            window.addEventListener('drag-ended', () => {
                this.isDragging = false;
                this.draggedIssue = null;
            });
        }
    }));
});

/**
 * Utility functions for Kanban operations
 */
const KanbanUtils = {
    /**
     * Move an issue between columns
     */
    moveIssue(issues, issueId, newStatus) {
        const issueIndex = issues.findIndex(i => i.id === issueId);
        if (issueIndex === -1) return issues;
        
        const updatedIssues = [...issues];
        updatedIssues[issueIndex] = {
            ...updatedIssues[issueIndex],
            status: newStatus,
            updated_at: new Date().toISOString()
        };
        
        return updatedIssues;
    },
    
    /**
     * Sort issues within a column
     */
    sortIssues(issues, sortBy = 'created_at', order = 'desc') {
        return [...issues].sort((a, b) => {
            let aVal = a[sortBy];
            let bVal = b[sortBy];
            
            if (sortBy === 'severity') {
                const severityOrder = { critical: 4, high: 3, medium: 2, low: 1 };
                aVal = severityOrder[aVal] || 0;
                bVal = severityOrder[bVal] || 0;
            }
            
            if (order === 'desc') {
                return aVal > bVal ? -1 : 1;
            } else {
                return aVal < bVal ? -1 : 1;
            }
        });
    },
    
    /**
     * Filter issues by multiple criteria
     */
    filterIssues(issues, filters) {
        return issues.filter(issue => {
            // Apply each filter
            if (filters.severity && issue.severity !== filters.severity) return false;
            if (filters.category && issue.category !== filters.category) return false;
            if (filters.status && issue.status !== filters.status) return false;
            if (filters.search) {
                const searchTerm = filters.search.toLowerCase();
                const match = issue.title.toLowerCase().includes(searchTerm) ||
                             issue.description?.toLowerCase().includes(searchTerm) ||
                             issue.file.toLowerCase().includes(searchTerm);
                if (!match) return false;
            }
            return true;
        });
    },
    
    /**
     * Group issues by status
     */
    groupByStatus(issues) {
        return {
            open: issues.filter(i => i.status === 'open'),
            in_progress: issues.filter(i => i.status === 'in_progress'),
            resolved: issues.filter(i => i.status === 'resolved')
        };
    },
    
    /**
     * Calculate column statistics
     */
    getColumnStats(issues) {
        const grouped = this.groupByStatus(issues);
        
        return {
            open: {
                total: grouped.open.length,
                bySeverity: this.countBySeverity(grouped.open)
            },
            in_progress: {
                total: grouped.in_progress.length,
                bySeverity: this.countBySeverity(grouped.in_progress)
            },
            resolved: {
                total: grouped.resolved.length,
                bySeverity: this.countBySeverity(grouped.resolved)
            }
        };
    },
    
    /**
     * Count issues by severity
     */
    countBySeverity(issues) {
        return issues.reduce((acc, issue) => {
            acc[issue.severity] = (acc[issue.severity] || 0) + 1;
            return acc;
        }, {});
    }
};

// Export for use in other modules
window.KanbanUtils = KanbanUtils;
