document.addEventListener('DOMContentLoaded', () => {
    const chatMessages = document.getElementById('chat-messages');
    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');
    const sendButton = document.getElementById('send-button');
    const welcomeMessage = document.getElementById('welcome-message');
    const questionBoxes = document.querySelectorAll('.question-box');
    const restartButton = document.getElementById('restart-button');

    let socket = null;
    let chatStarted = false;
    let sessionId = getStoredSessionId();
    let sessionData = null;
    let messageHistory = getStoredMessages();

    sendButton.disabled = true;
    restartButton.disabled = true;
    chatInput.focus();
    if (localStorage.getItem('chat_started') === 'true') {
        chatStarted = true;
        restartButton.disabled = false;
        welcomeMessage.classList.add('hidden');
    } else {
        welcomeMessage.classList.remove('hidden');
    }

    // Event Listeners
    function initializeEventListeners() {
        chatForm.addEventListener('submit', handleFormSubmit);
        chatInput.addEventListener('input', () => { sendButton.disabled = chatInput.value.trim() === ''; });
        restartButton.addEventListener('click', restartChat);
        questionBoxes.forEach(box => {
            box.addEventListener('click', () => {
                const questionText = box.querySelector('p').textContent.trim();
                chatInput.value = questionText;
                handleFormSubmit(new Event('click'));
            });
        });
    }

    // Socket
    function initializeSocket() {
        socket = io();

        socket.on('connect', () => {
            console.log('Connected to server');
            
            // Join session
            socket.emit('join_session', {
                session_id: sessionId
            });
        });

        socket.on('disconnect', () => {
            console.log('Disconnected from server');
        });

        socket.on('session_initialised', (data) => {
            sessionId = data.session_id;
            sessionData = data.session_data;
            
            // Store session data
            localStorage.setItem('chat_session_id', sessionId);
            storeSessionData();
            
            // Load message history from server if local storage is empty
            if (messageHistory.length === 0 && data.messages.length > 0) {
                messageHistory = data.messages;
                storeMessages();
                displayStoredMessages();
            }
        });

        socket.on('ai_response', (data) => {
            const messageData = data.message_data;
            sessionData = data.session_data;
            
            // Display AI response
            displayAIMessage(
                messageData.answer, 
                messageData.timestamp, 
                messageData.duration
            );
            
            // Store message data and session data
            messageHistory.push(messageData);
            storeMessages();
            storeSessionData();
                                
            // Re-enable input
            chatInput.disabled = false;
            chatInput.placeholder = 'Type your message...';
            chatInput.focus();
        });

        socket.on('error', (data) => {
            console.error('Socket error:', data);
            displayErrorMessage(data.message || 'An error occurred');
            chatInput.disabled = false;
        });
    }

    // Session and Message Management
    function getStoredSessionId() {
        let sessionId = localStorage.getItem('chat_session_id');
        if (!sessionId) {
            sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
            localStorage.setItem('chat_session_id', sessionId);
        }
        return sessionId;
    }

    function getStoredMessages() {
        const stored = localStorage.getItem('chat_message_history');
        return stored ? JSON.parse(stored) : [];
    }

    function storeMessages() {
        localStorage.setItem('chat_message_history', JSON.stringify(messageHistory));
    }

    function storeSessionData() {
        if (sessionData) {
            localStorage.setItem('chat_session_data', JSON.stringify(sessionData));
        }
    }

    // Resets the chat to its initial state.
    function restartChat() {
        // End current session properly
        if (socket && socket.connected && sessionId) {
            socket.emit('end_session', {
                session_id: sessionId
            });
        }
        
        // Clear all stored data
        localStorage.clear();
        
        // Generate new session ID
        sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        localStorage.setItem('chat_session_id', sessionId);
        
        // Reset message history and session data
        messageHistory = [];
        sessionData = null;
        
        // Reset UI elements
        chatMessages.innerHTML = '';
        welcomeMessage.classList.remove('hidden');
        chatStarted = false;
        restartButton.disabled = true;
        sendButton.disabled = true;
        chatInput.disabled = false;
        chatInput.placeholder = 'Type your message...';
        chatInput.focus();
        chatMessages.scrollTop = 0;
        
        // Join new session
        if (socket && socket.connected) {
            socket.emit('join_session', {
                session_id: sessionId
            });
        }
    }

    // Sending Messages
    function sendMessage() {
        const message = chatInput.value.trim();

        if (!message) return;

        // Display user message immediately
        // Create the timestamp in BST (May have to adjust based on timezone)
        const now = new Date();
        const bstOffset = -120;
        const bstTime = new Date(now.getTime() - (bstOffset * 60000));
        const timestamp = bstTime.toISOString().replace('Z', '+01:00');
        displayUserMessage(message, timestamp);

        // Disable send button and show loading state
        sendButton.disabled = true;
        chatInput.disabled = true;

        // Send message to server
        socket.emit('user_message', {
            session_id: sessionId,
            message: message
        });

        chatInput.value = '';
        chatInput.style.height = 'auto';
        chatInput.placeholder = 'Just a second...';
    }

    function handleFormSubmit(e) {
        e.preventDefault();
        if (!chatStarted) {
            welcomeMessage.classList.add('hidden');
            chatStarted = true;
            localStorage.setItem('chat_started', 'true');
            restartButton.disabled = false;
        }
        const userInput = chatInput.value.trim();
        if (userInput) {
            sendMessage();
            showTypingIndicator();
        }
    }

    // Displaying Messages
    function displayStoredMessages() {
        messageHistory.forEach(messageData => {
            displayUserMessage(messageData.question, messageData.timestamp, false);
            displayAIMessage(messageData.answer, messageData.timestamp, messageData.duration, false);
        });
    }
    
    function displayUserMessage(message, timestamp, animate = true) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message user';
        const time = new Date(timestamp).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
            timeZone: 'UTC' // Replace with your actual timezone
        });
        
        messageDiv.innerHTML = `
            <div class="message-avatar" aria-label="Message from Me">ME</div>
            <div class="message-content" role="group">
                <div class="message-bubble">
                    ${escapeHtml(message)}
                </div>
                <time class="message-time" datetime="${time}">${time}</time> 
            </div>
        `;
        chatMessages.appendChild(messageDiv);
        scrollToBottom();
    }

    function displayAIMessage(message, timestamp, duration = null, animate = true) {
        removeTypingIndicator();
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message ai';
        const time = new Date(timestamp).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
            timeZone: 'UTC' // Replace with your actual timezone
        });
        const durationText = duration ? ` • ${duration.toFixed(1)}s` : '';

        const markdownText = escapeHtml(message);
        messageDiv.innerHTML = `
            <div class="message-avatar" aria-label="Message from AI">AI</div>
            <div class="message-content" role="group">
                <div class="message-bubble">
                    ${marked.parse(markdownText)}
                </div>
                <time class="message-time" datetime="${time}">Assistant • ${time}${durationText}</time> 
            </div>   
        `;
        chatMessages.appendChild(messageDiv);
        scrollToBottom();
    }

    function displayErrorMessage(message) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message ai';
        
        messageDiv.innerHTML = `
            <div class="message-bubble" style="background: #fef2f2; color: #dc2626; border-color: #fecaca;">
                ⚠️ ${escapeHtml(message)}
            </div>
            <div class="message-time">System Error</div>
        `;

        chatMessages.appendChild(messageDiv);
        scrollToBottom();
    }

    // Utility Functions
    function showTypingIndicator() {
        const indicatorElement = document.createElement('div');
        indicatorElement.className = 'typing-indicator-container';
        indicatorElement.innerHTML = `
            <div class="typing-indicator">
                <span></span><span></span><span></span>
            </div>
        `;
        chatMessages.appendChild(indicatorElement);
        scrollToBottom();
    }
    
    function removeTypingIndicator() {
        const indicator = document.querySelector('.typing-indicator-container');
        if (indicator) indicator.remove();
    }

    function scrollToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    initializeEventListeners();
    initializeSocket();
    displayStoredMessages();

});
