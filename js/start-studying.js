// Subject Data
const subjectData = {
    constitutional: {
        title: "Constitutional Law",
        icon: "⚖️",
        description: "Master the foundation of Indian law",
        topics: [
            {
                number: "Article 14-16",
                title: "Right to Equality",
                description: "Equality before law, prohibition of discrimination, equal opportunity in public employment",
                tags: ["10 marks", "Very Important"]
            },
            {
                number: "Article 19-22",
                title: "Right to Freedom",
                description: "Freedom of speech, assembly, movement, and personal liberty",
                tags: ["10 marks", "Frequently Asked"]
            },
            {
                number: "Article 32",
                title: "Constitutional Remedies",
                description: "Right to constitutional remedies and writs",
                tags: ["5 marks", "Important"]
            },
            {
                number: "Article 368",
                title: "Amendment Procedure",
                description: "Power of Parliament to amend the Constitution",
                tags: ["10 marks", "Critical"]
            },
            {
                number: "Article 356",
                title: "President's Rule",
                description: "Provisions in case of failure of constitutional machinery in states",
                tags: ["5 marks", "Important"]
            },
            {
                number: "Part III",
                title: "Fundamental Rights",
                description: "Complete overview of all fundamental rights",
                tags: ["15 marks", "Very Important"]
            }
        ],
        cases: [
            {
                name: "Kesavananda Bharati v. State of Kerala",
                year: "1973",
                citation: "AIR 1973 SC 1461",
                description: "Established the basic structure doctrine, limiting Parliament's power to amend the Constitution. The court held that while Parliament has wide powers, it cannot alter the basic structure.",
                tags: ["Basic Structure", "Landmark", "Must Know"]
            },
            {
                name: "Maneka Gandhi v. Union of India",
                year: "1978",
                citation: "AIR 1978 SC 597",
                description: "Expanded the scope of Article 21 to include the right to life and personal liberty with dignity. Established that procedure must be just, fair, and reasonable.",
                tags: ["Article 21", "Fundamental Rights", "Critical"]
            },
            {
                name: "Minerva Mills v. Union of India",
                year: "1980",
                citation: "AIR 1980 SC 1789",
                description: "Reinforced the basic structure doctrine and struck down clauses of the 42nd Amendment that gave unlimited amending power to Parliament.",
                tags: ["Basic Structure", "Amendment", "Important"]
            },
            {
                name: "I.R. Coelho v. State of Tamil Nadu",
                year: "2007",
                citation: "AIR 2007 SC 861",
                description: "Clarified that laws placed in the 9th Schedule can be challenged if they violate basic structure or fundamental rights.",
                tags: ["9th Schedule", "Recent", "Important"]
            }
        ],
        questions: [
            {
                type: "Essay",
                marks: 10,
                text: "Discuss the evolution of the basic structure doctrine in India with reference to landmark cases."
            },
            {
                type: "Short Answer",
                marks: 5,
                text: "Explain the relationship between Article 14 and Article 16 of the Indian Constitution."
            },
            {
                type: "Essay",
                marks: 15,
                text: "Critically analyze the expansion of Article 21 through judicial interpretation. Discuss key cases."
            }
        ]
    },
    criminal: {
        title: "Criminal Law",
        icon: "🔨",
        description: "Navigate the Indian Penal Code and criminal procedure",
        topics: [
            {
                number: "Section 300",
                title: "Murder",
                description: "Definition of murder and its essential ingredients",
                tags: ["10 marks", "Very Important"]
            },
            {
                number: "Section 304B",
                title: "Dowry Death",
                description: "Provisions relating to dowry death and presumption",
                tags: ["5 marks", "Important"]
            },
            {
                number: "Section 375",
                title: "Rape",
                description: "Definition of rape and recent amendments",
                tags: ["10 marks", "Critical"]
            },
            {
                number: "Section 34",
                title: "Common Intention",
                description: "Acts done by several persons in furtherance of common intention",
                tags: ["5 marks", "Frequently Asked"]
            },
            {
                number: "Section 420",
                title: "Cheating",
                description: "Cheating and dishonestly inducing delivery of property",
                tags: ["5 marks", "Important"]
            },
            {
                number: "General Exceptions",
                title: "IPC Sections 76-106",
                description: "General exceptions to criminal liability",
                tags: ["10 marks", "Very Important"]
            }
        ],
        cases: [
            {
                name: "State of Maharashtra v. Mayer Hans George",
                year: "1965",
                citation: "AIR 1965 SC 722",
                description: "Distinguished between culpable homicide and murder. Provided clarity on the degree of intention required for murder.",
                tags: ["Murder", "Culpable Homicide", "Landmark"]
            },
            {
                name: "Machhi Singh v. State of Punjab",
                year: "1983",
                citation: "AIR 1983 SC 957",
                description: "Laid down guidelines for awarding death penalty in 'rarest of rare' cases.",
                tags: ["Death Penalty", "Sentencing", "Important"]
            },
            {
                name: "Bachan Singh v. State of Punjab",
                year: "1980",
                citation: "AIR 1980 SC 898",
                description: "Upheld constitutional validity of death penalty and established the 'rarest of rare' doctrine.",
                tags: ["Death Penalty", "Constitution", "Landmark"]
            },
            {
                name: "K.M. Nanavati v. State of Maharashtra",
                year: "1962",
                citation: "AIR 1962 SC 605",
                description: "Famous case on grave and sudden provocation. Discussed the concept of temporary loss of self-control.",
                tags: ["Provocation", "Murder", "Famous"]
            }
        ],
        questions: [
            {
                type: "Essay",
                marks: 10,
                text: "Distinguish between culpable homicide and murder with the help of relevant case laws."
            },
            {
                type: "Short Answer",
                marks: 5,
                text: "What is the 'rarest of rare' doctrine? Discuss its application in death penalty cases."
            },
            {
                type: "Problem",
                marks: 15,
                text: "A, with the intention to kill B, shoots at him. The bullet misses B but hits C who dies. Discuss A's liability under IPC."
            }
        ]
    },
    contract: {
        title: "Contract Law",
        icon: "📝",
        description: "Understand agreements, obligations, and remedies",
        topics: [
            {
                number: "Section 2(h)",
                title: "Contract Definition",
                description: "Definition of contract and essential elements",
                tags: ["5 marks", "Very Important"]
            },
            {
                number: "Section 10",
                title: "Valid Contract",
                description: "What agreements are contracts - essentials of a valid contract",
                tags: ["10 marks", "Critical"]
            },
            {
                number: "Section 23",
                title: "Lawful Consideration",
                description: "What considerations and objects are lawful",
                tags: ["5 marks", "Important"]
            },
            {
                number: "Section 73",
                title: "Compensation for Breach",
                description: "Compensation for loss or damage caused by breach of contract",
                tags: ["10 marks", "Frequently Asked"]
            },
            {
                number: "Section 56",
                title: "Frustration of Contract",
                description: "Agreement to do impossible act - doctrine of frustration",
                tags: ["10 marks", "Important"]
            },
            {
                number: "Section 124-147",
                title: "Indemnity and Guarantee",
                description: "Contracts of indemnity and guarantee",
                tags: ["10 marks", "Very Important"]
            }
        ],
        cases: [
            {
                name: "Carlill v. Carbolic Smoke Ball Co.",
                year: "1893",
                citation: "[1893] 1 QB 256",
                description: "Landmark case on unilateral contracts. Established that advertisements can constitute valid offers if there is clear intention to be bound.",
                tags: ["Offer", "Acceptance", "Landmark"]
            },
            {
                name: "Balfour v. Balfour",
                year: "1919",
                citation: "[1919] 2 KB 571",
                description: "Established that domestic agreements are generally not intended to create legal relations.",
                tags: ["Intention", "Domestic Agreements", "Important"]
            },
            {
                name: "Satyabrata Ghose v. Mugneeram Bangur & Co.",
                year: "1954",
                citation: "AIR 1954 SC 44",
                description: "Indian Supreme Court case on the doctrine of frustration. Discussed impossibility and frustration of contracts.",
                tags: ["Frustration", "Impossibility", "Landmark"]
            },
            {
                name: "Mohori Bibee v. Dharmodas Ghose",
                year: "1903",
                citation: "(1903) 30 Cal 539",
                description: "Held that a contract with a minor is void ab initio and cannot be ratified even after attaining majority.",
                tags: ["Minors", "Capacity", "Important"]
            }
        ],
        questions: [
            {
                type: "Essay",
                marks: 10,
                text: "Explain the essential elements of a valid contract with relevant case laws."
            },
            {
                type: "Short Answer",
                marks: 5,
                text: "Distinguish between indemnity and guarantee."
            },
            {
                type: "Problem",
                marks: 15,
                text: "A agrees to sell his car to B for Rs. 5 lakhs. Before the sale is completed, the car is destroyed by fire without fault of either party. Discuss the legal position."
            }
        ]
    }
};

