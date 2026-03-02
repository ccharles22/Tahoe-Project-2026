/**
 * staging.js
 * Client-side interaction handlers for the staging workspace.
 *
 * Scope:
 * - Sidebar/task navigation and persisted UI state
 * - Step/task affordances (collapse, current-step focus, loading state)
 * - Experiment list actions (open, rename, delete, create)
 * - Result exploration UI (filters, variant detail modal, warning insights)
 *
 * Note: Server-side validation and authorization remain the source of truth.
 */

// Initialize sidebar on page load
// Restore the last active sidebar section between page loads.
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

function initializeTaskbarDna() {
  const track = document.querySelector('[data-taskbar-dna-track]');
  if (!track) return;

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const bases = ['A', 'C', 'G', 'T'];

  const buildTrack = () => {
    const railWidth = track.parentElement
      ? track.parentElement.getBoundingClientRect().width
      : 112;
    const rowHeight = 20;
    const rowCount = Math.max(16, Math.ceil((window.innerHeight * 1.12) / rowHeight));
    const baseCount = Math.max(12, Math.ceil(railWidth / 10) + 8);

    const createRow = () => {
      let row = '';
      for (let idx = 0; idx < baseCount; idx += 1) {
        const base = bases[Math.floor(Math.random() * bases.length)];
        row += `<span class="taskbar__dna-base--${base}">${base}</span>`;
      }
      return `<span class="taskbar__dna-row">${row}</span>`;
    };

    let firstSet = '';
    for (let idx = 0; idx < rowCount; idx += 1) {
      firstSet += createRow();
    }

    track.innerHTML = `${firstSet}${firstSet}`;
    if (reduceMotion) {
      track.style.animation = 'none';
      track.style.transform = 'rotate(-3deg) scale(1.02)';
    }
  };

  let resizeFrame = null;
  const scheduleBuild = () => {
    if (resizeFrame !== null) {
      window.cancelAnimationFrame(resizeFrame);
    }
    resizeFrame = window.requestAnimationFrame(() => {
      resizeFrame = null;
      buildTrack();
    });
  };

  buildTrack();
  window.addEventListener('resize', scheduleBuild, { passive: true });
}

window.addEventListener('load', initializeTaskbarDna);

// Apply dynamic progress width from template data attribute.
window.addEventListener('load', () => {
  const progressFill = document.querySelector('.stepper-bar__fill[data-progress]');
  if (!progressFill) return;
  const progress = Number(progressFill.getAttribute('data-progress'));
  if (!Number.isNaN(progress)) {
    progressFill.style.width = `${Math.max(0, Math.min(100, progress))}%`;
  }
});

/* STEP COLLAPSING & CURRENT-STEP HIGHLIGHT */
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

/* LOADING SPINNER ON FORM SUBMIT */
document.querySelectorAll('.btn--submit').forEach(btn => {
  const form = btn.closest('form');
  if (form) {
    form.addEventListener('submit', () => {
      btn.classList.add('is-loading');
    });
  }
});

