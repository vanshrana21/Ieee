/**
 * Phase 4: Memorial Upload Controller
 * 
 * Handles PDF upload workflow with drag & drop, progress tracking,
 * and AI analysis status polling.
 * 
 * Features:
 * - Drag & drop file selection
 * - File validation (PDF, size, pages)
 * - Upload progress tracking
 * - AI analysis status polling
 * - Previous submissions list
 */

class MemorialUploadController {
    /**
     * @param {number} competitionId - ID of the competition
     * @param {object} options - Configuration options
     */
    constructor(competitionId, options = {}) {
        this.competitionId = competitionId;
        this.apiBaseUrl = options.apiBaseUrl || '/api';
        this.onUploadComplete = options.onUploadComplete || null;
        this.onAnalysisComplete = options.onAnalysisComplete || null;
        
        // State
        this.selectedFile = null;
        this.currentTeamId = null;
        this.currentTeamSide = null;
        this.submissionNotes = '';
        this.uploadId = null;
        this.isUploading = false;
        this.statusPollInterval = null;
        
        // Validation limits
        this.MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB
        this.MAX_PAGES = 50;
        this.ALLOWED_TYPES = ['application/pdf'];
        
        // DOM Element Cache
        this.elements = {};
        
        // Bind methods
        this.handleDragOver = this.handleDragOver.bind(this);
        this.handleDragLeave = this.handleDragLeave.bind(this);
        this.handleDrop = this.handleDrop.bind(this);
        this.handleFileSelect = this.handleFileSelect.bind(this);
        this.uploadFile = this.uploadFile.bind(this);
        this.pollAnalysisStatus = this.pollAnalysisStatus.bind(this);
    }
    
    /**
     * Initialize controller and setup event listeners
     */
    initialize() {
        this.cacheElements();
        this.setupEventListeners();
        this.loadPreviousSubmissions();
    }
    
    /**
     * Cache DOM elements for performance
     */
    cacheElements() {
        // Upload container
        this.elements.container = document.getElementById('memorial-upload-container');
        
        // Drop zone
        this.elements.dropZone = document.getElementById('drop-zone');
        this.elements.dropOverlay = document.getElementById('drop-overlay');
        this.elements.fileInput = document.getElementById('memorial-file');
        
        // File preview
        this.elements.filePreview = document.getElementById('file-preview');
        this.elements.fileName = document.getElementById('file-name');
        this.elements.fileSize = document.getElementById('file-size');
        this.elements.filePages = document.getElementById('file-pages');
        this.elements.fileStatus = document.getElementById('file-status');
        this.elements.validationErrors = document.getElementById('validation-errors');
        this.elements.errorText = document.getElementById('error-text');
        this.elements.removeFileBtn = document.getElementById('remove-file');
        
        // Form elements
        this.elements.teamSelect = document.getElementById('memorial-team');
        this.elements.submissionNotes = document.getElementById('submission-notes');
        this.elements.notesCount = document.getElementById('notes-count');
        
        // Progress
        this.elements.uploadProgress = document.getElementById('upload-progress');
        this.elements.progressPercentage = document.getElementById('progress-percentage');
        this.elements.progressFill = document.getElementById('progress-fill');
        this.elements.progressBytes = document.getElementById('progress-bytes');
        this.elements.progressTime = document.getElementById('progress-time');
        
        // Analysis status
        this.elements.analysisStatus = document.getElementById('analysis-status');
        this.elements.analysisStage = document.getElementById('analysis-stage');
        this.elements.analysisPage = document.getElementById('analysis-page');
        this.elements.analysisTime = document.getElementById('analysis-time');
        
        // Messages
        this.elements.successMessage = document.getElementById('success-message');
        this.elements.errorMessage = document.getElementById('error-message');
        this.elements.errorTextDetail = document.getElementById('error-text-detail');
        this.elements.viewAnalysisBtn = document.getElementById('view-analysis-btn');
        this.elements.uploadAnotherBtn = document.getElementById('upload-another-btn');
        this.elements.retryBtn = document.getElementById('retry-btn');
        
        // Action buttons
        this.elements.actionButtons = document.getElementById('action-buttons');
        this.elements.cancelBtn = document.getElementById('cancel-upload');
        this.elements.submitBtn = document.getElementById('submit-memorial');
        
        // Previous submissions
        this.elements.previousSubmissions = document.getElementById('previous-submissions');
        this.elements.submissionList = document.getElementById('submission-list');
        this.elements.refreshBtn = document.getElementById('refresh-submissions');
        this.elements.template = document.getElementById('submission-item-template');
    }
    