// DOM Elements
const subjectSelection = document.getElementById('subject-selection');
const studyHub = document.getElementById('study-hub');
const subjectCards = document.querySelectorAll('.subject-card');
const changeSubjectBtn = document.getElementById('changeSubjectBtn');
const optionCards = document.querySelectorAll('.option-card');

// Current state
let currentSubject = null;
let currentOption = 'concepts';

// Initialize
function init() {
    // Add click handlers to subject cards
    subjectCards.forEach(card => {
        card.addEventListener('click', () => {
            const subject = card.dataset.subject;
            if (!card.classList.contains('coming-soon')) {
                selectSubject(subject);
            }
        });
    });

    // Add click handler to change subject button
    changeSubjectBtn.addEventListener('click', () => {
        showSubjectSelection();
    });

    // Add click handlers to study option cards
    optionCards.forEach(card => {
        card.addEventListener('click', () => {
            const option = card.dataset.option;
            selectStudyOption(option);
        });
    });
}

// Select a subject
function selectSubject(subject) {
    if (!subjectData[subject]) return;

    currentSubject = subject;
    const data = subjectData[subject];

    // Update hub header
    document.getElementById('currentSubjectIcon').textContent = data.icon;
    document.getElementById('currentSubjectTitle').textContent = data.title;
    document.getElementById('currentSubjectDesc').textContent = data.description;

    // Hide subject selection, show study hub
    subjectSelection.classList.add('hidden');
    studyHub.classList.remove('hidden');

    // Load default content (concepts)
    selectStudyOption('concepts');
}

