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
      if (e.target.closest('.badge') || e.target.closest('.task__state') || e.target.closest('form')) return;
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

// Top results generation filter (format: "min-max")
const genFilterInput = document.getElementById('topResultsGenFilter');
if (genFilterInput) {
  genFilterInput.addEventListener('input', () => {
    const raw = genFilterInput.value.trim();
    const match = raw.match(/^(\d+)\s*-\s*(\d+)$/);
    const rows = document.querySelectorAll('.top-results__table tbody tr[data-generation]');
    rows.forEach((row) => {
      const gen = Number(row.getAttribute('data-generation'));
      let visible = true;
      if (raw.length > 0 && match) {
        const min = Number(match[1]);
        const max = Number(match[2]);
        visible = gen >= min && gen <= max;
      }
      row.style.display = visible ? '' : 'none';
    });
  });
}

// Variant detail modal
const variantModal = document.getElementById('variantModal');
const modalEls = {
  rank: document.getElementById('modalRank'),
  variantId: document.getElementById('modalVariantId'),
  generation: document.getElementById('modalGeneration'),
  parentVariant: document.getElementById('modalParentVariant'),
  variant: document.getElementById('modalVariant'),
  activity: document.getElementById('modalActivity'),
  mutationsBody: document.getElementById('modalMutationsBody'),
  proteinSnippet: document.getElementById('modalProteinSnippet'),
  dnaLink: document.getElementById('modalDownloadDna'),
  proteinLink: document.getElementById('modalDownloadProtein'),
  mutCsvLink: document.getElementById('modalDownloadMutCsv'),
};

function closeVariantModal() {
  if (!variantModal) return;
  variantModal.classList.remove('is-open');
  variantModal.setAttribute('aria-hidden', 'true');
}

function renderMutationRows(mutations) {
  if (!modalEls.mutationsBody) return;
  if (!mutations || mutations.length === 0) {
    modalEls.mutationsBody.innerHTML = '<tr><td colspan="4">No mutation data.</td></tr>';
    return;
  }
  modalEls.mutationsBody.innerHTML = mutations.map((m) => {
    const aa = `${m.wt_aa || '-'} -> ${m.var_aa || '-'}`;
    const nt = `${m.wt_codon || '-'} -> ${m.var_codon || '-'}`;
    const pos = m.aa_position || m.codon_index || '-';
    return `<tr>
      <td>${m.mutation_type || '-'}</td>
      <td>${aa}</td>
      <td>${nt}</td>
      <td>${pos}</td>
    </tr>`;
  }).join('');
}

if (variantModal) {
  document.querySelectorAll('.js-view-variant').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const variantId = btn.dataset.variantId;
      if (!variantId) return;

      if (modalEls.rank) modalEls.rank.textContent = `#${btn.dataset.rank || '-'}`;
      if (modalEls.variantId) modalEls.variantId.textContent = String(variantId);
      if (modalEls.generation) modalEls.generation.textContent = btn.dataset.generation || '-';
      if (modalEls.parentVariant) modalEls.parentVariant.textContent = '-';
      if (modalEls.variant) modalEls.variant.textContent = btn.dataset.variant || '-';
      if (modalEls.activity) modalEls.activity.textContent = btn.dataset.activity || '-';
      renderMutationRows([]);
      if (modalEls.proteinSnippet) modalEls.proteinSnippet.textContent = '-';
      if (modalEls.dnaLink) modalEls.dnaLink.href = '#';
      if (modalEls.proteinLink) modalEls.proteinLink.href = '#';
      if (modalEls.mutCsvLink) modalEls.mutCsvLink.href = '#';

      variantModal.classList.add('is-open');
      variantModal.setAttribute('aria-hidden', 'false');

      try {
        const resp = await fetch(`/staging/variant/${variantId}/details`, { credentials: 'same-origin' });
        if (!resp.ok) return;
        const data = await resp.json();
        if (modalEls.variantId) modalEls.variantId.textContent = data.variant_id ?? '-';
        if (modalEls.generation) modalEls.generation.textContent = data.generation_number ?? '-';
        if (modalEls.parentVariant) modalEls.parentVariant.textContent = data.parent_variant_id ?? 'None';
        if (modalEls.variant) modalEls.variant.textContent = data.variant_index ?? '-';
        if (modalEls.activity) modalEls.activity.textContent = data.activity_score ?? '-';
        if (modalEls.proteinSnippet) modalEls.proteinSnippet.textContent = data.protein_snippet || 'Not available';
        renderMutationRows(data.mutations || []);

        if (data.download_urls) {
          if (modalEls.dnaLink) modalEls.dnaLink.href = data.download_urls.dna_fasta || '#';
          if (modalEls.proteinLink) modalEls.proteinLink.href = data.download_urls.protein_fasta || '#';
          if (modalEls.mutCsvLink) modalEls.mutCsvLink.href = data.download_urls.mutation_csv || '#';
        }
      } catch (err) {
        // Keep drawer open with fallback values.
      }
    });
  });

  document.querySelectorAll('.js-close-variant-modal').forEach((el) => {
    el.addEventListener('click', closeVariantModal);
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeVariantModal();
  });
}