    /**
     * Setup all event listeners
     */
    setupEventListeners() {
        // Drop zone events
        if (this.elements.dropZone) {
            this.elements.dropZone.addEventListener('dragover', this.handleDragOver);
            this.elements.dropZone.addEventListener('dragleave', this.handleDragLeave);
            this.elements.dropZone.addEventListener('drop', this.handleDrop);
            this.elements.dropZone.addEventListener('click', () => {
                if (this.elements.fileInput) {
                    this.elements.fileInput.click();
                }
            });
        }
        
        // File input change
        if (this.elements.fileInput) {
            this.elements.fileInput.addEventListener('change', this.handleFileSelect);
        }
        
        // Remove file button
        if (this.elements.removeFileBtn) {
            this.elements.removeFileBtn.addEventListener('click', () => this.removeFile());
        }
        
        // Team selection
        if (this.elements.teamSelect) {
            this.elements.teamSelect.addEventListener('change', (e) => {
                this.currentTeamSide = e.target.value;
                this.currentTeamId = e.target.selectedOptions[0]?.dataset.teamId || null;
                this.updateSubmitButton();
            });
        }
        
        // Submission notes
        if (this.elements.submissionNotes) {
            this.elements.submissionNotes.addEventListener('input', (e) => {
                this.submissionNotes = e.target.value;
                this.updateNotesCounter();
            });
        }
        
        // Action buttons
        if (this.elements.cancelBtn) {
            this.elements.cancelBtn.addEventListener('click', () => this.cancelUpload());
        }
        
        if (this.elements.submitBtn) {
            this.elements.submitBtn.addEventListener('click', () => this.uploadFile());
        }
        
        if (this.elements.retryBtn) {
            this.elements.retryBtn.addEventListener('click', () => this.resetForm());
        }
        
        if (this.elements.uploadAnotherBtn) {
            this.elements.uploadAnotherBtn.addEventListener('click', () => this.resetForm());
        }
        
        if (this.elements.viewAnalysisBtn) {
            this.elements.viewAnalysisBtn.addEventListener('click', () => {
                if (this.onAnalysisComplete) {
                    this.onAnalysisComplete(this.uploadId);
                }
            });
        }
        
        if (this.elements.refreshBtn) {
            this.elements.refreshBtn.addEventListener('click', () => this.loadPreviousSubmissions());
        }
    }
    
    /**
     * Handle drag over event
     * @param {DragEvent} e 
     */
    handleDragOver(e) {
        e.preventDefault();
        e.stopPropagation();
        if (this.elements.dropOverlay) {
            this.elements.dropOverlay.style.display = 'flex';
        }
    }
    
    /**
     * Handle drag leave event
     * @param {DragEvent} e 
     */
    handleDragLeave(e) {
        e.preventDefault();
        e.stopPropagation();
        if (this.elements.dropOverlay) {
            this.elements.dropOverlay.style.display = 'none';
        }
    }
    
    /**
     * Handle drop event
     * @param {DragEvent} e 
     */
    handleDrop(e) {
        e.preventDefault();
        e.stopPropagation();
        
        if (this.elements.dropOverlay) {
            this.elements.dropOverlay.style.display = 'none';
        }
        
        const files = e.dataTransfer?.files;
        if (files && files.length > 0) {
            this.validateAndSetFile(files[0]);
        }
    }
    
    /**
     * Handle file selection from input
     * @param {Event} e 
     */
    handleFileSelect(e) {
        const files = e.target?.files;
        if (files && files.length > 0) {
            this.validateAndSetFile(files[0]);
        }
    }
    
    /**
     * Validate and set the selected file
     * @param {File} file 
     */
    validateAndSetFile(file) {
        // Reset previous errors
        this.hideValidationErrors();
        
        // Check file type
        if (!file.name.toLowerCase().endsWith('.pdf')) {
            this.showValidationError('Only PDF files are allowed');
            return;
        }
        
        // Check file size
        if (file.size > this.MAX_FILE_SIZE) {
            const maxMB = this.MAX_FILE_SIZE / (1024 * 1024);
            this.showValidationError(`File too large. Maximum size is ${maxMB}MB`);
            return;
        }
        
        this.selectedFile = file;
        this.showFilePreview();
        this.updateSubmitButton();
    }
    