// Show subject selection
function showSubjectSelection() {
    studyHub.classList.add('hidden');
    subjectSelection.classList.remove('hidden');
    currentSubject = null;
}

// Select study option
function selectStudyOption(option) {
    if (!currentSubject) return;

    currentOption = option;

    // Update active state on option cards
    optionCards.forEach(card => {
        if (card.dataset.option === option) {
            card.classList.add('active');
        } else {
            card.classList.remove('active');
        }
    });

    // Hide all content sections
    const contentSections = document.querySelectorAll('.content-section');
    contentSections.forEach(section => section.classList.add('hidden'));

    // Show selected content section and load data
    switch (option) {
        case 'concepts':
            document.getElementById('conceptsContent').classList.remove('hidden');
            loadTopics();
            break;
        case 'cases':
            document.getElementById('casesContent').classList.remove('hidden');
            loadCases();
            break;
        case 'practice':
            document.getElementById('practiceContent').classList.remove('hidden');
            loadQuestions();
            break;
        case 'notes':
            document.getElementById('notesContent').classList.remove('hidden');
            loadNotes();
            break;
    }
}

// Load topics
function loadTopics() {
    const data = subjectData[currentSubject];
    const topicsGrid = document.getElementById('topicsGrid');

    topicsGrid.innerHTML = data.topics.map(topic => `
        <div class="topic-card">
            <div class="topic-number">${topic.number}</div>
            <h4>${topic.title}</h4>
            <p>${topic.description}</p>
            <div class="topic-meta">
                ${topic.tags.map(tag => `<span class="meta-tag">${tag}</span>`).join('')}
            </div>
        </div>
    `).join('');
}

