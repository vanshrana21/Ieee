// Case Database - Static dummy data
const casesDatabase = {
    kesavananda: {
        name: "Kesavananda Bharati v. State of Kerala (1973)",
        subject: "Constitutional Law",
        facts: `The petitioner, Kesavananda Bharati, was the head of a Hindu monastery in Kerala. He challenged the Kerala Land Reforms Act and constitutional amendments (24th, 25th, and 29th) that limited property rights. The case arose when the State of Kerala imposed restrictions on religious institutions' property rights. The petitioner argued that Parliament's amending power under Article 368 was unlimited and could destroy the basic features of the Constitution.`,
        issues: [
            "Whether Parliament has unlimited power to amend the Constitution under Article 368?",
            "Can Parliament amend fundamental rights including the right to property?",
            "What are the limits, if any, on the amending power of Parliament?"
        ],
        judgment: `The Supreme Court delivered a historic judgment with a 7-6 majority. The Court held that while Parliament has wide powers to amend the Constitution, it cannot alter the <span class="highlight">basic structure</span> of the Constitution. The Court identified certain features as part of the basic structure including supremacy of the Constitution, republican and democratic form of government, secular character, separation of powers, and federal character. The Court upheld the validity of Article 368 but with limitations.`,
        ratio: `Parliament's power to amend the Constitution under Article 368 is subject to the limitation that the <span class="keyword">basic structure</span> or essential features of the Constitution cannot be destroyed or abrogated. While individual fundamental rights can be amended, the fundamental rights as a whole, which form part of the basic structure, cannot be abolished.`,
        articles: [
            "Article 368 - Power of Parliament to amend the Constitution",
            "Article 13 - Laws inconsistent with or in derogation of fundamental rights",
            "Article 31 - Right to Property (as it existed then)",
            "Part III - Fundamental Rights (Articles 12-35)",
            "Article 14 - Right to Equality",
            "Article 19 - Right to Freedom"
        ],
        examImportance: {
            why: "Kesavananda Bharati is the most important case in Indian Constitutional Law. It established the Basic Structure Doctrine which has shaped constitutional interpretation for 50+ years.",
            topics: [
                "Fundamental Rights vs. Directive Principles",
                "Parliamentary Sovereignty vs. Constitutional Supremacy",
                "Judicial Review and its scope",
                "Constitutional Amendments",
                "Federalism and Separation of Powers"
            ],
            tips: [
                "Always mention the 7-6 majority verdict",
                "List at least 5 elements of Basic Structure",
                "Contrast with Golak Nath and Minerva Mills cases",
                "Explain the historical context (Emergency period)",
                "Discuss the doctrine's evolution and application"
            ]
        },
        answerFormat: {
            fiveMark: `<strong>Structure:</strong><br>
                <strong>1. Introduction (1 mark):</strong> Brief case facts and year<br>
                <strong>2. Issue (1 mark):</strong> Whether Parliament can amend fundamental rights<br>
                <strong>3. Judgment (2 marks):</strong> Basic Structure Doctrine explained<br>
                <strong>4. Significance (1 mark):</strong> Impact on constitutional law`,
            tenMark: `<strong>Structure:</strong><br>
                <strong>1. Introduction (1.5 marks):</strong> Detailed facts, parties involved, year, bench composition<br>
                <strong>2. Background (1.5 marks):</strong> Prior cases (Shankari Prasad, Golak Nath)<br>
                <strong>3. Issues Raised (2 marks):</strong> All three questions before the Court<br>
                <strong>4. Judgment & Ratio (3 marks):</strong> Basic Structure Doctrine, elements, 7-6 majority<br>
                <strong>5. Impact & Criticism (2 marks):</strong> Subsequent cases, importance, any limitations`
        }
    },
    maneka: {
        name: "Maneka Gandhi v. Union of India (1978)",
        subject: "Constitutional Law",
        facts: `Maneka Gandhi, a journalist and political activist, had her passport impounded by the Regional Passport Officer under Section 10(3)(c) of the Passports Act, 1967. The government did not provide her with reasons for the impoundment. She challenged this action as violating her fundamental right to travel abroad under Article 21 (Right to Life and Personal Liberty).`,
        issues: [
            "Whether the right to travel abroad is part of personal liberty under Article 21?",
            "What is the scope and meaning of 'procedure established by law' in Article 21?",
            "Whether Articles 14, 19, and 21 are mutually exclusive or overlapping?"
        ],
        judgment: `The Supreme Court held that the right to travel abroad is part of 'personal liberty' under Article 21. The Court expanded the interpretation of Article 21 by ruling that 'procedure established by law' must be <span class="highlight">just, fair and reasonable</span>. The procedure cannot be arbitrary or fanciful. The Court also established that Articles 14, 19, and 21 are not mutually exclusive but form a <span class="keyword">golden triangle</span> - they overlap and must be read together.`,
        ratio: `Article 21 is the heart of fundamental rights. The procedure contemplated by Article 21 must be <span class="keyword">just, fair and reasonable</span>, not arbitrary. It must satisfy the test of Articles 14 (equality) and 19 (freedoms). The right to life and personal liberty includes the right to travel abroad.`,
        articles: [
            "Article 21 - Protection of Life and Personal Liberty",
            "Article 14 - Right to Equality",
            "Article 19(1)(a) - Freedom of Speech and Expression",
            "Article 19(1)(d) - Freedom to move freely",
            "Section 10(3)(c) of Passports Act, 1967"
        ],
        examImportance: {
            why: "This case revolutionized the interpretation of Article 21 and expanded fundamental rights beyond their literal meaning. It's crucial for understanding modern constitutional rights.",
            topics: [
                "Expanded interpretation of Article 21",
                "Relationship between Articles 14, 19, and 21",
                "Natural Justice and Fair Procedure",
                "Right to Travel Abroad",
                "Judicial Activism and Creative Interpretation"
            ],
            tips: [
                "Emphasize the 'golden triangle' concept",
                "Explain how this case departed from A.K. Gopalan",
                "List rights that later flowed from Article 21",
                "Mention Justice Bhagwati's landmark judgment",
                "Connect to subsequent Article 21 cases"
            ]
        },
        answerFormat: {
            fiveMark: `<strong>Structure:</strong><br>
                <strong>1. Facts (1 mark):</strong> Passport impoundment issue<br>
                <strong>2. Issue (1 mark):</strong> Scope of Article 21<br>
                <strong>3. Judgment (2 marks):</strong> Just, fair, reasonable procedure; Golden Triangle<br>
                <strong>4. Significance (1 mark):</strong> Expanded fundamental rights`,
            tenMark: `<strong>Structure:</strong><br>
                <strong>1. Introduction (1 mark):</strong> Background and facts<br>
                <strong>2. Previous Position (1.5 marks):</strong> A.K. Gopalan case, narrow interpretation<br>
                <strong>3. Issues (2 marks):</strong> Three questions before Court<br>
                <strong>4. Judgment (3 marks):</strong> Golden Triangle, expanded Article 21, examples<br>
                <strong>5. Impact (2.5 marks):</strong> Subsequent developments, new rights derived`
        }
    },
    nanavati: {
        name: "K.M. Nanavati v. State of Maharashtra (1962)",
        subject: "Criminal Law",
        facts: `Commander K.M. Nanavati, a Naval officer, was married to Sylvia. Sylvia confessed to having an affair with Prem Ahuja, a businessman. On April 27, 1959, after learning of the affair, Nanavati went to Ahuja's apartment and shot him dead with his service revolver. Nanavati claimed he acted under grave and sudden provocation. The case garnered massive public attention and became the last jury trial in India.`,
        issues: [
            "Whether the accused acted under grave and sudden provocation?",
            "Whether there was sufficient cooling time between provocation and the act?",
            "Whether the killing was culpable homicide amounting to murder or manslaughter?"
        ],
        judgment: `The Sessions Court jury acquitted Nanavati. However, the Bombay High Court set aside the acquittal and convicted him for murder under Section 302 IPC. The Supreme Court upheld the conviction, holding that the provocation was not grave and sudden as required under Exception 1 to Section 300 IPC. The Court noted the time gap between discovering the affair and the shooting, indicating <span class="highlight">premeditation</span> rather than sudden provocation.`,
        ratio: `For Exception 1 to Section 300 IPC (grave and sudden provocation) to apply, the provocation must cause sudden and temporary loss of self-control. A time gap between provocation and the act indicates <span class="keyword">premeditation</span>, which negates the defense. The accused must act in the heat of passion without premeditation.`,
        articles: [
            "Section 300 - Murder (IPC)",
            "Section 302 - Punishment for Murder (IPC)",
            "Exception 1 to Section 300 - Grave and Sudden Provocation",
            "Section 299 - Culpable Homicide (IPC)",
            "Section 304 - Culpable Homicide not amounting to Murder (IPC)"
        ],
        examImportance: {
            why: "This is the most famous criminal case in India. It led to the abolition of jury trials and is crucial for understanding the defense of provocation.",
            topics: [
                "Difference between Murder and Culpable Homicide",
                "Exceptions to Section 300 IPC",
                "Defense of Grave and Sudden Provocation",
                "Jury System in India",
                "Media Trial and Public Opinion"
            ],
            tips: [
                "Clearly distinguish Section 299 and Section 300",
                "Explain all four exceptions to Section 300",
                "Discuss the facts chronologically",
                "Mention this was the last jury trial",
                "Analyze why provocation defense failed"
            ]
        },
        answerFormat: {
            fiveMark: `<strong>Structure:</strong><br>
                <strong>1. Facts (1.5 marks):</strong> Naval officer, affair, shooting<br>
                <strong>2. Issue (1 mark):</strong> Grave and sudden provocation<br>
                <strong>3. Judgment (1.5 marks):</strong> Conviction upheld, time gap crucial<br>
                <strong>4. Significance (1 mark):</strong> Last jury trial, legal principles`,
            tenMark: `<strong>Structure:</strong><br>
                <strong>1. Introduction (1 mark):</strong> Background, parties, year<br>
                <strong>2. Detailed Facts (2 marks):</strong> Timeline of events, relationship dynamics<br>
                <strong>3. Legal Framework (2 marks):</strong> Sections 299, 300, Exception 1<br>
                <strong>4. Arguments & Judgment (3 marks):</strong> Defense arguments, Court's reasoning<br>
                <strong>5. Legal Impact (2 marks):</strong> Principles established, jury abolition`
        }
    },
    carlill: {
        name: "Carlill v. Carbolic Smoke Ball Co. (1893)",
        subject: "Contract Law",
        facts: `The Carbolic Smoke Ball Company advertised that it would pay £100 to anyone who contracted influenza after using their smoke ball product as directed. They deposited £1,000 in a bank as a sign of sincerity. Mrs. Carlill purchased the smoke ball, used it as directed, but still contracted influenza. She claimed the £100 reward. The company refused to pay, arguing there was no contract.`,
        issues: [
            "Whether the advertisement was a mere puff or a binding offer?",
            "Can an offer be made to the world at large?",
            "Whether acceptance can be through performance without prior communication?",
            "Whether there was intention to create legal relations?"
        ],
        judgment: `The Court of Appeal held that the advertisement was a <span class="highlight">unilateral offer</span> to the world at large, not a mere puff. By depositing £1,000 in the bank, the company showed intention to be legally bound. Mrs. Carlill accepted the offer by performing the conditions (using the smoke ball as directed). Communication of acceptance is not required in unilateral contracts - <span class="keyword">performance constitutes acceptance</span>.`,
        ratio: `An offer can be made to the world at large and can be accepted by anyone who performs the stipulated conditions. In a <span class="keyword">unilateral contract</span>, performance of the conditions constitutes acceptance, and prior communication of acceptance is not necessary. Deposit of money or similar acts can demonstrate intention to create legal relations.`,
        articles: [
            "Section 2(a) - Definition of Offer (Indian Contract Act)",
            "Section 2(b) - Definition of Acceptance",
            "Section 8 - Acceptance by performing conditions",
            "Section 10 - What agreements are contracts",
            "General Principles of Offer and Acceptance"
        ],
        examImportance: {
            why: "This is the most important case for understanding unilateral contracts and offer-acceptance principles. It's cited universally in contract law.",
            topics: [
                "Unilateral vs Bilateral Contracts",
                "Offer to the World at Large",
                "Acceptance by Performance",
                "Intention to Create Legal Relations",
                "Distinction between Offer and Invitation to Offer"
            ],
            tips: [
                "Emphasize it's a unilateral contract",
                "Explain why it wasn't a mere puff",
                "Discuss the £1,000 deposit significance",
                "Compare with invitation to offer cases",
                "Give modern examples (reward offers)"
            ]
        },
        answerFormat: {
            fiveMark: `<strong>Structure:</strong><br>
                <strong>1. Facts (1 mark):</strong> Smoke ball advertisement and claim<br>
                <strong>2. Issues (1 mark):</strong> Whether binding offer existed<br>
                <strong>3. Judgment (2 marks):</strong> Unilateral contract, performance = acceptance<br>
                <strong>4. Principle (1 mark):</strong> Offer to world at large`,
            tenMark: `<strong>Structure:</strong><br>
                <strong>1. Introduction (1 mark):</strong> Context, parties, English case law<br>
                <strong>2. Facts (2 marks):</strong> Advertisement details, Mrs. Carlill's actions<br>
                <strong>3. Company's Arguments (2 marks):</strong> Mere puff, no acceptance communicated<br>
                <strong>4. Court's Reasoning (3 marks):</strong> Each issue addressed, legal principles<br>
                <strong>5. Application in India (2 marks):</strong> Relevance, similar provisions in ICA`
        }
    }
};

