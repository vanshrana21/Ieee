document.addEventListener('DOMContentLoaded', async () => {
    await checkAuth();
    loadCompetitions();
    setupEventListeners();
    
    // Show create button only for admins/faculty
    const userRole = localStorage.getItem('user_role');
    if (['admin', 'faculty', 'super_admin'].includes(userRole)) {
        document.getElementById('create-comp-btn').style.display = 'block';
    }
});

async function loadCompetitions(status = 'all') {
    const token = getAuthToken();
    if (!token) return;
    
    try {
        const url = status === 'all' 
            ? '/api/competitions' 
            : `/api/competitions?status=${status}`;
        
        const response = await fetch(url, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (!response.ok) throw new Error('Failed to load competitions');
        
        const competitions = await response.json();
        renderCompetitions(competitions);
    } catch (error) {
        console.error('Error loading competitions:', error);
        alert('Failed to load competitions. Please try again.');
    }
}

function renderCompetitions(competitions) {
    const container = document.getElementById('competitions-container');
    container.innerHTML = competitions.length === 0 
        ? '<p class="no-competitions">No competitions found. Check back later!</p>'
        : competitions.map(comp => `
            <div class="competition-card ${comp.status}">
                <div class="comp-header">
                    <h3>${comp.title}</h3>
                    <span class="status-badge ${comp.status}">${comp.status.toUpperCase()}</span>
                </div>
                <p class="comp-desc">${comp.description.substring(0, 100)}...</p>
                <div class="comp-meta">
                    <span>📅 ${new Date(comp.start_date).toLocaleDateString()}</span>
                    <span>👥 ${comp.teams_count} teams</span>
                </div>
                <button class="btn btn-secondary join-btn" data-id="${comp.id}">
                    ${comp.status === 'live' ? 'Join Competition' : 'View Details'}
                </button>
            </div>
        `).join('');
}

function setupEventListeners() {
    document.getElementById('status-filter').addEventListener('change', (e) => {
        loadCompetitions(e.target.value);
    });
    
    document.getElementById('create-comp-btn').addEventListener('click', () => {
        document.getElementById('create-comp-modal').style.display = 'block';
    });
    
    document.querySelector('.close').addEventListener('click', () => {
        document.getElementById('create-comp-modal').style.display = 'none';
    });
    
    document.getElementById('create-comp-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        await createCompetition();
    });
    
    document.getElementById('competitions-container').addEventListener('click', (e) => {
        if (e.target.classList.contains('join-btn')) {
            const compId = e.target.dataset.id;
            window.location.href = `create-team.html?comp_id=${compId}`;
        }
    });
}

async function createCompetition() {
    const token = getAuthToken();
    if (!token) return;
    
    const formData = {
        title: document.getElementById('comp-title').value,
        description: document.getElementById('comp-desc').value,
        problem_id: parseInt(document.getElementById('comp-problem').value),
        start_date: document.getElementById('comp-start').value + ':00',
        memorial_deadline: document.getElementById('comp-memorial-deadline').value + ':00',
        oral_start_date: document.getElementById('comp-oral-start').value + ':00',
        oral_end_date: document.getElementById('comp-oral-end').value + ':00',
        max_team_size: 4
    };
    
    try {
        const response = await fetch('/api/competitions', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(formData)
        });
        
        if (!response.ok) throw new Error('Failed to create competition');
        
        alert('Competition created successfully!');
        document.getElementById('create-comp-modal').style.display = 'none';
        loadCompetitions();
    } catch (error) {
        console.error('Error creating competition:', error);
        alert('Failed to create competition. Please try again.');
    }
}
