// Global state
let currentSubject = '';
let currentMode = '';

// Static data for different subjects
const subjectData = {
    constitutional: {
        name: 'Constitutional Law',
        concepts: [
            {
                title: 'Fundamental Rights (Articles 12-35)',
                description: 'Basic human rights guaranteed by the Constitution including Right to Equality, Freedom, and Life.',
                details: 'Covers Articles 14-32 including equality before law, freedom of speech, protection of life and personal liberty, and constitutional remedies.'
            },
            {
                title: 'Directive Principles of State Policy (Articles 36-51)',
                description: 'Guidelines for the State to establish social and economic democracy.',
                details: 'Non-justiciable principles including right to work, education, public assistance, and organization of village panchayats.'
            },
            {
                title: 'Basic Structure Doctrine',
                description: 'Constitutional principles that cannot be altered by Parliament through amendments.',
                details: 'Established in Kesavananda Bharati case - includes supremacy of Constitution, rule of law, independence of judiciary, and federal character.'
            },
            {
                title: 'Separation of Powers',
                description: 'Division of governmental powers among Legislature, Executive, and Judiciary.',
                details: 'Ensures checks and balances in the system to prevent concentration of power and protect citizens\' rights.'
            },
            {
                title: 'Judicial Review (Article 13, 32, 136, 226)',
                description: 'Power of courts to examine the constitutionality of laws and executive actions.',
                details: 'Supreme Court and High Courts can strike down laws that violate fundamental rights or constitutional provisions.'
            }
        ],
        cases: [
            {
                title: 'Kesavananda Bharati v. State of Kerala (1973)',
                year: '1973',
                importance: 'Landmark - Basic Structure',
                description: 'Established the Basic Structure Doctrine - Parliament cannot destroy the basic features of the Constitution.',
                ratio: 'While Parliament has wide amending powers under Article 368, it cannot alter the basic structure of the Constitution.'
            },
            {
                title: 'Maneka Gandhi v. Union of India (1978)',
                year: '1978',
                importance: 'Fundamental Rights',
                description: 'Expanded the scope of Article 21 - Right to Life and Personal Liberty includes right to travel abroad.',
                ratio: 'Procedure established by law must be just, fair and reasonable. Article 21 is the heart of fundamental rights.'
            },
            {
                title: 'ADM Jabalpur v. Shivkant Shukla (1976)',
                year: '1976',
                importance: 'Emergency Powers',
                description: 'During Emergency, right to move court for enforcement of Articles 14, 21, 22 was suspended.',
                ratio: 'Criticized decision - held that during emergency proclamation, detention without trial is valid.'
            },
            {
                title: 'Minerva Mills v. Union of India (1980)',
                year: '1980',
                importance: 'Parliamentary Limits',
                description: 'Struck down amendments that gave unlimited amending power to Parliament.',
                ratio: 'Limited government, judicial review, and harmony between fundamental rights and directive principles are part of basic structure.'
            }
        ],
        questions: [
            {
                title: 'Explain the Basic Structure Doctrine with reference to Kesavananda Bharati case.',
                marks: 10,
                difficulty: 'Medium',
                hint: 'Cover: Origin, key features of basic structure, importance, and subsequent developments.'
            },
            {
                title: 'Discuss the evolution of Article 21 - Right to Life and Personal Liberty.',
                marks: 10,
                difficulty: 'Medium',
                hint: 'Include: Original scope, Maneka Gandhi case, expansion through judicial interpretation, and important derived rights.'
            },
            {
                title: 'What is Judicial Review? Explain its scope and significance.',
                marks: 5,
                difficulty: 'Easy',
                hint: 'Define judicial review, mention relevant articles, and explain its role in protecting constitutional supremacy.'
            },
            {
                title: 'Differentiate between Fundamental Rights and Directive Principles.',
                marks: 5,
                difficulty: 'Easy',
                hint: 'Compare: Justiciability, nature, purpose, and their relationship as per Minerva Mills case.'
            }
        ]
    },
    criminal: {
        name: 'Criminal Law',
        concepts: [
            {
                title: 'Mens Rea (Guilty Mind)',
                description: 'Mental element or criminal intent required for an offense.',
                details: 'A person cannot be held guilty unless the act was done with a guilty mind. Exceptions exist for strict liability offenses.'
            },
            {
                title: 'Actus Reus (Guilty Act)',
                description: 'Physical element of a crime - the actual conduct that is prohibited.',
                details: 'The prohibited act or omission that constitutes the physical component of a crime, must be voluntary.'
            },
            {
                title: 'General Exceptions (IPC Sections 76-106)',
                description: 'Circumstances under which an act is not considered an offense.',
                details: 'Includes mistake of fact, judicial acts, accident, necessity, infancy, insanity, intoxication, and private defense.'
            },
            {
                title: 'Right of Private Defense (Sections 96-106)',
                description: 'Right to defend oneself or others against unlawful aggression.',
                details: 'Can extend to causing death in defense of body (grave danger) or property (specific situations like robbery, house-breaking at night).'
            },
            {
                title: 'Abetment (Sections 107-120)',
                description: 'Instigating, engaging in conspiracy, or aiding commission of an offense.',
                details: 'Abettor is liable even if the abetted offense is not committed, under certain circumstances.'
            }
        ],
        cases: [
            {
                title: 'State of Maharashtra v. Mayer Hans George (1965)',
                year: '1965',
                importance: 'Mens Rea',
                description: 'Possession of foreign currency without declaration - strict liability offense.',
                ratio: 'For strict liability offenses, proof of mens rea is not required. Mere commission of prohibited act is sufficient.'
            },
            {
                title: 'K.M. Nanavati v. State of Maharashtra (1962)',
                year: '1962',
                importance: 'Murder - Provocation',
                description: 'Naval officer killed wife\'s lover - whether grave and sudden provocation existed.',
                ratio: 'Provocation must be grave and sudden. Time gap between provocation and act negates the defense.'
            },
            {
                title: 'Vidhya Singh v. State of MP (1971)',
                year: '1971',
                importance: 'Private Defense',
                description: 'Limits of right of private defense of property.',
                ratio: 'Right to private defense is available only when there is reasonable apprehension of danger from unlawful aggression.'
            }
        ],
        questions: [
            {
                title: 'Explain the concept of Mens Rea with exceptions.',
                marks: 10,
                difficulty: 'Medium',
                hint: 'Define mens rea, explain its importance, discuss strict liability and absolute liability as exceptions with cases.'
            },
            {
                title: 'Discuss the Right of Private Defense under IPC.',
                marks: 10,
                difficulty: 'Medium',
                hint: 'Cover: When it arises, extent (body vs property), when it extends to causing death, and limitations.'
            },
            {
                title: 'What are General Exceptions under IPC?',
                marks: 5,
                difficulty: 'Easy',
                hint: 'List and briefly explain sections 76-106 including mistake, accident, necessity, insanity, intoxication, private defense.'
            }
        ]
    },
    contract: {
        name: 'Contract Law',
        concepts: [
            {
                title: 'Essentials of a Valid Contract (Section 10)',
                description: 'Requirements for an agreement to be legally enforceable.',
                details: 'Free consent, competent parties, lawful consideration and object, not expressly declared void, certainty of terms.'
            },
            {
                title: 'Offer and Acceptance (Sections 2(a), 2(b))',
                description: 'Proposal and its acceptance form the basis of an agreement.',
                details: 'Offer must be clear, communicated, and made with intention to create legal relations. Acceptance must be absolute and unconditional.'
            },
            {
                title: 'Consideration (Sections 2(d), 25)',
                description: 'Something in return - price paid for the promise.',
                details: 'Must move at the desire of promisor, can move from any person, can be past/present/future, need not be adequate but must be real.'
            },
            {
                title: 'Breach of Contract (Section 73)',
                description: 'Failure to perform contractual obligations.',
                details: 'Can be actual breach or anticipatory breach. Aggrieved party entitled to damages, specific performance, or injunction.'
            },
            {
                title: 'Discharge of Contract',
                description: 'Ways in which contractual obligations come to an end.',
                details: 'By performance, agreement, impossibility, lapse of time, operation of law, or breach.'
            }
        ],
        cases: [
            {
                title: 'Carlill v. Carbolic Smoke Ball Co. (1893)',
                year: '1893',
                importance: 'Unilateral Contract',
                description: 'Advertisement offering reward was a unilateral contract - performance constitutes acceptance.',
                ratio: 'An offer made to the world at large can be accepted by anyone who performs the conditions without need to communicate acceptance.'
            },
            {
                title: 'Balfour v. Balfour (1919)',
                year: '1919',
                importance: 'Intention to Create Legal Relations',
                description: 'Agreement between husband and wife to pay allowance - domestic arrangement, not contract.',
                ratio: 'Domestic and social agreements are presumed not to create legal relations unless proved otherwise.'
            },
            {
                title: 'Lalman Shukla v. Gauri Dutt (1913)',
                year: '1913',
                importance: 'Communication of Offer',
                description: 'Servant found missing boy without knowing about reward - no contract.',
                ratio: 'Acceptance of an offer must be made with knowledge of the offer. Act done in ignorance of offer cannot be acceptance.'
            }
        ],
        questions: [
            {
                title: 'Explain the essentials of a valid contract under Indian Contract Act.',
                marks: 10,
                difficulty: 'Medium',
                hint: 'Discuss Section 10 requirements: agreement, free consent, competency, consideration, lawful object, certainty, possibility.'
            },
            {
                title: 'What is Consideration? "An agreement without consideration is void" - Discuss with exceptions.',
                marks: 10,
                difficulty: 'Medium',
                hint: 'Define consideration, state general rule under Section 25, explain exceptions like natural love and affection, past voluntary service, etc.'
            },
            {
                title: 'Distinguish between Offer and Invitation to Offer.',
                marks: 5,
                difficulty: 'Easy',
                hint: 'Define both, explain intention to be bound, examples like advertisements, auction, tenders.'
            }
        ]
    }
};