// Global state
let currentCase = null;

// Navigation
function goBackToDashboard() {
    window.location.href = "./dashboard-student.html";
}

// Load popular case
function loadPopularCase(caseKey) {
    if (casesDatabase[caseKey]) {
        const caseData = casesDatabase[caseKey];
        document.getElementById('caseName').value = caseData.name;
        
        // Set subject dropdown
        const subjectMap = {
            'Constitutional Law': 'constitutional',
            'Criminal Law': 'criminal',
            'Contract Law': 'contract'
        };
        document.getElementById('subjectSelect').value = subjectMap[caseData.subject];
        
        // Show toast
        showToast(`Loaded: ${caseData.name}`);
    }
}

// Main simplify function
function simplifyCase() {
    const caseName = document.getElementById('caseName').value.trim();
    const subject = document.getElementById('subjectSelect').value;
    
    if (!caseName) {
        showToast('⚠️ Please enter a case name');
        return;
    }
    
    if (!subject) {
        showToast('⚠️ Please select a subject');
        return;
    }
    
    // Check if it's a popular case
    let caseData = null;
    for (let key in casesDatabase) {
        if (casesDatabase[key].name.toLowerCase().includes(caseName.toLowerCase()) || 
            caseName.toLowerCase().includes(key)) {
            caseData = casesDatabase[key];
            break;
        }
    }
    
    // If not found, create generic case
    if (!caseData) {
        caseData = generateGenericCase(caseName, subject);
    }
    
    currentCase = {
        name: caseName,
        subject: subject,
        data: caseData
    };
    
    // Populate and show output
    displayCaseOutput(caseData);
    
    // Scroll to output
    document.getElementById('outputSection').scrollIntoView({ behavior: 'smooth' });
}

