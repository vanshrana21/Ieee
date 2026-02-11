document.addEventListener('DOMContentLoaded', async () => {
    await checkAuth();
    
    const urlParams = new URLSearchParams(window.location.search);
    const compId = urlParams.get('comp_id');
    
    document.getElementById('create-team-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        await createTeam(compId);
    });
});

async function createTeam(compId) {
    const token = getAuthToken();
    if (!token || !compId) {
        alert('Missing competition ID or authentication');
        return;
    }
    
    const teamName = document.getElementById('team-name').value;
    const side = document.querySelector('input[name="side"]:checked').value;
    
    try {
        const response = await fetch(`/api/competitions/${compId}/teams`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ name: teamName, side: side })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to create team');
        }
        
        const result = await response.json();
        alert('Team created successfully!');
        window.location.href = `competition-dashboard.html?team_id=${result.team_id}&comp_id=${compId}`;
    } catch (error) {
        console.error('Error creating team:', error);
        alert(error.message || 'Failed to create team. Please try again.');
    }
}