function initRunLoader() {
  const loader = document.getElementById('runLoader');
  if (!loader) return;

  const titleEl = document.getElementById('runLoaderTitle');
  const textEl = document.getElementById('runLoaderText');

  const copy = {
    sequence: {
      title: 'Processing Sequences',
      text: 'The DNA reference is rotating through translation and mutation-calling now. This page will refresh when the run finishes.',
    },
    analysis: {
      title: 'Running Analysis',
      text: 'The portal is refreshing metrics, plots, and reports now. This page will update automatically when the run finishes.',
    },
  };

  const showLoader = (mode) => {
    const content = copy[mode] || copy.analysis;
    if (titleEl) titleEl.textContent = content.title;
    if (textEl) textEl.textContent = content.text;
    loader.classList.add('is-visible');
    loader.setAttribute('aria-hidden', 'false');
    document.body.classList.add('is-run-loading');
  };

  const hideLoader = () => {
    loader.classList.remove('is-visible');
    loader.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('is-run-loading');
  };

  const readJsonPayload = async (response) => {
    const contentType = (response.headers.get('content-type') || '').toLowerCase();
    if (!contentType.includes('application/json')) {
      const bodyText = (await response.text()).trim();
      const preview = bodyText ? bodyText.slice(0, 300) : `status ${response.status}`;
      throw new Error(`Unexpected non-JSON response: ${preview}`);
    }
    return response.json();
  };

  document
    .querySelectorAll('form[action*="/sequence/run"], form[action*="/analysis/run"]')
    .forEach((form) => {
      form.addEventListener('submit', async (event) => {
        event.preventDefault();
        if (form.dataset.submitting === 'true') return;

        const mode = form.action.includes('/sequence/run') ? 'sequence' : 'analysis';
        const submitBtn = form.querySelector('.btn--submit');
        form.dataset.submitting = 'true';
        if (submitBtn) submitBtn.classList.add('is-loading');
        showLoader(mode);

        try {
          const response = await fetch(form.action, {
            method: form.method || 'POST',
            body: new FormData(form),
            credentials: 'same-origin',
            redirect: 'follow',
            headers: {
              'X-Requested-With': 'XMLHttpRequest',
            },
          });

          if (mode === 'sequence') {
            const payload = await readJsonPayload(response);
            if (payload.state === 'completed') {
              window.location.reload();
              return;
            }
            if (payload.state === 'failed') {
              const rawTarget = payload.redirect_url || window.location.href;
              const targetUrl = new URL(rawTarget, window.location.href);
              targetUrl.searchParams.set('_refresh', String(Date.now()));
              window.location.assign(targetUrl.toString());
              return;
            }
            throw new Error(`Unexpected sequence state: ${payload.state}`);
          }

          const payload = await readJsonPayload(response);
          if (payload.state === 'completed' || payload.state === 'failed') {
            const rawTarget = payload.redirect_url || window.location.href;
            const targetUrl = new URL(rawTarget, window.location.href);
            targetUrl.searchParams.set('_refresh', String(Date.now()));
            window.location.assign(targetUrl.toString());
            return;
          }

          throw new Error(`Unexpected analysis state: ${payload.state}`);
        } catch (error) {
          console.error('Run request failed:', error);
          hideLoader();
          form.dataset.submitting = 'false';
          if (submitBtn) submitBtn.classList.remove('is-loading');
          window.alert('The run request did not finish. The page stayed in place so you can try again.');
        }
      });
    });
}

initRunLoader();

// Click experiment card to open
document.querySelectorAll('.experiment-item[data-open-url]').forEach(card => {
  const openCard = () => {
    const openUrl = card.getAttribute('data-open-url');
    if (openUrl) {
      window.location.href = openUrl;
    }
  };

  card.addEventListener('click', function(e) {
    if (e.target.closest('.experiment-item__actions, .experiment-item__rename-form, a, button, input, select, textarea, label, form')) {
      return;
    }
    openCard();
  });

  card.addEventListener('keydown', function(e) {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    if (e.target.closest('.experiment-item__actions, .experiment-item__rename-form, a, button, input, select, textarea, label, form')) {
      return;
    }
    e.preventDefault();
    openCard();
  });
});

// Variant detail drawer
const variantModal = document.getElementById('variantModal');
const modalEls = {
  rank: document.getElementById('modalRank'),
  variantId: document.getElementById('modalVariantId'),
  generation: document.getElementById('modalGeneration'),
  parentVariant: document.getElementById('modalParentVariant'),
  variant: document.getElementById('modalVariant'),
  activity: document.getElementById('modalActivity'),
  dnaYield: document.getElementById('modalDnaYield'),
  proteinYield: document.getElementById('modalProteinYield'),
  qcNote: document.getElementById('modalQcNote'),
  mutationsBody: document.getElementById('modalMutationsBody'),
  proteinSnippet: document.getElementById('modalProteinSnippet'),
  dnaLink: document.getElementById('modalDownloadDna'),
  proteinLink: document.getElementById('modalDownloadProtein'),
  mutCsvLink: document.getElementById('modalDownloadMutCsv'),
  fullVariantPage: document.getElementById('modalFullVariantPage'),
};

// Close the variant details modal and reset its accessibility state.
function closeVariantModal() {
  if (!variantModal) return;
  variantModal.classList.remove('is-open');
  variantModal.setAttribute('aria-hidden', 'true');
}

