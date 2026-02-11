/**
 * js/bulk-upload-controller.js
 * Phase 6: Bulk CSV upload controller with progress polling
 */

class BulkUploadController {
    constructor() {
        this.baseUrl = 'http://localhost:8000/api';
        this.currentFile = null;
        this.sessionId = null;
        this.pollingInterval = null;
        this.institutionId = 1; // Would be determined from context
    }

    getAuthToken() {
        return localStorage.getItem('access_token') || '';
    }

    /**
     * Preview CSV and show column mapping
     */
    previewCSV(file) {
        this.currentFile = file;
        
        const reader = new FileReader();
        reader.onload = (e) => {
            const content = e.target.result;
            const lines = content.split('\n');
            
            if (lines.length < 2) {
                alert('CSV file appears to be empty or invalid.');
                return;
            }
            
            // Parse headers
            const headers = this.parseCSVLine(lines[0]);
            const sampleRow = this.parseCSVLine(lines[1]);
            
            // Auto-detect column mappings
            const mappings = this.detectColumnMappings(headers);
            
            // Show mapping UI
            this.renderColumnMappings(headers, sampleRow, mappings);
            
            // Show column mapping section
            document.getElementById('column-mapping').style.display = 'block';
            document.getElementById('upload-zone').style.display = 'none';
        };
        reader.readAsText(file);
    }

    parseCSVLine(line) {
        // Simple CSV parsing (handles quoted values)
        const result = [];
        let current = '';
        let inQuotes = false;
        
        for (let i = 0; i < line.length; i++) {
            const char = line[i];
            
            if (char === '"') {
                inQuotes = !inQuotes;
            } else if (char === ',' && !inQuotes) {
                result.push(current.trim());
                current = '';
            } else {
                current += char;
            }
        }
        result.push(current.trim());
        return result;
    }

    detectColumnMappings(headers) {
        const mappings = {};
        
        headers.forEach((header, index) => {
            const lower = header.toLowerCase();
            
            if (lower.includes('name') || lower === 'student_name' || lower === 'full_name') {
                mappings[index] = { field: 'name', confidence: 'high' };
            } else if (lower.includes('email') || lower === 'e-mail' || lower === 'email_address') {
                mappings[index] = { field: 'email', confidence: 'high' };
            } else if (lower.includes('roll') || lower === 'roll_number' || lower === 'student_id') {
                mappings[index] = { field: 'roll_number', confidence: 'medium' };
            } else if (lower.includes('year') || lower === 'academic_year') {
                mappings[index] = { field: 'year', confidence: 'medium' };
            } else if (lower.includes('course') || lower === 'program' || lower === 'degree') {
                mappings[index] = { field: 'course', confidence: 'medium' };
            } else {
                mappings[index] = { field: null, confidence: 'manual' };
            }
        });
        
        return mappings;
    }

    renderColumnMappings(headers, sampleRow, mappings) {
        const container = document.getElementById('mapping-rows');
        container.innerHTML = '';
        
        headers.forEach((header, index) => {
            const mapping = mappings[index];
            const sampleValue = sampleRow[index] || '';
            
            const row = document.createElement('div');
            row.className = 'mapping-row';
            row.innerHTML = `
                <div class="mapping-label">${header}</div>
                <div class="mapping-value">${sampleValue || '(empty)'}</div>
                <div class="mapping-status ${mapping.confidence}">
                    ${mapping.field ? `→ ${mapping.field}` : 'Manual'}
                </div>
            `;
            container.appendChild(row);
        });
    }

