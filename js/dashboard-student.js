
        // ===== AUTHENTICATION LOGIC (PRESERVED) =====
        if (!window.auth.requireAuth()) {
            window.location.href = './login.html';
        }
        
        const role = window.auth.getRole();
        if (role !== 'student') {
            console.warn('Non-student trying to access student dashboard');
            window.auth.redirectToDashboard(role);
        }

        // ===== DASHBOARD FUNCTIONALITY =====
        
        // Primary Action Card Functions
        function startStudying() {
            console.log('Starting study session...');
            alert('📘 Subject Selection - Choose your subject:\n\n• Constitutional Law\n• Criminal Law\n• Contract Law\n• Tort Law\n• Family Law');
        }

        function openCaseSimplifier() {
            console.log('Opening Case Simplifier...');
            alert('📚 Case Simplifier\n\nEnter a case name to get:\n✓ Facts\n✓ Issues\n✓ Judgment\n✓ Ratio Decidendi\n✓ Exam Importance');
        }

        function practiceAnswers() {
            console.log('Opening Answer Practice...');
            alert('✍️ Answer Writing Practice\n\nSelect question type:\n• 5-mark questions\n• 10-mark questions\n• 20-mark questions\n\nGet AI-powered feedback!');
        }

        function openNotes() {
            console.log('Opening Notes...');
            alert('📝 My Notes\n\nAccess your:\n• Case-linked notes\n• Subject-wise notes\n• Exam preparation notes');
        }

        // AI Assistant Functions
        function askAI() {
            const query = document.getElementById('aiQuery').value;
            if (query.trim()) {
                console.log('AI Query:', query);
                alert('🤖 AI Processing...\n\nYour question: "' + query + '"\n\nIn a real implementation, this would provide a student-friendly explanation!');
                document.getElementById('aiQuery').value = '';
            }
        }

        function setQuery(element) {
            const query = element.textContent.trim().replace(/"/g, '');
            document.getElementById('aiQuery').value = query;
            document.getElementById('aiQuery').focus();
        }

        // Enter key support for AI input
        document.getElementById('aiQuery').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                askAI();
            }
        });

        // Checklist Toggle Function
        function toggleCheck(item) {
            const checkbox = item.querySelector('.checkbox');
            checkbox.classList.toggle('checked');
            item.classList.toggle('completed');
        }

        // Recent Item Click Handler
        function openItem(itemId) {
            console.log('Opening item:', itemId);
            alert('Opening: ' + itemId + '\n\nIn production, this would navigate to the actual content.');
        }

        // Animate progress bars on load
        window.addEventListener('load', function() {
            const progressBars = document.querySelectorAll('.progress-fill');
            progressBars.forEach(bar => {
                const width = bar.style.width;
                bar.style.width = '0%';
                setTimeout(() => {
                    bar.style.width = width;
                }, 100);
            });
        });

        // Optional: Load student name from auth if available
        try {
            const userData = window.auth.getCurrentUser();
            if (userData && userData.name) {
                document.getElementById('studentName').textContent = userData.name;
            }
        } catch (e) {
            console.log('Using placeholder student name');
        }