    /**
     * Show file preview with details
     */
    showFilePreview() {
        if (!this.selectedFile || !this.elements.filePreview) return;
        
        // Update file info
        if (this.elements.fileName) {
            this.elements.fileName.textContent = this.selectedFile.name;
        }
        
        if (this.elements.fileSize) {
            const sizeMB = (this.selectedFile.size / (1024 * 1024)).toFixed(1);
            this.elements.fileSize.textContent = `${sizeMB} MB`;
        }
        
        // Show preview, hide drop zone
        this.elements.filePreview.style.display = 'block';
        if (this.elements.dropZone) {
            this.elements.dropZone.style.display = 'none';
        }
    }
    
    /**
     * Remove selected file
     */
    removeFile() {
        this.selectedFile = null;
        
        if (this.elements.filePreview) {
            this.elements.filePreview.style.display = 'none';
        }
        
        if (this.elements.dropZone) {
            this.elements.dropZone.style.display = 'block';
        }
        
        if (this.elements.fileInput) {
            this.elements.fileInput.value = '';
        }
        
        this.hideValidationErrors();
        this.updateSubmitButton();
    }
    
    /**
     * Show validation error
     * @param {string} message 
     */
    showValidationError(message) {
        if (this.elements.errorText) {
            this.elements.errorText.textContent = message;
        }
        if (this.elements.validationErrors) {
            this.elements.validationErrors.style.display = 'block';
        }
        if (this.elements.fileStatus) {
            this.elements.fileStatus.innerHTML = `
                <span class="status-icon error">✗</span>
                <span class="status-text">${message}</span>
            `;
        }
    }
    
    /**
     * Hide validation errors
     */
    hideValidationErrors() {
        if (this.elements.validationErrors) {
            this.elements.validationErrors.style.display = 'none';
        }
    }
    
    /**
     * Update notes character counter
     */
    updateNotesCounter() {
        if (this.elements.notesCount && this.elements.submissionNotes) {
            this.elements.notesCount.textContent = this.elements.submissionNotes.value.length;
        }
    }
    
    /**
     * Update submit button state
     */
    updateSubmitButton() {
        if (!this.elements.submitBtn) return;
        
        const canSubmit = this.selectedFile && this.currentTeamSide && !this.isUploading;
        this.elements.submitBtn.disabled = !canSubmit;
    }
    
