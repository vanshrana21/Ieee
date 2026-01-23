(function() {
    'use strict';

    const TOPICS = [
        "Judicial Review violates Parliamentary Sovereignty",
        "Article 21 should include the Right to Privacy",
        "Capital Punishment should be abolished",
        "Uniform Civil Code is necessary in India",
        "Judicial Activism weakens democracy",
        "Live-in relationships deserve legal protection",
        "Plea Bargaining compromises justice",
        "Collegium system needs reform"
    ];

    const AI_RESPONSES = {
        for: [
            [
                "The proposition raises an interesting point. However, we must consider that constitutional safeguards exist precisely to prevent abuse. The framers anticipated such challenges and built in protective mechanisms through Articles 13 and 32.",
                "While my opponent makes a compelling argument, the historical context shows that similar provisions in other democracies have strengthened rather than weakened governance. The Kesavananda Bharati case established clear boundaries.",
                "In conclusion, the evidence suggests that rather than being problematic, this constitutional provision has evolved through judicial interpretation to serve the democratic ideal. The balance of power remains intact."
            ],
            [
                "The argument presented overlooks key precedents. In Maneka Gandhi v. Union of India, the Supreme Court expanded the interpretation precisely because narrow readings failed citizens.",
                "Furthermore, my learned friend ignores that fundamental rights are not absolute. Reasonable restrictions exist under Article 19(2). The real question is proportionality, not existence.",
                "To summarize, the legal framework already accounts for these concerns. What we need is not rejection but refinement of application."
            ]
        ],
        against: [
            [
                "My opponent's position, while passionate, fails to address the core legal issue. The doctrine of separation of powers, as articulated in Minerva Mills, clearly establishes that no single branch may claim supremacy.",
                "The argument ignores practical realities. Across 75 years of constitutional history, the system has self-corrected. This isn't failure—it's evolution as envisioned by our constitutional architects.",
                "In final analysis, the position against fails because it proposes solutions to problems that existing mechanisms already address. Let us not fix what isn't broken."
            ],
            [
                "I appreciate my opponent's enthusiasm, but legal analysis requires precision. The cited cases actually support the contrary position when read in full context.",
                "Moreover, comparative jurisprudence from the UK and US shows that similar concerns were raised and subsequently resolved through incremental reform, not wholesale rejection.",
                "To conclude, the weight of authority, precedent, and practical experience all point to maintaining the current framework with targeted improvements."
            ]
        ]
    };

    const FEEDBACK_DATA = {
        strengths: [
            "Clear articulation of legal principles",
            "Good use of logical structure",
            "Maintained focus on the core issue",
            "Demonstrated understanding of constitutional concepts"
        ],
        improvements: [
            "Cite more specific case laws to strengthen arguments",
            "Develop counter-arguments more thoroughly",
            "Strengthen concluding statements",
            "Use IRAC format more consistently"
        ],
        tips: [
            "In exams, present arguments in IRAC format: Issue, Rule, Application, Conclusion.",
            "Always acknowledge the opposing view before refuting it—this shows balanced thinking.",
            "Time management is crucial: allocate first 2 minutes to planning your argument structure.",
            "Use leading cases as anchors, then build your reasoning around them.",
            "Conclude with a clear, decisive statement that ties back to your opening position."
        ]
    };

    const state = {
        currentTopic: null,
        userSide: null,
        currentRound: 1,
        totalRounds: 3,
        isUserTurn: true,
        userArguments: [],
        aiArguments: [],
        prepTimerId: null,
        debateTimerId: null,
        responseSetIndex: 0,
        currentStep: 1
    };

    function showScreen(screenId) {
        document.querySelectorAll('.screen').forEach(s => s.classList.add('hidden'));
        document.getElementById(screenId).classList.remove('hidden');
    }

    function updateProgressSteps(step) {
        state.currentStep = step;
        document.querySelectorAll('.step').forEach((s, i) => {
            const stepNum = i + 1;
            s.classList.remove('active', 'completed');
            if (stepNum === step) s.classList.add('active');
            else if (stepNum < step) s.classList.add('completed');
        });
    }

    function updateContextPanel() {
        const panel = document.getElementById('contextPanel');
        const topicEl = document.getElementById('contextTopic');
        const sideEl = document.getElementById('contextSide');

        if (state.currentTopic) {
            panel.classList.remove('hidden');
            topicEl.textContent = state.currentTopic.length > 35 
                ? state.currentTopic.substring(0, 35) + '…' 
                : state.currentTopic;
            topicEl.title = state.currentTopic;
            
            if (state.userSide) {
                sideEl.textContent = state.userSide === 'for' ? 'FOR' : 'AGAINST';
                sideEl.className = `context-value context-side ${state.userSide}`;
            }
        } else {
            panel.classList.add('hidden');
        }
    }

    function getRandomItem(arr) {
        return arr[Math.floor(Math.random() * arr.length)];
    }

    function startDebate() {
        state.currentTopic = getRandomItem(TOPICS);
        state.userSide = Math.random() > 0.5 ? 'for' : 'against';
        state.responseSetIndex = Math.floor(Math.random() * 2);

        document.getElementById('debateTopic').textContent = state.currentTopic;
        
        const sideEl = document.getElementById('assignedSide');
        sideEl.textContent = state.userSide === 'for' ? 'FOR the motion' : 'AGAINST the motion';
        sideEl.className = `side-badge ${state.userSide}`;

        updateProgressSteps(2);
        updateContextPanel();
        showScreen('topicScreen');
    }

    function beginPrepTime() {
        document.getElementById('prepTopicText').textContent = state.currentTopic;
        document.getElementById('prepSideText').textContent = state.userSide === 'for' ? 'FOR' : 'AGAINST';
        document.getElementById('prepNotes').value = '';
        
        updateProgressSteps(3);
        showScreen('prepScreen');

        let seconds = 60;
        const countdownEl = document.getElementById('prepCountdown');

        state.prepTimerId = setInterval(() => {
            seconds--;
            const mins = Math.floor(seconds / 60);
            const secs = seconds % 60;
            countdownEl.textContent = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;

            if (seconds <= 0) {
                clearInterval(state.prepTimerId);
                startDebateRound();
            }
        }, 1000);
    }

    function skipPrep() {
        if (state.prepTimerId) clearInterval(state.prepTimerId);
        startDebateRound();
    }

    function startDebateRound() {
        state.currentRound = 1;
        state.isUserTurn = true;
        state.userArguments = [];
        state.aiArguments = [];

        const userBadge = document.getElementById('userSideBadge');
        userBadge.textContent = state.userSide === 'for' ? 'FOR' : 'AGAINST';
        userBadge.className = `mini-badge ${state.userSide}`;

        const aiBadge = document.getElementById('aiSideBadge');
        aiBadge.textContent = state.userSide === 'for' ? 'AGAINST' : 'FOR';
        aiBadge.className = `mini-badge ${state.userSide === 'for' ? 'against' : 'for'}`;

        document.getElementById('userArguments').innerHTML = '';
        document.getElementById('aiArguments').innerHTML = '';

        updateProgressSteps(4);
        showScreen('debateScreen');
        updateDebateUI();
        startTurnTimer();
    }

    function updateDebateUI() {
        document.getElementById('roundIndicator').textContent = `Round ${state.currentRound} of ${state.totalRounds}`;
        
        const turnBadge = document.getElementById('turnIndicator');
        turnBadge.textContent = state.isUserTurn ? 'Your Turn' : "Opponent's Turn";
        turnBadge.className = state.isUserTurn ? 'turn-badge' : 'turn-badge opponent';

        document.getElementById('inputArea').classList.toggle('hidden', !state.isUserTurn);
        document.getElementById('waitingArea').classList.toggle('hidden', state.isUserTurn);
        document.getElementById('argumentInput').value = '';
        document.getElementById('submitArgument').disabled = false;
    }

    function startTurnTimer() {
        let seconds = 45;
        const countdownEl = document.getElementById('debateCountdown');

        if (state.debateTimerId) clearInterval(state.debateTimerId);

        state.debateTimerId = setInterval(() => {
            seconds--;
            countdownEl.textContent = `00:${String(seconds).padStart(2, '0')}`;

            if (seconds <= 0) {
                clearInterval(state.debateTimerId);
                if (state.isUserTurn) {
                    submitArgument(true);
                }
            }
        }, 1000);
    }

    function submitArgument(timeout = false) {
        if (!state.isUserTurn) return;

        const input = document.getElementById('argumentInput');
        const text = input.value.trim();

        if (!text && !timeout) return;

        const argument = text || "(No response submitted)";
        state.userArguments.push(argument);
        
        const userArgsEl = document.getElementById('userArguments');
        userArgsEl.innerHTML += `<div class="argument-bubble">${escapeHtml(argument)}</div>`;
        userArgsEl.scrollTop = userArgsEl.scrollHeight;

        document.getElementById('submitArgument').disabled = true;
        clearInterval(state.debateTimerId);

        state.isUserTurn = false;
        updateDebateUI();

        setTimeout(() => {
            generateAIResponse();
        }, 1500);
    }

    function generateAIResponse() {
        const aiSide = state.userSide === 'for' ? 'against' : 'for';
        const responses = AI_RESPONSES[aiSide][state.responseSetIndex];
        const response = responses[state.currentRound - 1] || responses[0];

        state.aiArguments.push(response);

        const aiArgsEl = document.getElementById('aiArguments');
        aiArgsEl.innerHTML += `<div class="argument-bubble">${escapeHtml(response)}</div>`;
        aiArgsEl.scrollTop = aiArgsEl.scrollHeight;

        setTimeout(() => {
            if (state.currentRound >= state.totalRounds) {
                endDebate();
            } else {
                state.currentRound++;
                state.isUserTurn = true;
                updateDebateUI();
                startTurnTimer();
            }
        }, 1000);
    }

    function endDebate() {
        clearInterval(state.debateTimerId);

        const score = (6 + Math.random() * 3).toFixed(1);
        document.getElementById('overallScore').textContent = score;

        const strengthsList = document.getElementById('strengthsList');
        const shuffledStrengths = [...FEEDBACK_DATA.strengths].sort(() => Math.random() - 0.5).slice(0, 3);
        strengthsList.innerHTML = shuffledStrengths.map(s => `<li>${s}</li>`).join('');

        const improvementsList = document.getElementById('improvementsList');
        const shuffledImprovements = [...FEEDBACK_DATA.improvements].sort(() => Math.random() - 0.5).slice(0, 3);
        improvementsList.innerHTML = shuffledImprovements.map(i => `<li>${i}</li>`).join('');

        document.getElementById('examTipText').textContent = getRandomItem(FEEDBACK_DATA.tips);

        updateProgressSteps(5);
        showScreen('feedbackScreen');
    }

    function restart() {
        state.currentTopic = null;
        state.userSide = null;
        state.currentRound = 1;
        state.isUserTurn = true;
        state.userArguments = [];
        state.aiArguments = [];

        if (state.prepTimerId) clearInterval(state.prepTimerId);
        if (state.debateTimerId) clearInterval(state.debateTimerId);

        updateProgressSteps(1);
        updateContextPanel();
        showScreen('entryScreen');
    }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    window.debateApp = {
        startDebate,
        beginPrepTime,
        skipPrep,
        submitArgument: () => submitArgument(false),
        restart
    };
})();