// Load cases
function loadCases() {
    const data = subjectData[currentSubject];
    const casesList = document.getElementById('casesList');

    casesList.innerHTML = data.cases.map(caseItem => `
        <div class="case-card">
            <div class="case-header">
                <div>
                    <h4>${caseItem.name}</h4>
                    <div class="case-citation">${caseItem.citation}</div>
                </div>
                <span class="case-year">${caseItem.year}</span>
            </div>
            <p>${caseItem.description}</p>
            <div class="case-tags">
                ${caseItem.tags.map(tag => `<span class="case-tag">${tag}</span>`).join('')}
            </div>
        </div>
    `).join('');
}

// Load questions
function loadQuestions() {
    const data = subjectData[currentSubject];
    const practiceQuestions = document.getElementById('practiceQuestions');

    practiceQuestions.innerHTML = data.questions.map((question, index) => `
        <div class="question-card">
            <div class="question-header">
                <span class="question-type">${question.type}</span>
                <span class="question-marks">${question.marks} Marks</span>
            </div>
            <div class="question-text">Q${index + 1}. ${question.text}</div>
            <div class="question-footer">
                <button class="answer-btn" onclick="startAnswer(${index})">Start Writing Answer</button>
                <button class="hint-btn" onclick="showHint(${index})">Show Hint</button>
            </div>
        </div>
    `).join('');
}

// Load notes
function loadNotes() {
    // Empty state is already in HTML
    // In a real app, this would load saved notes
}

// Handle answer writing
function startAnswer(questionIndex) {
    const data = subjectData[currentSubject];
    const question = data.questions[questionIndex];
    
    // In a real app, this would open an answer writing interface
    // For now, we'll show a simple confirmation
    const card = event.target.closest('.question-card');
    card.style.borderColor = 'var(--success-green)';
    card.style.background = 'var(--bg-white)';
    
    setTimeout(() => {
        card.style.borderColor = 'var(--border-gray)';
        card.style.background = 'var(--bg-gray)';
    }, 1000);
}

// Show hint
function showHint(questionIndex) {
    const data = subjectData[currentSubject];
    const question = data.questions[questionIndex];
    
    // In a real app, this would show relevant hints or outline
    const card = event.target.closest('.question-card');
    
    // Create hint element if it doesn't exist
    let hintElement = card.querySelector('.hint-display');
    if (!hintElement) {
        hintElement = document.createElement('div');
        hintElement.className = 'hint-display';
        hintElement.style.cssText = `
            margin-top: 16px;
            padding: 16px;
            background: var(--secondary-blue);
            border-left: 4px solid var(--primary-blue);
            border-radius: 8px;
            font-size: 14px;
            color: var(--text-dark);
        `;
        
        const hints = {
            0: "Structure: Introduction → Basic Structure Doctrine → Key Cases (Kesavananda, Minerva Mills) → Impact → Conclusion",
            1: "Key Points: Article 14 is general, Article 16 is specific. Discuss equality vs equal opportunity. Mention classification doctrine.",
            2: "Cover: Original scope → Maneka Gandhi case → Recent expansions (privacy, environment, etc.) → Impact on rights"
        };
        
        hintElement.innerHTML = `<strong>💡 Hint:</strong> ${hints[questionIndex] || "Break down the question into key components and address each systematically with case law support."}`;
        card.appendChild(hintElement);
    } else {
        hintElement.remove();
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', init);