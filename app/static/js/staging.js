// Initialize sidebar on page load
function initializeSidebar() {
  // Get saved section from localStorage, default to 'tools'
  const savedSection = localStorage.getItem('activeSidebarSection') || 'tools';
  
  // Find and click the corresponding taskbar item
  const taskbarItem = document.querySelector(`.taskbar__item[data-section="${savedSection}"]`);
  if (taskbarItem) {
    taskbarItem.click();
  }
}

// Taskbar navigation functionality
document.querySelectorAll('.taskbar__item').forEach(item => {
  item.addEventListener('click', function(e) {
    e.preventDefault();
    
    // Remove active state from all taskbar items
    document.querySelectorAll('.taskbar__item').forEach(el => {
      el.classList.remove('taskbar__item--active');
    });
    
    // Add active state to clicked taskbar item
    this.classList.add('taskbar__item--active');
    
    // Get the section name
    const section = this.getAttribute('data-section');
    
    // Save to localStorage
    localStorage.setItem('activeSidebarSection', section);
    
    // Hide all sidebar sections
    document.querySelectorAll('.sidebar__section').forEach(el => {
      el.classList.remove('sidebar__section--active');
    });
    
    // Show the selected section
    const targetSection = document.querySelector('.sidebar__section--' + section);
    if (targetSection) {
      targetSection.classList.add('sidebar__section--active');
    }
  });
});

// Initialize on page load
window.addEventListener('load', initializeSidebar);

// New Experiment button functionality
const newExpBtn = document.getElementById('newExperimentBtn');
if (newExpBtn) {
  newExpBtn.addEventListener('click', function(e) {
    e.preventDefault();
    
    // Switch to Tools sidebar
    const toolsItem = document.querySelector('.taskbar__item[data-section="tools"]');
    if (toolsItem) {
      toolsItem.click();
    }
    
    // Clear the UniProt accession input field
    const accessionInput = document.querySelector('input[name="accession"]');
    if (accessionInput) {
      accessionInput.value = '';
      accessionInput.focus();
    }
    
    // Scroll to top of sidebar
    const sidebar = document.querySelector('.sidebar');
    if (sidebar) {
      sidebar.scrollTop = 0;
    }
  });
}

// AI Chat Helper functionality
const chatInput = document.getElementById('chatInput');
const chatSendBtn = document.getElementById('chatSendBtn');
const chatMessages = document.getElementById('chatMessages');

function addChatMessage(text, isUser = false) {
  const messageDiv = document.createElement('div');
  messageDiv.className = `chat-message ${isUser ? 'chat-message--user' : 'chat-message--bot'}`;
  
  const contentDiv = document.createElement('div');
  contentDiv.className = 'chat-message__content';
  contentDiv.textContent = text;
  
  messageDiv.appendChild(contentDiv);
  chatMessages.appendChild(messageDiv);
  
  // Auto-scroll to bottom
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function sendChatMessage() {
  const message = chatInput.value.trim();
  if (!message) return;
  
  // Add user message
  addChatMessage(message, true);
  chatInput.value = '';
  
  // Simulate bot response (placeholder - can be connected to backend later)
  setTimeout(() => {
    const responses = [
      "That's a great question! I'm here to help with your workflow.",
      "I can help you understand the steps. What would you like to know?",
      "Feel free to ask me anything about the staging process.",
      "I'm learning! Can you tell me more about what you need?",
    ];
    const randomResponse = responses[Math.floor(Math.random() * responses.length)];
    addChatMessage(randomResponse, false);
  }, 500);
}

// Send message on button click
if (chatSendBtn) {
  chatSendBtn.addEventListener('click', sendChatMessage);
}

// Send message on Enter key
if (chatInput) {
  chatInput.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
      sendChatMessage();
    }
  });
}

