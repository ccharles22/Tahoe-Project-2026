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

// AI Chat Helper — context-aware workflow assistant
const chatInput = document.getElementById('chatInput');
const chatSendBtn = document.getElementById('chatSendBtn');
const chatMessages = document.getElementById('chatMessages');
const robot = document.getElementById('chatRobot');

/* ─── Robot animation helpers ─── */
function setRobotState(state, durationMs) {
  if (!robot) return;
  // clear previous states
  robot.classList.remove('robot--thinking','robot--talking','robot--happy','robot--wave');
  if (state) robot.classList.add(`robot--${state}`);
  if (durationMs) {
    setTimeout(() => robot.classList.remove(`robot--${state}`), durationMs);
  }
}

// Wave on page load
if (robot) {
  setTimeout(() => setRobotState('wave', 1600), 600);

  // Random idle expressions
  setInterval(() => {
    if (robot.classList.contains('robot--thinking') || robot.classList.contains('robot--talking')) return;
    const idle = ['wave','happy',''][Math.floor(Math.random() * 3)];
    if (idle) setRobotState(idle, 1200);
  }, 12000);

  // Click to get a random tip
  robot.addEventListener('click', () => {
    setRobotState('happy', 1500);
    const tips = [
      'Tip: Complete steps in order — each unlocks the next!',
      'Tip: You can find UniProt accessions at uniprot.org.',
      'Tip: TSV files need variant_index, generation, and sequence columns.',
      'Tip: Check the Experiments sidebar to switch between projects.',
      'Tip: Validation compares your plasmid FASTA against the WT protein.',
      'Tip: Generation 0 variants have no parent — they\'re your starting library.',
      'Tip: I can help with workflow steps, file formats, and troubleshooting!',
    ];
    addChatMessage(tips[Math.floor(Math.random() * tips.length)], false);
  });
}

/* ─── knowledge base: keyword patterns → answers ─── */
const KB = [
  // Workflow overview
  { keys: ['workflow','pipeline','steps','overview','how does','what do i do'],
    a: 'The workflow has 5 steps:\n\nA — Fetch a wild-type protein from UniProt\nB — Validate your plasmid FASTA against the WT\nC — Upload & parse experimental variant data (TSV/JSON)\nD — Run analysis (activity metrics, top-10 variants)\nE — Process DNA→protein sequences\n\nComplete them in order — each step unlocks after the previous one.' },

  // Step A
  { keys: ['step a','uniprot','wild-type','wt','accession','fetch wt','protein'],
    a: 'Step A fetches a wild-type protein from UniProt using its accession ID (e.g. O34996 for BsuPol). It retrieves the amino acid sequence, sequence length, and annotated functional domains, then creates an Experiment record linked to that protein.' },

  // Step B
  { keys: ['step b','plasmid','fasta','validate','validation'],
    a: 'Step B validates your plasmid FASTA file against the wild-type protein\'s back-translated DNA. It checks sequence identity, coverage, strand orientation, and whether the insert wraps the origin. A PASS means your plasmid encodes the expected protein.' },

  // Step C
  { keys: ['step c','upload','parsing','tsv','csv','json','data file','file format','format'],
    a: 'Step C accepts a TSV, CSV, or JSON file with your directed evolution data. Required columns:\n\n• variant_index (int) — unique variant ID\n• generation (int) — selection round\n• parent_variant_index (int, empty for gen 0)\n• assembled_dna_sequence (A/T/G/C)\n• dna_yield (numeric)\n• protein_yield (numeric)\n\nThe system parses, runs QC, and inserts into the database.' },

  // Step D
  { keys: ['step d','analysis','run analysis','activity','metrics','top 10','top10'],
    a: 'Step D runs the analysis pipeline on your uploaded data. It calculates unified activity metrics, generates an activity distribution plot, identifies the top-10 performing variants, and produces a QC debug report. Results appear in the workspace panel.' },

  // Step E
  { keys: ['step e','sequence','process','dna to protein','translation','processing'],
    a: 'Step E translates assembled DNA sequences into protein sequences and computes alignment-based metrics against the wild-type. This lets you track mutations and functional changes across generations.' },

  // Directed evolution concepts
  { keys: ['directed evolution','what is directed','evolution','de ','mutagenesis'],
    a: 'Directed evolution is a method to engineer proteins by mimicking natural selection in the lab. You create variant libraries through mutagenesis, screen for desired activity (e.g. yield), and carry winners into the next generation. This platform tracks that process across multiple rounds.' },

  // Generation / variant
  { keys: ['generation','variant','parent','lineage','round'],
    a: 'A "generation" (or round) is one cycle of mutagenesis + screening. Each variant has a variant_index, belongs to a generation, and may reference a parent_variant_index from the previous generation. Generation 0 variants have no parent.' },

  // Experiment management
  { keys: ['experiment','sidebar','switch','open','new experiment'],
    a: 'Use the Experiments tab in the left sidebar to see all your experiments. Click "Open" to switch between them, or "New Experiment" to start fresh. Each experiment tracks its own WT protein, plasmid validation, and variant data independently.' },

  // Errors / troubleshooting
  { keys: ['error','fail','problem','not working','broken','bug','issue'],
    a: 'Common issues:\n\n• "Fetch WT" fails → check the UniProt accession is valid\n• Plasmid validation FAIL → your insert may not match the WT protein; check strand/frame\n• Parse errors → ensure your file has the required columns and correct data types\n• Steps disabled → complete earlier steps first (each unlocks the next)' },

  // QC
  { keys: ['qc','quality','threshold','warning','warnings'],
    a: 'Quality control checks run automatically during parsing (Step C). Warnings flag potential issues like unusual yields or missing sequences but don\'t block upload. Errors (critical problems) will prevent data from being stored. Check the warnings panel in results for details.' },

  // UniProt
  { keys: ['uniprot id','accession id','o34996','bsupol','p00000'],
    a: 'A UniProt accession ID is a unique identifier for a protein (e.g. O34996 for Bacillus subtilis DNA Polymerase I). You can find accession IDs by searching uniprot.org. Enter just the ID (not the full URL) in Step A.' },

  // Database
  { keys: ['database','postgres','stored','saved','persist','where is my data'],
    a: 'All data is stored in a PostgreSQL database with a normalized schema: Experiments → Generations → Variants → Metrics. Your WT protein and features are also saved. Data persists across sessions — you can close the browser and come back.' },
];

