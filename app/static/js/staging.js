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

// Apply dynamic progress width from template data attribute.
window.addEventListener('load', () => {
  const progressFill = document.querySelector('.stepper-bar__fill[data-progress]');
  if (!progressFill) return;
  const progress = Number(progressFill.getAttribute('data-progress'));
  if (!Number.isNaN(progress)) {
    progressFill.style.width = `${Math.max(0, Math.min(100, progress))}%`;
  }
});

/* ─── STEP COLLAPSING & CURRENT-STEP HIGHLIGHT ─── */
(function() {
  const tasks = document.querySelectorAll('.task[data-step]');
  let currentFound = false;

  tasks.forEach(task => {
    const status = task.dataset.status;  // 'done', 'fail', or 'pending'
    const isLocked = task.classList.contains('is-locked');

    // Auto-collapse completed steps
    if (status === 'done') {
      task.classList.add('task--collapsed');
    }

    // Highlight the first non-done, non-locked step as "current"
    if (!currentFound && status !== 'done' && !isLocked) {
      task.classList.add('task--current');
      currentFound = true;

      // Scroll sidebar to show current step after a short delay
      setTimeout(() => {
        task.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }, 300);
    }
  });

  // Toggle collapse on click
  document.querySelectorAll('.task__top').forEach(top => {
    top.addEventListener('click', (e) => {
      // Don't toggle if user is clicking a badge or the form within
      if (e.target.closest('.badge') || e.target.closest('form')) return;
      const task = top.closest('.task');
      if (task && !task.classList.contains('is-locked')) {
        task.classList.toggle('task--collapsed');
      }
    });
  });
})();

/* ─── LOADING SPINNER ON FORM SUBMIT ─── */
document.querySelectorAll('.btn--submit').forEach(btn => {
  const form = btn.closest('form');
  if (form) {
    form.addEventListener('submit', () => {
      btn.classList.add('is-loading');
    });
  }
});

// New Experiment button functionality
const newExpBtn = document.getElementById('newExperimentBtn');
if (newExpBtn) {
  newExpBtn.addEventListener('click', function(e) {
    e.preventDefault();
    
    // Set the active section to 'tools' so it opens on the Tools section after redirect
    localStorage.setItem('activeSidebarSection', 'tools');
    
    // Disable button and show loading state
    newExpBtn.disabled = true;
    newExpBtn.textContent = 'Creating...';
    
    // Create a form and submit it to create a new experiment
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = '/staging/experiment/new';
    document.body.appendChild(form);
    form.submit();
  });
}

// Experiment card menu actions (rename/delete)
const experimentMenus = document.querySelectorAll('.experiment-menu');

function closeAllExperimentMenus() {
  experimentMenus.forEach(menu => menu.classList.remove('is-open'));
}

experimentMenus.forEach(menu => {
  const toggle = menu.querySelector('.experiment-menu__toggle');
  if (!toggle) return;

  toggle.addEventListener('click', function(e) {
    e.preventDefault();
    e.stopPropagation();

    const isOpen = menu.classList.contains('is-open');
    closeAllExperimentMenus();
    if (!isOpen) {
      menu.classList.add('is-open');
    }
  });
});

document.addEventListener('click', function() {
  closeAllExperimentMenus();
});

document.querySelectorAll('.experiment-menu__item').forEach(actionBtn => {
  actionBtn.addEventListener('click', function(e) {
    e.preventDefault();
    e.stopPropagation();

    const action = this.getAttribute('data-action');
    const expId = this.getAttribute('data-exp-id');
    const expName = this.getAttribute('data-exp-name') || '';
    const currentId = this.getAttribute('data-current-id') || '';

    if (!expId) return;

    if (action === 'rename') {
      const newName = window.prompt('Rename experiment:', expName);
      if (!newName) return;

      const trimmedName = newName.trim();
      if (!trimmedName) return;

      const form = document.createElement('form');
      form.method = 'POST';
      form.action = '/staging/experiment/rename';

      const expIdInput = document.createElement('input');
      expIdInput.type = 'hidden';
      expIdInput.name = 'experiment_id';
      expIdInput.value = expId;
      form.appendChild(expIdInput);

      const currentIdInput = document.createElement('input');
      currentIdInput.type = 'hidden';
      currentIdInput.name = 'current_experiment_id';
      currentIdInput.value = currentId;
      form.appendChild(currentIdInput);

      const nameInput = document.createElement('input');
      nameInput.type = 'hidden';
      nameInput.name = 'name';
      nameInput.value = trimmedName;
      form.appendChild(nameInput);

      document.body.appendChild(form);
      form.submit();
    }

    if (action === 'delete') {
      const confirmed = window.confirm(`Delete experiment "${expName}"? This cannot be undone.`);
      if (!confirmed) return;

      const form = document.createElement('form');
      form.method = 'POST';
      form.action = '/staging/experiment/delete';

      const expIdInput = document.createElement('input');
      expIdInput.type = 'hidden';
      expIdInput.name = 'experiment_id';
      expIdInput.value = expId;
      form.appendChild(expIdInput);

      const currentIdInput = document.createElement('input');
      currentIdInput.type = 'hidden';
      currentIdInput.name = 'current_experiment_id';
      currentIdInput.value = currentId;
      form.appendChild(currentIdInput);

      document.body.appendChild(form);
      form.submit();
    }
  });
});

// Click experiment card to open
document.querySelectorAll('.experiment-item[data-open-url]').forEach(card => {
  card.addEventListener('click', function(e) {
    if (e.target.closest('.experiment-menu, .experiment-item__actions, .experiment-item__rename-form, a, button, input, select, textarea, label, form')) {
      return;
    }

    const openUrl = this.getAttribute('data-open-url');
    if (openUrl) {
      window.location.href = openUrl;
    }
  });
});