// Render mutation rows into the modal table with fallback values for missing fields.
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

function fmtNum(value) {
  const n = Number(value);
  if (Number.isNaN(n)) return '-';
  return n.toFixed(3);
}

async function openVariantDrawer(row) {
  if (!row || !variantModal) return;
  const variantId = row.dataset.variantId;
  if (!variantId) return;

  if (modalEls.rank) modalEls.rank.textContent = `#${row.dataset.rank || '-'}`;
  if (modalEls.variantId) modalEls.variantId.textContent = String(variantId);
  if (modalEls.generation) modalEls.generation.textContent = row.dataset.generationValue || '-';
  if (modalEls.parentVariant) modalEls.parentVariant.textContent = '-';
  if (modalEls.variant) modalEls.variant.textContent = row.dataset.variant || '-';
  if (modalEls.activity) modalEls.activity.textContent = row.dataset.activity || '-';
  if (modalEls.qcNote) modalEls.qcNote.textContent = row.dataset.qcNote || '-';
  if (modalEls.dnaYield) modalEls.dnaYield.textContent = '-';
  if (modalEls.proteinYield) modalEls.proteinYield.textContent = '-';
  renderMutationRows([]);
  if (modalEls.proteinSnippet) modalEls.proteinSnippet.textContent = '-';
  if (modalEls.dnaLink) modalEls.dnaLink.href = '#';
  if (modalEls.proteinLink) modalEls.proteinLink.href = '#';
  if (modalEls.mutCsvLink) modalEls.mutCsvLink.href = '#';
  if (modalEls.fullVariantPage) modalEls.fullVariantPage.href = '#';

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
    if (modalEls.activity) modalEls.activity.textContent = data.activity_score !== null && data.activity_score !== undefined ? fmtNum(data.activity_score) : '-';
    if (modalEls.dnaYield) modalEls.dnaYield.textContent = data.dna_yield !== null && data.dna_yield !== undefined ? fmtNum(data.dna_yield) : '-';
    if (modalEls.proteinYield) modalEls.proteinYield.textContent = data.protein_yield !== null && data.protein_yield !== undefined ? fmtNum(data.protein_yield) : '-';
    if (modalEls.qcNote) modalEls.qcNote.textContent = data.qc_note || '-';
    if (modalEls.proteinSnippet) modalEls.proteinSnippet.textContent = data.protein_snippet || 'Not available';
    renderMutationRows(data.mutations || []);

    if (data.download_urls) {
      if (modalEls.dnaLink) modalEls.dnaLink.href = data.download_urls.dna_fasta || '#';
      if (modalEls.proteinLink) modalEls.proteinLink.href = data.download_urls.protein_fasta || '#';
      if (modalEls.mutCsvLink) modalEls.mutCsvLink.href = data.download_urls.mutation_csv || '#';
    }
    if (modalEls.fullVariantPage) {
      modalEls.fullVariantPage.href = data.full_variant_url || '#';
    }
  } catch (err) {
    // Keep drawer open with fallback values.
  }
}