// Generate generic case data
function generateGenericCase(name, subject) {
    const subjectNames = {
        constitutional: 'Constitutional Law',
        criminal: 'Criminal Law',
        contract: 'Contract Law',
        tort: 'Tort Law',
        property: 'Property Law'
    };
    
    return {
        name: name,
        subject: subjectNames[subject],
        facts: `This case involves important principles of ${subjectNames[subject]}. The petitioner challenged certain provisions and raised questions about the interpretation and application of relevant legal principles. The case came before the court under special circumstances requiring detailed examination of statutory provisions and constitutional validity.`,
        issues: [
            `What is the correct interpretation of the relevant provisions?`,
            `Whether the actions challenged are legally valid?`,
            `What are the broader implications for ${subjectNames[subject]}?`
        ],
        judgment: `The Court examined the facts, statutory provisions, and precedents in detail. After considering arguments from both sides, the Court delivered a comprehensive judgment addressing all issues raised. The judgment provides <span class="highlight">important guidelines</span> for future cases and clarifies the legal position on key matters.`,
        ratio: `The key principle established is that legal provisions must be interpreted in accordance with constitutional values and established precedents. The Court emphasized the importance of <span class="keyword">contextual interpretation</span> and balanced application of law.`,
        articles: [
            `Relevant statutory provisions of ${subjectNames[subject]}`,
            `Constitutional Articles (if applicable)`,
            `Procedural provisions`,
            `Related enactments and rules`
        ],
        examImportance: {
            why: `This case is important for understanding fundamental principles of ${subjectNames[subject]} and how courts approach interpretation of legal provisions.`,
            topics: [
                `Core concepts in ${subjectNames[subject]}`,
                `Judicial interpretation principles`,
                `Application of precedents`,
                `Contemporary legal issues`
            ],
            tips: [
                `Focus on the core legal principles established`,
                `Understand the reasoning process`,
                `Connect to related cases and provisions`,
                `Practice application to hypothetical scenarios`
            ]
        },
        answerFormat: {
            fiveMark: `<strong>Structure:</strong><br>
                <strong>1. Introduction (1 mark):</strong> Brief facts and context<br>
                <strong>2. Issue (1 mark):</strong> Main legal question<br>
                <strong>3. Judgment (2 marks):</strong> Court's decision and reasoning<br>
                <strong>4. Significance (1 mark):</strong> Legal principle established`,
            tenMark: `<strong>Structure:</strong><br>
                <strong>1. Introduction (1.5 marks):</strong> Detailed background and facts<br>
                <strong>2. Legal Framework (2 marks):</strong> Relevant provisions and precedents<br>
                <strong>3. Issues (2 marks):</strong> All questions before the Court<br>
                <strong>4. Judgment (3 marks):</strong> Detailed analysis of Court's reasoning<br>
                <strong>5. Impact (1.5 marks):</strong> Significance and subsequent developments`
        }
    };
}

