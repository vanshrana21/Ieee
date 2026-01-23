const API_BASE_URL = 'http://127.0.0.1:8000';

document.addEventListener('DOMContentLoaded', () => {
    const loginForm = document.getElementById('loginForm');
    
    if (loginForm) {
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const email = document.getElementById('email').value.trim();
            const password = document.getElementById('password').value;
            const submitBtn = loginForm.querySelector('button[type="submit"]');
            
            let errorEl = document.getElementById('loginError');
            if (!errorEl) {
                errorEl = document.createElement('div');
                errorEl.id = 'loginError';
                errorEl.className = 'login-error';
                loginForm.insertBefore(errorEl, loginForm.firstChild);
            }
            errorEl.textContent = '';
            errorEl.style.display = 'none';
            
            if (!email || !password) {
                errorEl.textContent = 'Please enter both email and password';
                errorEl.style.display = 'block';
                return;
            }
            
            const originalText = submitBtn.textContent;
            submitBtn.disabled = true;
            submitBtn.textContent = 'Signing in...';
            
            try {
                const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        email: email,
                        password: password
                    })
                });
                
                const data = await response.json();
                
                if (!response.ok) {
                    let errorMsg = 'Login failed';
                    
                    if (response.status === 401) {
                        errorMsg = data.detail?.message || 'Invalid email or password';
                    } else if (response.status === 403) {
                        errorMsg = data.detail?.message || 'Access forbidden';
                    } else if (response.status === 422) {
                        errorMsg = 'Invalid email format';
                    } else {
                        errorMsg = data.detail?.message || data.detail || 'Login failed';
                    }
                    
                    throw new Error(errorMsg);
                }
                
                if (data.access_token) {
                    localStorage.setItem('access_token', data.access_token);
                    
                    if (data.role) {
                        localStorage.setItem('user_role', data.role);
                    }
                    
                    window.location.href = '/html/dashboard-student.html';
                } else {
                    throw new Error('No access token received');
                }
                
            } catch (error) {
                if (error.name === 'TypeError' && error.message.includes('fetch')) {
                    errorEl.textContent = 'Cannot connect to server. Please check if the backend is running.';
                } else {
                    errorEl.textContent = error.message;
                }
                errorEl.style.display = 'block';
                
                submitBtn.disabled = false;
                submitBtn.textContent = originalText;
            }
        });
    }
});