function initTopResultsControls() {
  const tbody = document.getElementById('topResultsBody');
  if (!tbody) return;
  const rows = Array.from(tbody.querySelectorAll('tr[data-generation]'));
  if (rows.length === 0) return;

  const genFilterInput = document.getElementById('topResultsGenFilter');
  const sortSelect = document.getElementById('topResultsSort');
  const mutantsOnly = document.getElementById('topResultsMutantsOnly');
  const aboveBaseline = document.getElementById('topResultsAboveBaseline');
  const qcOnly = document.getElementById('topResultsQcFlagged');

  const applyControls = () => {
    const raw = (genFilterInput?.value || '').trim();
    const match = raw.match(/^(\d+)\s*-\s*(\d+)$/);
    const mode = sortSelect?.value || 'activity_desc';

    rows.sort((a, b) => {
      const activityA = Number(a.dataset.activityValue || '-Infinity');
      const activityB = Number(b.dataset.activityValue || '-Infinity');
      const genA = Number(a.dataset.generation || '0');
      const genB = Number(b.dataset.generation || '0');
      const mutA = Number(a.dataset.mutationCount || '0');
      const mutB = Number(b.dataset.mutationCount || '0');

      if (mode === 'generation_asc') return genA - genB || activityB - activityA;
      if (mode === 'mutations_desc') return mutB - mutA || activityB - activityA;
      return activityB - activityA;
    });

    rows.forEach((row) => tbody.appendChild(row));

    rows.forEach((row) => {
      const gen = Number(row.dataset.generation || '0');
      const activity = Number(row.dataset.activityValue || 'NaN');
      const isMutant = row.dataset.isMutant === '1';
      const isQcFlagged = row.dataset.qcFlagged === '1';

      let visible = true;
      if (raw.length > 0 && match) {
        const min = Number(match[1]);
        const max = Number(match[2]);
        visible = gen >= min && gen <= max;
      }
      if (visible && mutantsOnly?.checked) visible = isMutant;
      if (visible && aboveBaseline?.checked) visible = !Number.isNaN(activity) && activity > 1.0;
      if (visible && qcOnly?.checked) visible = isQcFlagged;

      row.style.display = visible ? '' : 'none';
    });
  };

  if (genFilterInput) genFilterInput.addEventListener('input', applyControls);
  if (sortSelect) sortSelect.addEventListener('change', applyControls);
  if (mutantsOnly) mutantsOnly.addEventListener('change', applyControls);
  if (aboveBaseline) aboveBaseline.addEventListener('change', applyControls);
  if (qcOnly) qcOnly.addEventListener('change', applyControls);

  rows.forEach((row) => {
    if (!row.dataset.variantId) return;
    row.addEventListener('click', () => openVariantDrawer(row));
    row.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        openVariantDrawer(row);
      }
    });
  });

  applyControls();
}

if (variantModal) {
  document.querySelectorAll('.js-close-variant-modal').forEach((el) => {
    el.addEventListener('click', closeVariantModal);
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeVariantModal();
  });
}

initTopResultsControls();

// Keep iframe explorer labels in sync with the currently selected view.
function initExplorerLabels() {
  const links = document.querySelectorAll('.js-explorer-label-link[data-explorer-title-target]');
  if (!links.length) return;

  links.forEach((link) => {
    link.addEventListener('click', () => {
      const titleTargetId = link.getAttribute('data-explorer-title-target');
      const descriptionTargetId = link.getAttribute('data-explorer-description-target');
      const tooltipTargetId = link.getAttribute('data-explorer-tooltip-target');
      const title = link.getAttribute('data-explorer-title') || link.textContent.trim();
      const description = link.getAttribute('data-explorer-description') || '';

      const titleTarget = titleTargetId ? document.getElementById(titleTargetId) : null;
      const descriptionTarget = descriptionTargetId ? document.getElementById(descriptionTargetId) : null;
      const tooltipTarget = tooltipTargetId ? document.getElementById(tooltipTargetId) : null;

      if (titleTarget) titleTarget.textContent = title;
      if (descriptionTarget) descriptionTarget.textContent = description;
      if (tooltipTarget) tooltipTarget.textContent = description;
    });
  });
}

initExplorerLabels();

async function exportPlotFromFrame(frame, filename) {
  try {
    const frameWindow = frame.contentWindow;
    const frameDoc = frame.contentDocument || (frameWindow && frameWindow.document);
    if (!frameDoc || !frameWindow) return false;

    const modebarBtn = frameDoc.querySelector(
      '.modebar-btn[data-title*="Download plot as"], .modebar-btn[aria-label*="Download"]'
    );
    if (modebarBtn) {
      modebarBtn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
      return true;
    }

    const plotRoot = frameDoc.querySelector('.js-plotly-plot');
    if (plotRoot && frameWindow.Plotly && typeof frameWindow.Plotly.downloadImage === 'function') {
      await frameWindow.Plotly.downloadImage(plotRoot, {
        format: 'png',
        filename,
      });
      return true;
    }
  } catch (_) {
    // Ignore export failures; the iframe content remains usable.
  }

  return false;
}

function waitForFrameLoad(frame) {
  return new Promise((resolve) => {
    frame.addEventListener('load', () => resolve(), { once: true });
  });
}

