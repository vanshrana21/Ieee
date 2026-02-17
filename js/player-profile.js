/**
 * Phase 6 — Player Profile Frontend
 */

const API_BASE = '/api/leaderboard';
let ratingChart = null;

// Get user_id from URL params
const urlParams = new URLSearchParams(window.location.search);
const userId = urlParams.get('user_id');

if (!userId) {
    document.body.innerHTML = '<div class="error">No user ID provided</div>';
} else {
    loadPlayerProfile(userId);
}

async function loadPlayerProfile(userId) {
    try {
        const response = await fetch(`${API_BASE}/player/${userId}`, {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('token') || ''}`
            }
        });

        if (!response.ok) {
            if (response.status === 404) {
                document.body.innerHTML = '<div class="error">Player not found</div>';
                return;
            }
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        
        if (!data.success) {
            throw new Error(data.message || 'Failed to load profile');
        }

        renderProfile(data.profile);
    } catch (error) {
        console.error('Failed to load profile:', error);
        document.body.innerHTML = '<div class="error">Failed to load player profile. Please refresh.</div>';
    }
}

function renderProfile(profile) {
    const { user_basic_info, rating_stats, performance_metrics, recent_matches, rating_history_graph_data } = profile;

    // Header
    document.getElementById('player-name').textContent = user_basic_info.username;
    document.getElementById('current-rating').textContent = rating_stats.current_rating || '-';
    document.getElementById('global-rank').textContent = rating_stats.global_rank ? `#${rating_stats.global_rank}` : '-';
    document.getElementById('win-rate').textContent = rating_stats.win_rate ? `${rating_stats.win_rate.toFixed(1)}%` : '-';

    // Performance Overview
    document.getElementById('peak-rating').textContent = rating_stats.peak_rating || '-';
    document.getElementById('total-matches').textContent = rating_stats.total_matches || '0';
    document.getElementById('avg-score').textContent = rating_stats.average_score || '-';
    document.getElementById('percentile-rank').textContent = rating_stats.percentile_rank ? `${rating_stats.percentile_rank}%` : '-';

    // Performance Metrics
    document.getElementById('rating-delta-10').textContent = formatRatingChange(performance_metrics.rating_delta_last_10);
    document.getElementById('strongest-win').textContent = performance_metrics.strongest_win || '-';
    document.getElementById('worst-loss').textContent = performance_metrics.worst_loss || '-';
    document.getElementById('avg-round-score').textContent = performance_metrics.average_round_score || '-';

    // Rating Chart
    renderRatingChart(rating_history_graph_data);

    // Recent Matches
    renderRecentMatches(recent_matches);
}

function renderRatingChart(graphData) {
    const ctx = document.getElementById('rating-chart').getContext('2d');
    
    if (ratingChart) {
        ratingChart.destroy();
    }

    const labels = graphData.map(d => {
        const date = new Date(d.date);
        return date.toLocaleDateString();
    });
    const ratings = graphData.map(d => d.rating);

    ratingChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Rating',
                data: ratings,
                borderColor: '#d4af37',
                backgroundColor: 'rgba(212, 175, 55, 0.1)',
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                y: {
                    beginAtZero: false,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: '#ffffff'
                    }
                },
                x: {
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: '#ffffff'
                    }
                }
            }
        }
    });
}

function renderRecentMatches(matches) {
    const tbody = document.getElementById('recent-matches-body');
    
    if (matches.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="empty">No matches found</td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = matches.map(match => {
        const date = new Date(match.date);
        const resultClass = match.result === 'win' ? 'result-win' : match.result === 'loss' ? 'result-loss' : 'result-draw';
        const ratingChange = formatRatingChange(match.rating_change);
        
        return `
            <tr>
                <td>${date.toLocaleDateString()}</td>
                <td>
                    <a href="/html/player-profile.html?user_id=${match.opponent_id}" class="opponent-link">
                        ${escapeHtml(match.opponent_name)}
                    </a>
                </td>
                <td>${match.opponent_rating_at_match}</td>
                <td class="${resultClass}">${match.result.toUpperCase()}</td>
                <td class="${match.rating_change >= 0 ? 'positive' : 'negative'}">${ratingChange}</td>
                <td>${match.final_match_score.toFixed(2)}</td>
            </tr>
        `;
    }).join('');
}

function formatRatingChange(change) {
    if (change === null || change === undefined) return '-';
    const sign = change >= 0 ? '+' : '';
    return `${sign}${change}`;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