    /**
     * Start the upload process
     */
    async startUpload() {
        if (!this.currentFile) {
            alert('Please select a CSV file first.');
            return;
        }
        
        const token = this.getAuthToken();
        if (!token) {
            alert('Please log in first.');
            return;
        }
        
        // Hide mapping, show progress
        document.getElementById('column-mapping').style.display = 'none';
        document.getElementById('progress-section').classList.add('active');
        
        // Create form data
        const formData = new FormData();
        formData.append('file', this.currentFile);
        
        try {
            const response = await fetch(
                `${this.baseUrl}/institutions/${this.institutionId}/bulk-upload`,
                {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${token}`
                    },
                    body: formData
                }
            );
            
            if (response.ok) {
                const data = await response.json();
                this.sessionId = data.session_id;
                
                // Start polling for progress
                this.startPolling();
            } else {
                const error = await response.json();
                alert('Upload failed: ' + (error.detail || 'Unknown error'));
                this.resetUpload();
            }
        } catch (error) {
            console.error('Upload error:', error);
            alert('Network error during upload.');
            this.resetUpload();
        }
    }

    /**
     * Poll for upload progress
     */
    startPolling() {
        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
        }
        
        this.pollStatus(); // Immediate first poll
        
        this.pollingInterval = setInterval(() => {
            this.pollStatus();
        }, 2000); // Poll every 2 seconds
    }

    async pollStatus() {
        if (!this.sessionId) return;
        
        const token = this.getAuthToken();
        
        try {
            const response = await fetch(
                `${this.baseUrl}/institutions/${this.institutionId}/bulk-upload/${this.sessionId}/status`,
                {
                    headers: { 'Authorization': `Bearer ${token}` }
                }
            );
            
            if (response.ok) {
                const status = await response.json();
                this.updateProgressUI(status);
                
                // Check if complete
                if (status.status === 'completed' || status.status === 'failed') {
                    clearInterval(this.pollingInterval);
                    this.onUploadComplete(status);
                }
            }
        } catch (error) {
            console.error('Polling error:', error);
        }
    }

    updateProgressUI(status) {
        // Update progress bar
        const progressBar = document.getElementById('progress-bar');
        progressBar.style.width = status.progress_percentage + '%';
        progressBar.textContent = status.progress_percentage + '%';
        
        // Update text
        document.getElementById('progress-text').textContent = 
            `${status.processed_rows}/${status.total_rows} rows`;
        
        // Update stats
        document.getElementById('success-count').textContent = status.success_count;
        document.getElementById('error-count').textContent = status.error_count;
        document.getElementById('pending-count').textContent = 
            status.total_rows - status.processed_rows;
        
        // Update time remaining
        const timeEl = document.getElementById('time-remaining');
        if (status.estimated_time_remaining) {
            timeEl.textContent = `Estimated time remaining: ${status.estimated_time_remaining}`;
        } else if (status.status === 'completed') {
            timeEl.textContent = 'Upload complete!';
        }
    }

    onUploadComplete(status) {
        // Show success message
        const progressBar = document.getElementById('progress-bar');
        progressBar.classList.remove('processing');
        progressBar.style.background = '#4CAF50';
        
        // Show error log section if there were errors
        if (status.error_count > 0 && status.error_log_path) {
            document.getElementById('error-log-section').classList.add('active');
        }
        
        // Final status update
        document.getElementById('time-remaining').textContent = 
            `Upload complete! ${status.success_count} successful, ${status.error_count} failed.`;
        
        // Auto-refresh parent dashboard if exists
        if (window.opener && window.opener.loadStats) {
            window.opener.loadStats();
        }
    }

    resetUpload() {
        this.currentFile = null;
        this.sessionId = null;
        
        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
        }
        
        document.getElementById('upload-zone').style.display = 'block';
        document.getElementById('column-mapping').style.display = 'none';
        document.getElementById('progress-section').classList.remove('active');
        document.getElementById('error-log-section').classList.remove('active');
        
        // Reset progress bar
        const progressBar = document.getElementById('progress-bar');
        progressBar.style.width = '0%';
        progressBar.textContent = '0%';
        progressBar.classList.add('processing');
        progressBar.style.background = '';
        
        // Reset stats
        document.getElementById('success-count').textContent = '0';
        document.getElementById('error-count').textContent = '0';
        document.getElementById('pending-count').textContent = '0';
    }

    /**
     * Download error log
     */
    downloadErrorLog() {
        if (!this.sessionId) return;
        
        const token = this.getAuthToken();
        
        fetch(
            `${this.baseUrl}/institutions/${this.institutionId}/bulk-upload/${this.sessionId}/errors`,
            {
                headers: { 'Authorization': `Bearer ${token}` }
            }
        )
        .then(response => response.blob())
        .then(blob => {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `upload_errors_${this.sessionId}.csv`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
        })
        .catch(error => {
            console.error('Error downloading error log:', error);
        });
    }
}