// Trigger Plotly's built-in PNG export inside same-origin analysis iframes.
function initIframePlotDownloads() {
  const currentButtons = document.querySelectorAll('.js-download-iframe-plot[data-frame-name]');
  const specificButtons = document.querySelectorAll('.js-download-specific-iframe-plot[data-frame-name][data-export-src]');
  if (!currentButtons.length && !specificButtons.length) return;

  currentButtons.forEach((button) => {
    button.addEventListener('click', async () => {
      const frameName = button.getAttribute('data-frame-name');
      if (!frameName) return;

      const frame = document.querySelector(`iframe[name="${frameName}"]`);
      if (!frame) return;

      const filename = button.getAttribute('data-filename') || 'plot';
      await exportPlotFromFrame(frame, filename);
    });
  });

  specificButtons.forEach((button) => {
    button.addEventListener('click', async () => {
      const frameName = button.getAttribute('data-frame-name');
      const exportSrc = button.getAttribute('data-export-src');
      if (!frameName || !exportSrc) return;

      const frame = document.querySelector(`iframe[name="${frameName}"]`);
      if (!frame) return;

      const filename = button.getAttribute('data-filename') || 'plot';
      const currentSrc = frame.getAttribute('src') || '';
      const currentAbs = currentSrc ? new URL(currentSrc, window.location.href).toString() : '';
      const exportAbs = new URL(exportSrc, window.location.href).toString();
      const needsNavigation = currentAbs !== exportAbs;

      try {
        if (needsNavigation) {
          const loadPromise = waitForFrameLoad(frame);
          frame.src = exportSrc;
          await loadPromise;
        }

        await exportPlotFromFrame(frame, filename);
      } finally {
        if (needsNavigation && currentSrc) {
          frame.src = currentSrc;
        }
      }
    });
  });
}

initIframePlotDownloads();

// Warning drill-down: summary + classification + filters
// Normalize warning text into structured metadata for summary and filtering.
function classifyWarning(text) {
  const t = (text || '').toLowerCase();
  const rowMatch = t.match(/row\s+(\d+)/i);
  const fieldMatch = t.match(/(variant_index|parent_variant_index|generation|assembled_dna_sequence|dna_yield|protein_yield|field\s+'?([a-z0-9_]+)'?)/i);

  let category = 'other';
  let severity = 'advisory';
  let fix = 'Review this record and re-upload.';
  let why = 'This warning may affect data quality and reproducibility.';

  if (t.includes('duplicate') && t.includes('variant')) {
    category = 'duplicate_variant_index';
    severity = 'critical';
    fix = 'Use unique variant_index values for each record.';
    why = 'Duplicate variant IDs can overwrite lineage relationships and bias downstream ranking.';
  } else if ((t.includes('missing') && t.includes('field')) || t.includes('no generation 0')) {
    category = 'missing_fields';
    severity = 'critical';
    fix = 'Add required fields/controls and re-upload.';
    why = 'Missing required values break parsing assumptions and can invalidate analysis.';
  } else if (t.includes('invalid') || t.includes('must be') || t.includes('not a')) {
    category = 'invalid_values';
    severity = 'critical';
    fix = 'Correct value type/format for this field.';
    why = 'Invalid formats prevent reliable metric calculation and comparability.';
  } else if (t.includes('orphan') || t.includes('parent_variant_index')) {
    category = 'lineage_reference';
    severity = 'critical';
    fix = 'Ensure parent_variant_index points to an existing parent variant.';
    why = 'Broken parent links corrupt lineage reconstruction and mutation tracking.';
  } else if (t.includes('warning')) {
    category = 'quality_warning';
    severity = 'advisory';
    fix = 'Check whether this warning is acceptable for your analysis.';
    why = 'Advisory issues can shift confidence in conclusions if left unreviewed.';
  }

  return {
    category,
    severity,
    row: rowMatch ? rowMatch[1] : '-',
    field: fieldMatch ? (fieldMatch[2] || fieldMatch[1]) : '-',
    issue: text || '',
    fix,
    why,
  };
}