    /**
     * Upload the selected file
     */
    async uploadFile() {
        if (!this.selectedFile || !this.currentTeamSide || this.isUploading) return;
        
        this.isUploading = true;
        this.updateSubmitButton();
        
        // Show progress
        this.showUploadProgress();
        
        try {
            const formData = new FormData();
            formData.append('file', this.selectedFile);
            formData.append('team_id', this.currentTeamId || '1');
            formData.append('submission_notes', this.submissionNotes);
            
            const xhr = new XMLHttpRequest();
            
            // Track upload progress
            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable) {
                    const percentage = Math.round((e.loaded / e.total) * 100);
                    this.updateProgress(percentage, e.loaded, e.total);
                }
            });
            
            // Handle completion
            xhr.addEventListener('load', () => {
                if (xhr.status === 200 || xhr.status === 202) {
                    const response = JSON.parse(xhr.responseText);
                    this.uploadId = response.upload_id || response.id;
                    this.onUploadSuccess(response);
                } else {
                    let errorMsg = 'Upload failed';
                    try {
                        const error = JSON.parse(xhr.responseText);
                        errorMsg = error.detail || error.message || errorMsg;
                    } catch {}
                    this.onUploadError(errorMsg);
                }
            });
            
            xhr.addEventListener('error', () => {
                this.onUploadError('Network error. Please try again.');
            });
            
            xhr.open('POST', `${this.apiBaseUrl}/competitions/${this.competitionId}/memorials`);
            xhr.setRequestHeader('Authorization', `Bearer ${this.getAuthToken()}`);
            xhr.send(formData);
            
        } catch (error) {
            this.onUploadError(error.message || 'Upload failed');
        }
    }
    
    /**
     * Show upload progress UI
     */
    showUploadProgress() {
        if (this.elements.uploadProgress) {
            this.elements.uploadProgress.style.display = 'block';
        }
        if (this.elements.actionButtons) {
            this.elements.actionButtons.style.display = 'none';
        }
        if (this.elements.filePreview) {
            this.elements.filePreview.style.display = 'none';
        }
    }
    
    /**
     * Update progress display
     * @param {number} percentage 
     * @param {number} loaded 
     * @param {number} total 
     */
    updateProgress(percentage, loaded, total) {
        if (this.elements.progressPercentage) {
            this.elements.progressPercentage.textContent = `${percentage}%`;
        }
        
        if (this.elements.progressFill) {
            this.elements.progressFill.style.width = `${percentage}%`;
        }
        
        if (this.elements.progressBytes) {
            const loadedMB = (loaded / (1024 * 1024)).toFixed(1);
            const totalMB = (total / (1024 * 1024)).toFixed(1);
            this.elements.progressBytes.textContent = `${loadedMB} MB / ${totalMB} MB`;
        }
    }
    
    /**
     * Handle upload success
     * @param {object} response 
     */
    onUploadSuccess(response) {
        this.isUploading = false;
        
        // Hide progress
        if (this.elements.uploadProgress) {
            this.elements.uploadProgress.style.display = 'none';
        }
        
        // Show analysis status
        this.showAnalysisStatus();
        
        // Start polling for analysis status
        this.pollAnalysisStatus();
        
        // Callback
        if (this.onUploadComplete) {
            this.onUploadComplete(response);
        }
    }
    
    /**
     * Handle upload error
     * @param {string} errorMessage 
     */
    onUploadError(errorMessage) {
        this.isUploading = false;
        this.updateSubmitButton();
        
        // Hide progress
        if (this.elements.uploadProgress) {
            this.elements.uploadProgress.style.display = 'none';
        }
        
        // Show error
        if (this.elements.errorMessage) {
            this.elements.errorMessage.style.display = 'block';
        }
        if (this.elements.errorTextDetail) {
            this.elements.errorTextDetail.textContent = errorMessage;
        }
        
        // Show action buttons again
        if (this.elements.actionButtons) {
            this.elements.actionButtons.style.display = 'flex';
        }
    }
    
    /**
     * Show analysis status UI
     */
    showAnalysisStatus() {
        if (this.elements.analysisStatus) {
            this.elements.analysisStatus.style.display = 'block';
        }
    }
    
    /**
     * Poll for AI analysis status
     */
    async pollAnalysisStatus() {
        if (!this.uploadId) return;
        
        const checkStatus = async () => {
            try {
                const response = await fetch(
                    `${this.apiBaseUrl}/competitions/${this.competitionId}/memorials/${this.uploadId}/status`,
                    {
                        headers: {
                            'Authorization': `Bearer ${this.getAuthToken()}`
                        }
                    }
                );
                
                if (!response.ok) return;
                
                const data = await response.json();
                
                // Update UI
                if (this.elements.analysisStage) {
                    this.elements.analysisStage.textContent = data.message || 'Processing...';
                }
                
                // Check if complete
                if (data.status === 'completed') {
                    this.onAnalysisCompleteSuccess();
                } else if (data.status === 'failed') {
                    this.onAnalysisError(data.message || 'Analysis failed');
                } else {
                    // Continue polling
                    setTimeout(checkStatus, 3000);
                }
                
            } catch (error) {
                console.error('Status check failed:', error);
                setTimeout(checkStatus, 5000);
            }
        };
        
        // Start polling
        checkStatus();
    }
    
    /**
     * Handle analysis completion
     */
    onAnalysisCompleteSuccess() {
        // Hide analysis status
        if (this.elements.analysisStatus) {
            this.elements.analysisStatus.style.display = 'none';
        }
        
        // Show success message
        if (this.elements.successMessage) {
            this.elements.successMessage.style.display = 'block';
        }
        
        // Refresh submissions list
        this.loadPreviousSubmissions();
        
        // Callback
        if (this.onAnalysisComplete) {
            this.onAnalysisComplete(this.uploadId);
        }
    }
    
    /**
     * Handle analysis error
     * @param {string} errorMessage 
     */
    onAnalysisError(errorMessage) {
        if (this.elements.analysisStatus) {
            this.elements.analysisStatus.style.display = 'none';
        }
        
        if (this.elements.errorMessage) {
            this.elements.errorMessage.style.display = 'block';
        }
        if (this.elements.errorTextDetail) {
            this.elements.errorTextDetail.textContent = errorMessage;
        }
    }
    
    /**
     * Cancel upload
     */
    cancelUpload() {
        // Reset form
        this.resetForm();
    }
    
    /**
     * Reset form to initial state
     */
    resetForm() {
        this.selectedFile = null;
        this.uploadId = null;
        this.isUploading = false;
        this.currentTeamSide = null;
        this.submissionNotes = '';
        
        // Reset UI
        if (this.elements.fileInput) {
            this.elements.fileInput.value = '';
        }
        
        if (this.elements.filePreview) {
            this.elements.filePreview.style.display = 'none';
        }
        
        if (this.elements.dropZone) {
            this.elements.dropZone.style.display = 'block';
        }
        
        if (this.elements.uploadProgress) {
            this.elements.uploadProgress.style.display = 'none';
        }
        
        if (this.elements.analysisStatus) {
            this.elements.analysisStatus.style.display = 'none';
        }
        
        if (this.elements.successMessage) {
            this.elements.successMessage.style.display = 'none';
        }
        
        if (this.elements.errorMessage) {
            this.elements.errorMessage.style.display = 'none';
        }
        
        if (this.elements.actionButtons) {
            this.elements.actionButtons.style.display = 'flex';
        }
        
        if (this.elements.teamSelect) {
            this.elements.teamSelect.value = '';
        }
        
        if (this.elements.submissionNotes) {
            this.elements.submissionNotes.value = '';
        }
        
        this.updateNotesCounter();
        this.updateSubmitButton();
        this.hideValidationErrors();
    }
    
    /**
     * Load previous submissions
     */
    async loadPreviousSubmissions() {
        if (!this.elements.submissionList) return;
        
        try {
            const response = await fetch(
                `${this.apiBaseUrl}/competitions/${this.competitionId}/teams/1/memorials`,
                {
                    headers: {
                        'Authorization': `Bearer ${this.getAuthToken()}`
                    }
                }
            );
            
            if (!response.ok) {
                this.showEmptySubmissions();
                return;
            }
            
            const submissions = await response.json();
            this.renderSubmissions(submissions);
            
        } catch (error) {
            console.error('Failed to load submissions:', error);
            this.showEmptySubmissions();
        }
    }
    
    /**
     * Render submissions list
     * @param {Array} submissions 
     */
    renderSubmissions(submissions) {
        if (!this.elements.submissionList) return;
        
        if (!submissions || submissions.length === 0) {
            this.showEmptySubmissions();
            return;
        }
        
        this.elements.submissionList.innerHTML = '';
        
        submissions.forEach(sub => {
            const item = this.createSubmissionItem(sub);
            this.elements.submissionList.appendChild(item);
        });
    }
    
    /**
     * Create submission list item
     * @param {object} submission 
     * @returns {HTMLElement}
     */
    createSubmissionItem(submission) {
        const template = this.elements.template?.content?.cloneNode(true);
        const item = template?.querySelector('.submission-item') || document.createElement('div');
        
        item.className = 'submission-item';
        item.dataset.submissionId = submission.id;
        
        const nameEl = item.querySelector('.submission-name');
        if (nameEl) nameEl.textContent = submission.filename || 'memorial.pdf';
        
        const dateEl = item.querySelector('.submission-date');
        if (dateEl) {
            const date = new Date(submission.uploaded_at);
            dateEl.textContent = date.toLocaleDateString('en-US', {
                month: 'short',
                day: 'numeric',
                year: 'numeric'
            });
        }
        
        const statusEl = item.querySelector('.status-badge');
        if (statusEl) {
            statusEl.className = `status-badge ${submission.status}`;
            statusEl.textContent = submission.status === 'completed' ? 'Analysis Complete' : 
                                   submission.status === 'processing' ? 'Analyzing...' : 'Uploaded';
        }
        
        const viewBtn = item.querySelector('.view-analysis');
        if (viewBtn) {
            viewBtn.addEventListener('click', () => {
                window.location.href = submission.analysis_url || 
                    `memorial-analysis.html?memorial_id=${submission.id}`;
            });
        }
        
        const downloadLink = item.querySelector('.download-link');
        if (downloadLink) {
            downloadLink.href = submission.download_url || '#';
        }
        
        return item;
    }
    
    /**
     * Show empty submissions state
     */
    showEmptySubmissions() {
        if (!this.elements.submissionList) return;
        
        this.elements.submissionList.innerHTML = `
            <div class="submission-item empty">
                <span class="empty-icon">📭</span>
                <span>No submissions yet</span>
            </div>
        `;
    }
    
    /**
     * Get auth token from localStorage
     * @returns {string}
     */
    getAuthToken() {
        return localStorage.getItem('access_token') || '';
    }
    
    /**
     * Cleanup event listeners and resources
     */
    cleanup() {
        if (this.statusPollInterval) {
            clearInterval(this.statusPollInterval);
        }
    }
}

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = MemorialUploadController;
}