// Warning drill-down: summary + classification + filters
function classifyWarning(text) {
  const t = (text || '').toLowerCase();
  const rowMatch = t.match(/row\s+(\d+)/i);
  const fieldMatch = t.match(/(variant_index|parent_variant_index|generation|assembled_dna_sequence|dna_yield|protein_yield|field\s+'?([a-z0-9_]+)'?)/i);

  let category = 'other';
  let severity = 'advisory';
  let fix = 'Review this record and re-upload.';

  if (t.includes('duplicate') && t.includes('variant')) {
    category = 'duplicate_variant_index';
    severity = 'critical';
    fix = 'Use unique variant_index values for each record.';
  } else if ((t.includes('missing') && t.includes('field')) || t.includes('no generation 0')) {
    category = 'missing_fields';
    severity = 'critical';
    fix = 'Add required fields/controls and re-upload.';
  } else if (t.includes('invalid') || t.includes('must be') || t.includes('not a')) {
    category = 'invalid_values';
    severity = 'critical';
    fix = 'Correct value type/format for this field.';
  } else if (t.includes('orphan') || t.includes('parent_variant_index')) {
    category = 'lineage_reference';
    severity = 'critical';
    fix = 'Ensure parent_variant_index points to an existing parent variant.';
  } else if (t.includes('warning')) {
    category = 'quality_warning';
    severity = 'advisory';
    fix = 'Check whether this warning is acceptable for your analysis.';
  }

  return {
    category,
    severity,
    row: rowMatch ? rowMatch[1] : '-',
    field: fieldMatch ? (fieldMatch[2] || fieldMatch[1]) : '-',
    issue: text || '',
    fix,
  };
}

function initWarningInsights() {
  const rows = Array.from(document.querySelectorAll('.js-warning-row'));
  if (rows.length === 0) return;

  const counts = {
    missing_fields: 0,
    invalid_values: 0,
    duplicate_variant_index: 0,
    other: 0,
  };

  rows.forEach((row) => {
    const warningText = row.getAttribute('data-warning-text') || '';
    const p = classifyWarning(warningText);
    row.dataset.severity = p.severity;
    row.dataset.category = p.category;

    const sevCell = row.querySelector('[data-col="severity"]');
    const rowCell = row.querySelector('[data-col="row"]');
    const fieldCell = row.querySelector('[data-col="field"]');
    const issueCell = row.querySelector('[data-col="issue"]');
    const fixCell = row.querySelector('[data-col="fix"]');
    if (sevCell) sevCell.textContent = p.severity;
    if (rowCell) rowCell.textContent = p.row;
    if (fieldCell) fieldCell.textContent = p.field;
    if (issueCell) issueCell.textContent = p.issue;
    if (fixCell) fixCell.textContent = p.fix;

    if (p.category === 'missing_fields') counts.missing_fields += 1;
    else if (p.category === 'invalid_values') counts.invalid_values += 1;
    else if (p.category === 'duplicate_variant_index') counts.duplicate_variant_index += 1;
    else counts.other += 1;
  });

  const summary = document.querySelector('[data-warning-summary]');
  if (summary) {
    const total = rows.length;
    const parts = [];
    if (counts.missing_fields > 0) parts.push(`${counts.missing_fields} missing fields`);
    if (counts.invalid_values > 0) parts.push(`${counts.invalid_values} invalid values`);
    if (counts.duplicate_variant_index > 0) parts.push(`${counts.duplicate_variant_index} duplicate variant index`);
    if (counts.other > 0) parts.push(`${counts.other} other`);
    summary.textContent = `${total} warnings: ${parts.join(', ')}`;
  }

  const filterButtons = Array.from(document.querySelectorAll('.js-warning-filter'));
  const applyFilter = (mode) => {
    rows.forEach((row) => {
      const critical = row.dataset.severity === 'critical';
      row.style.display = (mode === 'all' || critical) ? '' : 'none';
    });
    filterButtons.forEach((btn) => {
      btn.classList.toggle('is-active', btn.getAttribute('data-filter') === mode);
    });
  };

  filterButtons.forEach((btn) => {
    btn.addEventListener('click', () => {
      applyFilter(btn.getAttribute('data-filter') || 'all');
    });
  });

  applyFilter('critical');
}

initWarningInsights();