// Build warning summary metrics and wire critical/all filter controls.
function initWarningInsights() {
  const rows = Array.from(document.querySelectorAll('.js-warning-row'));
  if (rows.length === 0) return;

  const counts = {
    critical: 0,
    advisory: 0,
    missing_fields: 0,
    invalid_values: 0,
    duplicate_variant_index: 0,
    other: 0,
  };
  const byField = {};

  rows.forEach((row) => {
    const warningText = row.getAttribute('data-warning-text') || '';
    const p = classifyWarning(warningText);
    row.dataset.severity = p.severity;
    row.dataset.category = p.category;

    const sevCell = row.querySelector('[data-col="severity"]');
    const rowCell = row.querySelector('[data-col="row"]');
    const fieldCell = row.querySelector('[data-col="field"]');
    const issueCell = row.querySelector('[data-col="issue"]');
    const whyCell = row.querySelector('[data-col="why"]');
    const fixCell = row.querySelector('[data-col="fix"]');
    const actionCell = row.querySelector('[data-col="action"]');
    if (sevCell) sevCell.textContent = p.severity;
    if (rowCell) rowCell.textContent = p.row;
    if (fieldCell) fieldCell.textContent = p.field;
    if (issueCell) issueCell.textContent = p.issue;
    if (whyCell) {
      whyCell.innerHTML = `<span class="warning-why" title="${p.why.replace(/"/g, '&quot;')}">ⓘ</span> ${p.why}`;
    }
    if (fixCell) fixCell.textContent = p.fix;
    if (actionCell) {
      const goBtn = actionCell.querySelector('.js-go-record');
      if (goBtn) {
        goBtn.disabled = true;
        goBtn.title = 'Record view is not available in this workspace.';
      }
    }

    counts[p.severity] += 1;
    const fieldKey = p.field && p.field !== '-' ? p.field : 'unclassified';
    if (!byField[fieldKey]) byField[fieldKey] = { total: 0, critical: 0, advisory: 0 };
    byField[fieldKey].total += 1;
    byField[fieldKey][p.severity] += 1;

    if (p.category === 'missing_fields') counts.missing_fields += 1;
    else if (p.category === 'invalid_values') counts.invalid_values += 1;
    else if (p.category === 'duplicate_variant_index') counts.duplicate_variant_index += 1;
    else counts.other += 1;
  });

  const summary = document.querySelector('[data-warning-summary]');
  if (summary) {
    summary.textContent = `${counts.advisory} advisory warnings (${counts.critical} critical)`;
  }

  const groupContainer = document.getElementById('warningGroups');
  const groupToggle = document.getElementById('warningGroupByField');
  const tableWrap = document.querySelector('.warning-insights__table-wrap');
  if (groupContainer) {
    const rowsHtml = Object.entries(byField)
      .sort((a, b) => b[1].total - a[1].total)
      .map(([field, c]) => (
        `<tr>
          <td>${field}</td>
          <td>${c.critical}</td>
          <td>${c.advisory}</td>
          <td>${c.total}</td>
        </tr>`
      ))
      .join('');
    groupContainer.innerHTML = `
      <table class="warning-insights__group-table">
        <thead><tr><th>Field</th><th>Critical</th><th>Advisory</th><th>Total</th></tr></thead>
        <tbody>${rowsHtml || '<tr><td colspan="4">No grouped warnings.</td></tr>'}</tbody>
      </table>
    `;
  }

  const filterButtons = Array.from(document.querySelectorAll('.js-warning-filter'));
  const applyFilter = (mode) => {
    rows.forEach((row) => {
      const critical = row.dataset.severity === 'critical';
      const advisory = row.dataset.severity === 'advisory';
      row.style.display = (
        mode === 'all' ||
        (mode === 'critical' && critical) ||
        (mode === 'advisory' && advisory)
      ) ? '' : 'none';
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

  if (groupToggle && groupContainer && tableWrap) {
    groupToggle.addEventListener('change', () => {
      const grouped = groupToggle.checked;
      groupContainer.classList.toggle('is-hidden', !grouped);
      tableWrap.classList.toggle('is-hidden', grouped);
    });
  }

  applyFilter(counts.critical > 0 ? 'critical' : 'advisory');
}

initWarningInsights();
