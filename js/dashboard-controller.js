document.addEventListener('DOMContentLoaded', async () => {
    await checkAuth();
    
    const urlParams = new URLSearchParams(window.location.search);
    const teamId = urlParams.get('team_id');
    const compId = urlParams.get('comp_id');
    
    if (teamId && compId) {
        loadTeamDashboard(teamId, compId);
    }
});

async function loadTeamDashboard(teamId, compId) {
    const token = getAuthToken();
    if (!token) return;
    
    try {
        // Load team info
        const teamResponse = await fetch(`/api/teams/${teamId}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (teamResponse.ok) {
            const team = await teamResponse.json();
            document.getElementById('team-name').textContent = team.name || 'Unknown Team';
            document.getElementById('team-side').textContent = team.side || 'Unknown';
        }
        
        // Load memorials
        const memorialResponse = await fetch(`/api/competitions/${compId}/teams/${teamId}/memorials`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (memorialResponse.ok) {
            const memorials = await memorialResponse.json();
            if (memorials.length > 0) {
                const latest = memorials[0];
                updateMemorialStatus(latest);
            }
        }
    } catch (error) {
        console.error('Error loading dashboard:', error);
    }
}

function updateMemorialStatus(memorial) {
    const statusEl = document.getElementById('memorial-status');
    statusEl.textContent = memorial.status;
    statusEl.className = `status-badge ${memorial.status}`;
    
    if (memorial.score_overall) {
        document.getElementById('irac-score').textContent = memorial.score_irac || '--';
        document.getElementById('citation-score').textContent = memorial.score_citation || '--';
        document.getElementById('reasoning-score').textContent = memorial.score_structure || '--';
    }
    
    // Update badges
    if (memorial.badges_earned && memorial.badges_earned.length > 0) {
        const badgesContainer = document.querySelector('.badges-container');
        badgesContainer.innerHTML = memorial.badges_earned.map(badge => 
            `<div class="badge">${badge.replace(/_/g, ' ')}</div>`
        ).join('');
    }
}
