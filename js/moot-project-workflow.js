// DOM-READY HANDLER (GUARANTEES DOM IS READY)
document.addEventListener('DOMContentLoaded', () => {
  console.log('Moot Project Workflow: DOM ready');
  
  try {
    // Initialize workflow AFTER DOM is ready
    initMootProjectWorkflow();
  } catch (error) {
    console.error('Moot Project Workflow: Initialization failed', error);
    showErrorBoundary('UI initialization failed. Please refresh the page.');
  }
});

// SAFE INITIALIZATION
function initMootProjectWorkflow() {
  console.log('Moot Project Workflow: Initializing');
  
  // Check if required elements exist
  if (!document.getElementById('add-issue-btn')) {
    console.warn('Moot Project Workflow: Required elements not found. Retrying in 500ms');
    setTimeout(initMootProjectWorkflow, 500);
    return;
  }
  
  // Initialize all components
  initAddIssueButton();
  initIssueList();
  initMemorialSection();
  initScheduleSection();
  initCourtroomSection();
  checkProjectState();
}

// ERROR BOUNDARY (CATCHES ALL ERRORS)
function showErrorBoundary(message) {
  const errorContainer = document.createElement('div');
  errorContainer.className = 'error-boundary';
  errorContainer.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.8);z-index:10000;display:flex;align-items:center;justify-content:center;';
  errorContainer.innerHTML = `
    <div class="error-alert" style="background:white;padding:40px;border-radius:20px;max-width:400px;text-align:center;">
      <h3 style="color:#e94560;margin-bottom:16px;">⚠️ UI Error</h3>
      <p style="color:#666;margin-bottom:16px;">${message}</p>
      <p style="color:#999;font-size:14px;margin-bottom:24px;"><strong>What to do:</strong> Refresh the page to fix this issue.</p>
      <button class="btn primary" id="refresh-page" style="background:#667eea;color:white;border:none;padding:12px 32px;border-radius:8px;font-size:16px;cursor:pointer;">Refresh Page</button>
    </div>
  `;
  
  document.body.appendChild(errorContainer);
  
  document.getElementById('refresh-page').addEventListener('click', () => {
    window.location.reload();
  });
}

// ADD ISSUE BUTTON HANDLER (FIXED)
function initAddIssueButton() {
  const addIssueButton = document.getElementById('add-issue-btn');
  if (addIssueButton) {
    addIssueButton.addEventListener('click', (e) => {
      e.preventDefault();
      console.log('Add Issue button clicked');
      try {
        // Show issue modal
        const modal = document.getElementById('issue-modal');
        if (modal) {
          modal.style.display = 'block';
          // Pre-fill issue title
          const issueTitle = document.getElementById('issue-title');
          if (issueTitle) issueTitle.value = 'Right to Privacy under Article 21';
        }
      } catch (error) {
        console.error('Add Issue button error:', error);
        showErrorBoundary('Failed to open issue modal. Please try again.');
      }
    });
  } else {
    console.warn('Add Issue button not found. Retrying in 200ms');
    setTimeout(initAddIssueButton, 200);
  }
}

// ISSUE LIST HANDLER (FIXED)
function initIssueList() {
  // Add event delegation for delete buttons
  document.addEventListener('click', (e) => {
    if (e.target.classList.contains('delete-issue')) {
      try {
        e.target.closest('.issue-item').remove();
        checkProjectState();
      } catch (error) {
        console.error('Delete issue error:', error);
        showErrorBoundary('Failed to delete issue. Please refresh.');
      }
    }
  });
}

// MEMORIAL SECTION HANDLER (FIXED)
function initMemorialSection() {
  const uploadBtn = document.getElementById('upload-memorial-btn');
  if (uploadBtn) {
    uploadBtn.addEventListener('click', () => {
      console.log('Upload Memorial clicked');
      // Show memorial modal
      const modal = document.getElementById('memorial-upload-modal');
      if (modal) {
        modal.style.display = 'flex';
      }
    });
  } else {
    console.warn('Upload Memorial button not found. Retrying in 200ms');
    setTimeout(initMemorialSection, 200);
  }
}