// Display case output
function displayCaseOutput(caseData) {
    // Show output section
    document.getElementById('outputSection').classList.remove('hidden');
    
    // Update header
    document.getElementById('outputCaseName').textContent = caseData.name;
    document.getElementById('outputSubject').textContent = caseData.subject;
    
    // Facts
    document.getElementById('factsContent').innerHTML = `
        <p>${caseData.facts}</p>
    `;
    
    // Issues
    const issuesHTML = caseData.issues.map((issue, index) => 
        `<p><strong>${index + 1}.</strong> ${issue}</p>`
    ).join('');
    document.getElementById('issuesContent').innerHTML = issuesHTML;
    
    // Judgment
    document.getElementById('judgmentContent').innerHTML = `
        <p>${caseData.judgment}</p>
    `;
    
    // Ratio Decidendi
    document.getElementById('ratioContent').innerHTML = `
        <p>${caseData.ratio}</p>
        <div style="background: #fef3c7; padding: 1rem; border-radius: 8px; margin-top: 1rem;">
            <strong>💡 Remember:</strong> The ratio decidendi is the legal principle or rule that forms the basis of the decision. This is what you must cite in exams!
        </div>
    `;
    
    // Articles
    const articlesHTML = caseData.articles.map(article => 
        `<li>${article}</li>`
    ).join('');
    document.getElementById('articlesContent').innerHTML = `<ul>${articlesHTML}</ul>`;
    
    // Exam Importance
    const topicsHTML = caseData.examImportance.topics.map(topic => 
        `<li>${topic}</li>`
    ).join('');
    const tipsHTML = caseData.examImportance.tips.map(tip => 
        `<li>${tip}</li>`
    ).join('');
    
    document.getElementById('examContent').innerHTML = `
        <div style="background: #dcfce7; padding: 1rem; border-radius: 8px; margin-bottom: 1rem;">
            <h4 style="color: #166534; margin-top: 0;">🎯 Why This Case Matters</h4>
            <p style="margin-bottom: 0;">${caseData.examImportance.why}</p>
        </div>
        <h4>📚 Related Topics for Exams:</h4>
        <ul>${topicsHTML}</ul>
        <h4>✅ Exam Writing Tips:</h4>
        <ul>${tipsHTML}</ul>
    `;
    
    // Answer Format
    document.getElementById('answerContent').innerHTML = `
        <div style="background: #ede9fe; padding: 1.5rem; border-radius: 10px; margin-bottom: 1rem;">
            <h4 style="color: #5b21b6; margin-top: 0;">✍️ For 5-Mark Questions</h4>
            <p>${caseData.answerFormat.fiveMark}</p>
        </div>
        <div style="background: #dbeafe; padding: 1.5rem; border-radius: 10px;">
            <h4 style="color: #1e40af; margin-top: 0;">✍️ For 10-Mark Questions</h4>
            <p>${caseData.answerFormat.tenMark}</p>
        </div>
        <div style="background: #fff7ed; padding: 1rem; border-radius: 8px; margin-top: 1rem;">
            <strong>⏰ Time Management:</strong> Spend 8-10 minutes on 5-mark answers and 15-18 minutes on 10-mark answers. Leave time for introduction and conclusion!
        </div>
    `;
    
    // Reset all cards to collapsed state
    document.querySelectorAll('.collapse-card').forEach(card => {
        card.classList.remove('active');
    });
}