function getPageContext() {
  const ctx = [];
  const pill = document.querySelector('.pill strong');
  if (pill) ctx.push(`experiment #${pill.textContent}`);
  const badges = document.querySelectorAll('.task .badge');
  badges.forEach((b, i) => {
    const step = String.fromCharCode(65 + i);  // A, B, C, …
    ctx.push(`Step ${step}: ${b.textContent.trim()}`);
  });
  return ctx.join(', ');
}

function findAnswer(msg) {
  const lower = msg.toLowerCase();

  // Check knowledge base
  for (const entry of KB) {
    if (entry.keys.some(k => lower.includes(k))) {
      return entry.a;
    }
  }

  // Context-aware fallback
  const ctx = getPageContext();
  if (ctx) {
    return `I'm not sure about that specific question, but here's your current state: ${ctx}.\n\nTry asking about a specific step (A–E), file formats, directed evolution, or troubleshooting.`;
  }

  return 'I can help with:\n\n• The 5-step workflow (A–E)\n• File format requirements\n• Directed evolution concepts\n• Troubleshooting errors\n\nTry asking something like "What format does Step C expect?" or "What is directed evolution?"';
}

function addChatMessage(text, isUser = false) {
  const messageDiv = document.createElement('div');
  messageDiv.className = `chat-message ${isUser ? 'chat-message--user' : 'chat-message--bot'}`;

  const contentDiv = document.createElement('div');
  contentDiv.className = 'chat-message__content';
  contentDiv.style.whiteSpace = 'pre-line';
  contentDiv.textContent = text;

  messageDiv.appendChild(contentDiv);
  chatMessages.appendChild(messageDiv);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function sendChatMessage() {
  const message = chatInput.value.trim();
  if (!message) return;

  addChatMessage(message, true);
  chatInput.value = '';

  // Robot thinks while "processing"
  setRobotState('thinking');

  // Brief delay, then answer
  setTimeout(() => {
    setRobotState('talking');
    const answer = findAnswer(message);
    addChatMessage(answer, false);

    // After talking, show happy for a moment then return to idle
    setTimeout(() => setRobotState('happy', 1500), answer.length * 8);
  }, 500 + Math.random() * 300);
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

