(function() {
    const TICKER_DATA = [
        {
            id: "case-simplifier",
            title: "Case Simplifier",
            subtitle: "Simplified judgments & exam-ready breakdown",
            icon: "assets/icons/case-simplifier.svg",
            href: "./case-simplifier.html",
            ariaLabel: "Open Case Simplifier"
        },
        {
            id: "debate",
            title: "Debate",
            subtitle: "Live argument practice",
            icon: "assets/icons/debate.svg",
            href: "./debate.html",
            ariaLabel: "Open Debate"
        },
        {
            id: "start-studying",
            title: "Start Studying",
            subtitle: "Open subject lessons",
            icon: "assets/icons/study.svg",
            href: "./start-studying.html",
            ariaLabel: "Start Studying"
        },
        {
            id: "my-notes",
            title: "My Notes",
            subtitle: "Create & sync notes",
            icon: "assets/icons/notes.svg",
            href: "./my-notes.html",
            ariaLabel: "Open My Notes"
        }
    ];

    function initTicker() {
        const track = document.getElementById('tickerTrack');
        if (!track) return;

        // Clear existing
        track.innerHTML = '';

        // Create one set of items
        const renderItems = (items) => {
            items.forEach(item => {
                const anchor = document.createElement('a');
                anchor.href = item.href;
                anchor.className = 'quick-action-item';
                anchor.setAttribute('role', 'link');
                anchor.setAttribute('aria-label', item.ariaLabel);

                anchor.innerHTML = `
                    <div class="qa-icon" aria-hidden="true">
                        <img src="${item.icon}" alt="" width="24" height="24" onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%2224%22 height=%2224%22 viewBox=%220 0 24 24%22 fill=%22none%22 stroke=%22%230066FF%22 stroke-width=%222%22 stroke-linecap=%22round%22 stroke-linejoin=%22round%22%3E%3Cpath d=%22M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z%22/%3E%3Cpolyline points=%2214 2 14 8 20 8%22/%3E%3C/svg%3E'">
                    </div>
                    <div class="qa-info">
                        <span class="qa-title">${item.title}</span>
                        <span class="qa-subtitle">${item.subtitle}</span>
                    </div>
                `;

                track.appendChild(anchor);
            });
        };

        // Render twice for infinite loop
        renderItems(TICKER_DATA);
        renderItems(TICKER_DATA);

        if (window.DEBUG_UI) {
            console.log('Ticker initialized with', TICKER_DATA.length, 'items');
        }
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initTicker);
    } else {
        initTicker();
    }
})();