// Navigation functions
function goBackToDashboard() {
    window.location.href = 'dashboard-student.html';
}

function selectSubject(subject) {
    currentSubject = subject;
    
    // Hide subject selection
    document.getElementById('subjectSelection').classList.add('hidden');
    
    // Show study hub
    const studyHub = document.getElementById('studyHub');
    studyHub.classList.remove('hidden');
    
    // Update subject name
    const subjectName = subjectData[subject].name;
    document.getElementById('currentSubject').textContent = subjectName;
    document.getElementById('subjectTitle').textContent = subjectName;
    
    // Hide content area
    document.getElementById('contentArea').classList.add('hidden');
}

function backToSubjects() {
    // Hide study hub
    document.getElementById('studyHub').classList.add('hidden');
    
    // Show subject selection
    document.getElementById('subjectSelection').classList.remove('hidden');
    
    // Reset state
    currentSubject = '';
    currentMode = '';
}

function openMode(mode) {
    currentMode = mode;
    
    // Show content area
    const contentArea = document.getElementById('contentArea');
    contentArea.classList.remove('hidden');
    
    // Update title and load content
    const titles = {
        concepts: 'Learn Concepts',
        cases: 'Landmark Cases',
        practice: 'Answer Writing Practice',
        notes: 'My Notes'
    };
    
    document.getElementById('contentTitle').textContent = titles[mode];
    
    // Load appropriate content
    loadContent(mode);
    
    // Scroll to content
    contentArea.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function backToModes() {
    document.getElementById('contentArea').classList.add('hidden');
    currentMode = '';
}

function loadContent(mode) {
    const contentBody = document.getElementById('contentBody');
    const data = subjectData[currentSubject];
    
    if (mode === 'concepts') {
        contentBody.innerHTML = `
            <div class="topic-list">
                ${data.concepts.map((topic, index) => `
                    <div class="topic-item">
                        <h4>${index + 1}. ${topic.title}</h4>
                        <p><strong>Overview:</strong> ${topic.description}</p>
                        <p><strong>Key Points:</strong> ${topic.details}</p>
                    </div>
                `).join('')}
            </div>
        `;
    } else if (mode === 'cases') {
        contentBody.innerHTML = `
            <div class="case-list">
                ${data.cases.map((caseItem, index) => `
                    <div class="case-item">
                        <h4>${index + 1}. ${caseItem.title}</h4>
                        <div class="case-meta">
                            <span class="meta-tag">Year: ${caseItem.year}</span>
                            <span class="meta-tag">${caseItem.importance}</span>
                        </div>
                        <p><strong>Facts & Issue:</strong> ${caseItem.description}</p>
                        <p><strong>Ratio Decidendi:</strong> ${caseItem.ratio}</p>
                    </div>
                `).join('')}
            </div>
        `;
    } else if (mode === 'practice') {
        contentBody.innerHTML = `
            <div class="question-list">
                ${data.questions.map((question, index) => `
                    <div class="question-item">
                        <h4>Q${index + 1}. ${question.title}</h4>
                        <div class="question-meta">
                            <span class="meta-tag">${question.marks} Marks</span>
                            <span class="meta-tag">Difficulty: ${question.difficulty}</span>
                        </div>
                        <p><strong>💡 Hint:</strong> ${question.hint}</p>
                    </div>
                `).join('')}
            </div>
        `;
    } else if (mode === 'notes') {
        contentBody.innerHTML = `
            <div class="notes-editor">
                <h3>📝 Create Your Notes for ${data.name}</h3>
                <p style="color: #64748b; margin-bottom: 1rem;">Write your personal notes, summaries, and key points here. They will be saved locally.</p>
                <textarea placeholder="Start typing your notes here...

Example:
- Important cases to remember
- Key principles
- Exam tips
- Memory tricks"></textarea>
                <button class="btn-save" onclick="saveNotes()">💾 Save Notes</button>
            </div>
        `;
    }
}

function saveNotes() {
    const textarea = document.querySelector('.notes-editor textarea');
    const notes = textarea.value;
    
    if (notes.trim()) {
        // In a real app, this would save to localStorage or backend
        // For demo, just show confirmation
        const btn = document.querySelector('.btn-save');
        const originalText = btn.textContent;
        btn.textContent = '✅ Saved!';
        btn.style.background = '#10b981';
        
        setTimeout(() => {
            btn.textContent = originalText;
            btn.style.background = '#667eea';
        }, 2000);
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    // Show subject selection by default
    document.getElementById('subjectSelection').classList.remove('hidden');
    document.getElementById('studyHub').classList.add('hidden');
});