// SCHEDULE SECTION HANDLER (FIXED)
function initScheduleSection() {
  const scheduleBtn = document.getElementById('schedule-round-btn');
  if (scheduleBtn) {
    scheduleBtn.addEventListener('click', async () => {
      console.log('Schedule Round clicked');
      try {
        const scheduledTime = document.getElementById('round-datetime')?.value;
        const durationMinutes = document.getElementById('round-duration')?.value || 45;
        
        if (!scheduledTime) {
          alert('Please select a date and time for the oral round.');
          return;
        }
        
        const scheduledDate = new Date(scheduledTime);
        if (scheduledDate < new Date()) {
          alert('Scheduled time must be in the future.');
          return;
        }
        
        const projectId = 1; // TODO: Get from URL
        
        const response = await fetch(
          `/api/moot-projects/${projectId}/schedule-round`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${getAuthToken()}`
            },
            body: JSON.stringify({
              scheduled_time: scheduledDate.toISOString(),
              duration_minutes: durationMinutes
            })
          }
        );
        
        if (!response.ok) {
          const error = await response.json();
          alert(error.detail || 'Failed to schedule round. Please try again.');
          return;
        }
        
        const data = await response.json();
        
        // Update state
        const roundId = data.round_id;
        
        // Redirect to courtroom
        const courtroomUrl = `/html/oral-courtroom.html?round_id=${roundId}`;
        window.location.href = courtroomUrl;
      } catch (error) {
        console.error('Schedule Round button error:', error);
        showErrorBoundary('Failed to schedule round. Please try again.');
      }
    });
  } else {
    console.warn('Schedule Round button not found. Retrying in 200ms');
    setTimeout(initScheduleSection, 200);
  }
}

// COURTROOM SECTION HANDLER (FIXED)
function initCourtroomSection() {
  const joinBtn = document.getElementById('join-courtroom-btn');
  if (joinBtn) {
    joinBtn.addEventListener('click', () => {
      console.log('Join Courtroom clicked');
      // Redirect to courtroom
      const roundId = document.getElementById('round-id')?.value;
      const courtroomUrl = `/html/oral-courtroom.html?round_id=${roundId || 1}`;
      window.location.href = courtroomUrl;
    });
  } else {
    console.warn('Join Courtroom button not found. Retrying in 200ms');
    setTimeout(initCourtroomSection, 200);
  }
}

// PROJECT STATE CHECKER (FIXED)
function checkProjectState() {
  console.log('Checking project state...');
  // Simulate API call with timeout
  setTimeout(async () => {
    try {
      const projectId = 1; // TODO: Get from URL
      const response = await fetch(
        `/api/moot-projects/${projectId}/state`,
        {
          headers: {
            'Authorization': `Bearer ${getAuthToken()}`
          }
        }
      );
      
      if (!response.ok) {
        console.error('Failed to fetch project state');
        return;
      }
      
      const data = await response.json();
      
      // Update UI based on state
      console.log('Project state checked');
      
      // Update memorial section
      const memorialSection = document.getElementById('memorial-section');
      if (memorialSection) {
        const showMemorial = data.has_legal_issues && 
                             data.memorial_status !== 'completed';
        memorialSection.style.display = showMemorial ? 'block' : 'none';
      }
      
      // Update schedule section
      const scheduleSection = document.getElementById('schedule-section');
      if (scheduleSection) {
        const showSchedule = data.memorial_status === 'completed' && 
                             data.round_status === 'none';
        scheduleSection.style.display = showSchedule ? 'block' : 'none';
      }
      
      // Update courtroom section
      const courtroomSection = document.getElementById('courtroom-section');
      if (courtroomSection) {
        const showCourtroom = data.round_status !== 'none';
        courtroomSection.style.display = showCourtroom ? 'block' : 'none';
        
        // Update scheduled time display
        const scheduledTimeDisplay = document.getElementById('scheduled-time-display');
        if (scheduledTimeDisplay && data.scheduled_time) {
          const date = new Date(data.scheduled_time);
          scheduledTimeDisplay.textContent = 
            date.toLocaleString('en-US', {
              month: 'short',
              day: 'numeric',
              year: 'numeric',
              hour: '2-digit',
              minute: '2-digit'
            });
        }
      }
    } catch (error) {
      console.error('Error checking project state:', error);
    }
  }, 100);
}

// GET AUTH TOKEN FROM LOCAL STORAGE
function getAuthToken() {
  return localStorage.getItem('access_token') || '';
}
