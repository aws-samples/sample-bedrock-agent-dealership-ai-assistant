document.addEventListener('DOMContentLoaded', function() {
    // Auth configuration
    const authConfig = {
        userPoolId: window.COGNITO_USER_POOL_ID,
        clientId: window.COGNITO_CLIENT_ID,
        identityPoolId: window.COGNITO_IDENTITY_POOL_ID,
        region: window.REGION,
        domain: window.COGNITO_DOMAIN
    };
    
    // Initialize AWS and Cognito
    AWS.config.region = authConfig.region;
    
    // Auth state
    let isAuthenticated = false;
    let idToken = localStorage.getItem('idToken');
    let accessToken = localStorage.getItem('accessToken');
    
    // Auth button
    const authButton = document.getElementById('auth-button');
    
    // Chat functionality
    const chatToggle = document.getElementById('chat-toggle');
    const chatWindow = document.getElementById('chat-window');
    const minimizeChat = document.getElementById('minimize-chat');
    const chatMessages = document.getElementById('chat-messages');
    const userInput = document.getElementById('user-input');
    const sendButton = document.getElementById('send-button');
    
    // Generate a random session ID for this chat session
    const sessionId = Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
    
    // Flag to track if a request is in progress
    let isRequestInProgress = false;
    
    // Initialize auth state on page load
    updateAuthUI(!!idToken);

    // Auth button click handler
    authButton.addEventListener('click', function(e) {
        e.preventDefault();
        
        if (isAuthenticated) {
            // Sign out
            signOut();
        } else {
            // Sign in - redirect to Cognito hosted UI
            signIn();
        }
    });

    // Sign in function - redirect to Cognito hosted UI
    function signIn() {
        const redirectUri = window.location.origin + '/';
        const hostedUIUrl = `https://${authConfig.domain}/login?client_id=${authConfig.clientId}&response_type=token&scope=email+openid+profile&redirect_uri=${encodeURIComponent(redirectUri)}`;
        window.location.href = hostedUIUrl;
    }

    // Sign out function
    function signOut() {
        // Clear tokens
        localStorage.removeItem('idToken');
        localStorage.removeItem('accessToken');
        
        // Redirect to Cognito logout
        const redirectUri = window.location.origin + '/';
        const logoutUrl = `https://${authConfig.domain}/logout?client_id=\${authConfig.clientId}&logout_uri=${encodeURIComponent(redirectUri)}`;
        
        window.location.href = logoutUrl;
    }

    // Update UI based on auth state
    function updateAuthUI(authenticated) {
        isAuthenticated = authenticated;
        
        if (authenticated) {
            authButton.textContent = 'Sign Out';
            // Optionally, parse idToken to get user info
            try {
                const payload = parseJwt(idToken);
                console.log('User authenticated:', payload.email);
                // You could update UI with user info here
            } catch (e) {
                console.error('Error parsing token:', e);
            }
        } else {
            authButton.textContent = 'Sign In';
        }
    }
    
    // Parse JWT token
    function parseJwt(token) {
        const base64Url = token.split('.')[1];
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
        const jsonPayload = decodeURIComponent(atob(base64).split('').map(function(c) {
            return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
        }).join(''));
        
        return JSON.parse(jsonPayload);
    }
    
    // Toggle chat window
    chatToggle.addEventListener('click', function() {
        // Check if user is authenticated before opening chat
        if (!isAuthenticated) {
            alert('Please sign in to use the chat feature');
            signIn();
            return;
        }
        
        chatWindow.classList.add('active');
        chatToggle.style.display = 'none';
        scrollToBottom();
    });
    
    // Minimize chat window
    minimizeChat.addEventListener('click', function() {
        chatWindow.classList.remove('active');
        chatToggle.style.display = 'flex';
    });
    
    // Auto-resize the input textarea
    userInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight < 80) ? this.scrollHeight + 'px' : '80px';
    });
    
    // Send message on Enter key (without Shift)
    userInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    
    // Send message on button click
    sendButton.addEventListener('click', sendMessage);
    
    function sendMessage() {
        // Check if user is authenticated
        if (!isAuthenticated) {
            alert('Please sign in to use the chat feature');
            signIn();
            return;
        }
        
        const message = userInput.value.trim();
        if (!message || isRequestInProgress) return;
        
        // Set flag to prevent multiple requests
        isRequestInProgress = true;
        
        // Add user message to chat
        addMessage(message, 'user');
        
        // Clear input field and reset height
        userInput.value = '';
        userInput.style.height = 'auto';
        
        // Show loading indicator
        const loadingDiv = document.createElement('div');
        loadingDiv.className = 'message bot loading-indicator-message';
        
        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        
        const botIcon = document.createElement('i');
        botIcon.className = 'fas fa-robot bot-icon';
        
        const loadingIndicator = document.createElement('div');
        loadingIndicator.className = 'loading-indicator';
        
        for (let i = 0; i < 3; i++) {
            const dot = document.createElement('div');
            dot.className = 'dot';
            loadingIndicator.appendChild(dot);
        }
        
        messageContent.appendChild(botIcon);
        messageContent.appendChild(loadingIndicator);
        loadingDiv.appendChild(messageContent);
        chatMessages.appendChild(loadingDiv);
        
        scrollToBottom();
        
        // Call the API Gateway endpoint to invoke the Bedrock Agent
        callBedrockAgentAPI(message)
            .then(response => {
                // Safely remove loading indicator
                removeLoadingIndicator();
                
                // Add bot response
                if (response && response.completion) {
                    addMessage(response.completion, 'bot');
                } else {
                    throw new Error("Invalid response from agent");
                }
            })
            .catch(error => {
                // Safely remove loading indicator
                removeLoadingIndicator();
                
                // Add error message
                addMessage("Sorry, I encountered an error. Please try again later.", 'bot');
                console.error('Error:', error);
            })
            .finally(() => {
                // Reset request flag
                isRequestInProgress = false;
            });
    }
    
    // Safely remove loading indicator
    function removeLoadingIndicator() {
        // Find and remove all loading indicators to be safe
        const loadingIndicators = document.querySelectorAll('.loading-indicator-message');
        loadingIndicators.forEach(indicator => {
            if (indicator && indicator.parentNode) {
                indicator.parentNode.removeChild(indicator);
            }
        });
    }
    
    function addMessage(text, sender) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}`;
        
        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        
        const messageText = document.createElement('div');
        messageText.className = 'message-text';
        
        // Format code blocks if present
        messageText.appendChild(formatMessage(text));
        
        if (sender === 'bot') {
            const botIcon = document.createElement('i');
            botIcon.className = 'fas fa-robot bot-icon';
            messageContent.appendChild(botIcon);
        }
        
        messageContent.appendChild(messageText);
        messageDiv.appendChild(messageContent);
        
        chatMessages.appendChild(messageDiv);
        scrollToBottom();
    }
    
    function formatMessage(text) {
        const fragment = document.createDocumentFragment();
        
        // Split by code blocks
        const parts = text.split(/```([\s\S]*?)```/);
        
        for (let i = 0; i < parts.length; i++) {
            if (i % 2 === 0) {
                // Regular text
                const lines = parts[i].split('\n');
                lines.forEach((line, idx) => {
                    const textNode = document.createTextNode(line);
                    fragment.appendChild(textNode);
                    
                    if (idx < lines.length - 1) {
                        fragment.appendChild(document.createElement('br'));
                    }
                });
            } else {
                // Code block
                const codeBlock = document.createElement('div');
                codeBlock.className = 'code-block';
                codeBlock.textContent = parts[i];
                fragment.appendChild(codeBlock);
            }
        }
        
        return fragment;
    }
    
    function scrollToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    
    /**
     * Calls the API Gateway endpoint that invokes the Bedrock Agent
     * @param {string} message - The user's message
     * @returns {Promise<{sessionId: string, completion: string}>}
     */
    async function callBedrockAgentAPI(message) {
        // Replace with your actual API Gateway URL
        const apiEndpoint = window.API_ENDPOINT + '/agent';
        
        try {
            const response = await fetch(apiEndpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    // Add Authorization header with the ID token
                    'Authorization': idToken
                },
                body: JSON.stringify({ 
                    prompt: message,
                    sessionId: sessionId
                })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            
            // Return data in the expected format
            return data;
            
        } catch (error) {
            console.error("Error calling Bedrock Agent API:", error);
            throw error;
        }
    }
    
    // Add car-related functionality
    const viewButtons = document.querySelectorAll('.secondary-button');
    viewButtons.forEach(button => {
        button.addEventListener('click', function() {
            // In a real app, this would navigate to the car details page
            const carName = this.parentElement.querySelector('h3').textContent;
            alert(`You clicked on ${carName}. In a real website, this would take you to the details page.`);
        });
    });
});