// Toggle collapse
function toggleCollapse(header) {
    const card = header.parentElement;
    card.classList.toggle('active');
}

// Copy section content
function copySection(contentId) {
    const content = document.getElementById(contentId);
    const textToCopy = content.innerText;
    
    // Create temporary textarea
    const textarea = document.createElement('textarea');
    textarea.value = textToCopy;
    document.body.appendChild(textarea);
    textarea.select();
    
    try {
        document.execCommand('copy');
        showToast('✅ Content copied to clipboard!');
    } catch (err) {
        showToast('❌ Failed to copy');
    }
    
    document.body.removeChild(textarea);
}

// Save case to localStorage
function saveCase() {
    if (!currentCase) {
        showToast('⚠️ No case to save');
        return;
    }
    
    // Get existing saved cases
    let savedCases = JSON.parse(localStorage.getItem('savedCases') || '[]');
    
    // Check if already saved
    const exists = savedCases.some(c => c.name === currentCase.name);
    if (exists) {
        showToast('ℹ️ Case already saved');
        return;
    }
    
    // Add new case
    const caseToSave = {
        name: currentCase.name,
        subject: currentCase.subject,
        savedDate: new Date().toLocaleDateString()
    };
    
    savedCases.unshift(caseToSave);
    
    // Limit to 10 saved cases
    if (savedCases.length > 10) {
        savedCases = savedCases.slice(0, 10);
    }
    
    localStorage.setItem('savedCases', JSON.stringify(savedCases));
    
    showToast('💾 Case saved successfully!');
    loadSavedCases();
}

