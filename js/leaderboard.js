/**
 * Phase 6 — Competitive Leaderboard Frontend
 */

const API_BASE = '/api/leaderboard';
let currentPage = 1;
const limit = 100;

async function loadLeaderboard(page = 1) {
    try {
        const response = await fetch(`${API_BASE}?page=${page}&limit=${limit}`, {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('token') || ''}`
            }
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        
        if (!data.success) {
            throw new Error(data.message || 'Failed to load leaderboard');
        }

        renderLeaderboard(data.leaderboard);
        updatePagination(data.pagination);
        currentPage = page;
    } catch (error) {
        console.error('Failed to load leaderboard:', error);
        document.getElementById('leaderboard-body').innerHTML = `
            <tr>
                <td colspan="7" class="error">Failed to load leaderboard. Please refresh.</td>
            </tr>
        `;
    }
}

function renderLeaderboard(leaderboard) {
    const tbody = document.getElementById('leaderboard-body');
    
    if (leaderboard.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="empty">No players found. Complete your first ranked match to appear!</td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = leaderboard.map(player => {
        const trendIcon = getTrendIcon(player.rating_trend);
        const rankClass = getRankClass(player.rank);
        
        return `
            <tr class="${rankClass}">
                <td class="rank-cell">${player.rank}</td>
                <td class="player-cell">
                    <a href="/html/player-profile.html?user_id=${player.user_id}" class="player-link">
                        ${escapeHtml(player.username)}
                    </a>
                </td>
                <td class="rating-cell">${player.current_rating}</td>
                <td class="peak-cell">${player.peak_rating}</td>
                <td class="record-cell">${player.wins}/${player.losses}/${player.draws}</td>
                <td class="winrate-cell">${player.win_rate.toFixed(1)}%</td>
                <td class="trend-cell">${trendIcon}</td>
            </tr>
        `;
    }).join('');
}

function getTrendIcon(trend) {
    switch (trend) {
        case 'up':
            return '<span class="trend-up">↑</span>';
        case 'down':
            return '<span class="trend-down">↓</span>';
        default:
            return '<span class="trend-neutral">→</span>';
    }
}

function getRankClass(rank) {
    if (rank === 1) return 'rank-gold';
    if (rank === 2) return 'rank-silver';
    if (rank === 3) return 'rank-bronze';
    return '';
}

function updatePagination(pagination) {
    document.getElementById('pagination-text').textContent = 
        `Page ${pagination.page} of ${pagination.total_pages} (${pagination.total_players} players)`;
    
    document.getElementById('prev-btn').disabled = !pagination.has_prev;
    document.getElementById('next-btn').disabled = !pagination.has_next;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Event listeners
document.getElementById('prev-btn').addEventListener('click', () => {
    if (currentPage > 1) {
        loadLeaderboard(currentPage - 1);
    }
});

document.getElementById('next-btn').addEventListener('click', () => {
    loadLeaderboard(currentPage + 1);
});

// Load initial data
loadLeaderboard(1);
