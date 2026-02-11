document.addEventListener('DOMContentLoaded', async () => {
    await checkAuth();
    setupUploadListeners();
    startCountdown();
});

function setupUploadListeners() {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('memorial-file');
    const browseBtn = document.getElementById('browse-btn');
    
    browseBtn.addEventListener('click', () => fileInput.click());
    
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileUpload(e.target.files[0]);
        }
    });
    
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });
    
    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });
    
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            handleFileUpload(e.dataTransfer.files[0]);
        }
    });
}

async function handleFileUpload(file) {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
        alert('Only PDF files are allowed');
        return;
    }
    
    if (file.size > 5 * 1024 * 1024) {
        alert('File size exceeds 5MB limit');
        return;
    }
    
    const urlParams = new URLSearchParams(window.location.search);
    const compId = urlParams.get('comp_id');
    const teamId = urlParams.get('team_id');
    
    if (!compId || !teamId) {
        alert('Missing competition or team ID');
        return;
    }
    
    const token = getAuthToken();
    if (!token) {
        alert('Please login first');
        return;
    }
    
    const formData = new FormData();
    formData.append('file', file);
    
    document.getElementById('drop-zone').style.display = 'none';
    document.getElementById('upload-status').style.display = 'block';
    
    try {
        const response = await fetch(`/api/competitions/${compId}/teams/${teamId}/memorials`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            },
            body: formData
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Upload failed');
        }
        
        const result = await response.json();
        document.getElementById('status-text').textContent = 'Memorial submitted!';
        document.getElementById('status-detail').textContent = 'AI analysis complete. View your results below.';
        
        // Poll for results
        pollForResults(compId, teamId);
    } catch (error) {
        console.error('Upload error:', error);
        alert(error.message || 'Upload failed. Please try again.');
        document.getElementById('drop-zone').style.display = 'block';
        document.getElementById('upload-status').style.display = 'none';
    }
}

async function pollForResults(compId, teamId) {
    const token = getAuthToken();
    
    const checkStatus = async () => {
        try {
            const response = await fetch(`/api/competitions/${compId}/teams/${teamId}/memorials`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            
            if (!response.ok) return false;
            
            const memorials = await response.json();
            if (memorials.length > 0 && memorials[0].status === 'accepted') {
                showResults(memorials[0]);
                return true;
            }
            return false;
        } catch (error) {
            console.error('Poll error:', error);
            return false;
        }
    };
    
    // Check every 3 seconds for up to 2 minutes
    for (let i = 0; i < 40; i++) {
        const complete = await checkStatus();
        if (complete) break;
        await new Promise(r => setTimeout(r, 3000));
    }
}

function showResults(memorial) {
    document.getElementById('upload-status').style.display = 'none';
    document.getElementById('results-container').style.display = 'block';
    
    if (memorial.score_overall) {
        document.getElementById('overall-score').textContent = `${memorial.score_overall}/5.0`;
    }
    
    // Render badges
    if (memorial.badges_earned && memorial.badges_earned.length > 0) {
        const badgesContainer = document.querySelector('.badges-container');
        badgesContainer.innerHTML = memorial.badges_earned.map(badge => 
            `<div class="badge">${badge.replace(/_/g, ' ')}</div>`
        ).join('');
    }
}

function startCountdown() {
    // Simple countdown placeholder - would be populated from competition data
    const deadline = new Date('2026-02-15T23:59:59');
    
    const updateTimer = () => {
        const now = new Date();
        const diff = deadline - now;
        
        if (diff <= 0) {
            document.getElementById('countdown-timer').textContent = 'Deadline passed';
            return;
        }
        
        const days = Math.floor(diff / (1000 * 60 * 60 * 24));
        const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
        const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
        
        document.getElementById('countdown-timer').textContent = 
            `${days}d ${hours}h ${minutes}m remaining`;
    };
    
    updateTimer();
    setInterval(updateTimer, 60000);
}