// Load saved cases
function loadSavedCases() {
    const savedCases = JSON.parse(localStorage.getItem('savedCases') || '[]');
    const savedList = document.getElementById('savedCasesList');
    
    if (savedCases.length === 0) {
        savedList.innerHTML = '<p class="empty-state">No saved cases yet. Simplify a case and save it!</p>';
        return;
    }
    
    const html = savedCases.map(caseItem => `
        <div class="saved-item" onclick="loadSavedCase('${caseItem.name}')">
            <div class="saved-item-title">${caseItem.name}</div>
            <div class="saved-item-meta">${caseItem.subject} • Saved on ${caseItem.savedDate}</div>
        </div>
    `).join('');
    
    savedList.innerHTML = html;
}

// Load a saved case
function loadSavedCase(caseName) {
    document.getElementById('caseName').value = caseName;
    showToast(`Loaded: ${caseName}`);
    
    // Auto-scroll to input
    document.querySelector('.input-card').scrollIntoView({ behavior: 'smooth' });
}

// Export PDF (UI only)
function exportPDF() {
    showToast('📄 PDF export feature coming soon!');
}

// Add to notes (placeholder)
function addToNotes() {
    showToast('📝 Added to your notes!');
}

// Reset form
function resetForm() {
    document.getElementById('caseName').value = '';
    document.getElementById('subjectSelect').value = '';
    document.getElementById('outputSection').classList.add('hidden');
    currentCase = null;
    
    // Scroll to top
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

// Show toast notification
function showToast(message) {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.classList.add('show');
    
    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    loadSavedCases();
    
    // Allow Enter key to submit
    document.getElementById('caseName').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            simplifyCase();
        }
    });
});