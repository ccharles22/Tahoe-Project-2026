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

/**
 * Restore the last active sidebar section from localStorage.
 * Falls back to 'tools' when no prior selection is stored.
 */
function initializeSidebar() {
  // Get saved section from localStorage, default to 'tools'
  const savedSection = localStorage.getItem('activeSidebarSection') || 'tools';
  
  // Find and click the corresponding taskbar item
  const taskbarItem = document.querySelector(`.taskbar__item[data-section="${savedSection}"]`);
  if (taskbarItem) {
    taskbarItem.click();
  }
}

// --- Taskbar navigation: toggle sidebar sections ---
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

/**
 * Wire the full-page loading overlay that appears while sequence-processing
 * or analysis runs execute on the server. Handles async polling for remote
 * deployments and auto-refreshes when the job completes.
 */
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

  /**
   * Display the loader overlay with mode-specific copy.
   * @param {'sequence'|'analysis'} mode
   */
  const showLoader = (mode) => {
    const content = copy[mode] || copy.analysis;
    if (titleEl) titleEl.textContent = content.title;
    if (textEl) textEl.textContent = content.text;
    loader.classList.add('is-visible');
    loader.setAttribute('aria-hidden', 'false');
    document.body.classList.add('is-run-loading');
  };

  /** Hide the loader overlay and restore interactivity. */
  const hideLoader = () => {
    loader.classList.remove('is-visible');
    loader.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('is-run-loading');
  };

  const isLocalHost = ['127.0.0.1', 'localhost'].includes(window.location.hostname);

  /**
   * Safely extract JSON from a fetch response; returns null for non-JSON.
   * @param {Response} response
   * @returns {Promise<Object|null>}
   */
  const readJsonPayload = async (response) => {
    const contentType = (response.headers.get('content-type') || '').toLowerCase();
    if (!contentType.includes('application/json')) {
      return null;
    }
    return response.json();
  };

  /** Redirect to a URL with a cache-busting query parameter. */
  const navigateToUrl = (rawTarget) => {
    const targetUrl = new URL(rawTarget || window.location.href, window.location.href);
    targetUrl.searchParams.set('_refresh', String(Date.now()));
    window.location.assign(targetUrl.toString());
  };

  /**
   * Poll the server for sequence-processing status and redirect when done.
   * @param {string} experimentId
   * @param {string} redirectUrl - Fallback URL if the server doesn't provide one.
   */
  const pollSequenceUntilDone = async (experimentId, redirectUrl) => {
    const pollUrl = `/staging/sequence/status?experiment_id=${encodeURIComponent(experimentId)}`;

    const poll = async () => {
      try {
        const response = await fetch(pollUrl, {
          credentials: 'same-origin',
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
          },
        });
        const payload = await readJsonPayload(response);
        if (!payload) {
          navigateToUrl(redirectUrl);
          return;
        }
        if (payload.state === 'running' || payload.state === 'started' || payload.state === 'idle') {
          window.setTimeout(poll, 3000);
          return;
        }
        navigateToUrl(payload.redirect_url || redirectUrl);
      } catch (error) {
        console.error('Sequence polling failed:', error);
        navigateToUrl(redirectUrl);
      }
    };

    window.setTimeout(poll, 3000);
  };

  document
    .querySelectorAll('form[action*="/sequence/run"], form[action*="/analysis/run"]')
    .forEach((form) => {
      form.addEventListener('submit', async (event) => {
        if (form.dataset.submitting === 'true') return;

        const mode = form.action.includes('/sequence/run') ? 'sequence' : 'analysis';
        const submitBtn = form.querySelector('.btn--submit');
        form.dataset.submitting = 'true';
        if (submitBtn) submitBtn.classList.add('is-loading');
        showLoader(mode);

        if (mode !== 'sequence' || isLocalHost) {
          return;
        }

        event.preventDefault();

        try {
          const formData = new FormData(form);
          const experimentId = String(formData.get('experiment_id') || '').trim();
          const response = await fetch(form.action, {
            method: form.method || 'POST',
            body: formData,
            credentials: 'same-origin',
            redirect: 'follow',
            headers: {
              'X-Requested-With': 'XMLHttpRequest',
            },
          });

          const payload = await readJsonPayload(response);
          if (!payload) {
            navigateToUrl(window.location.href);
            return;
          }

          if (payload.state === 'started' || payload.state === 'running') {
            pollSequenceUntilDone(experimentId, payload.redirect_url || window.location.href);
            return;
          }

          navigateToUrl(payload.redirect_url || window.location.href);
        } catch (error) {
          console.error('Sequence run request failed:', error);
          navigateToUrl(window.location.href);
        }
      });
    });
}

initRunLoader();

// --- Experiment card click-to-open and keyboard activation ---
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

/**
 * Synchronise explorer panel header and tooltip text when the user
 * switches between visualisation links.
 */
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

/**
 * Attempt to trigger a Plotly PNG export inside a same-origin iframe.
 * Falls back gracefully if the iframe is cross-origin or lacks Plotly.
 * @param {HTMLIFrameElement} frame    - Target iframe element.
 * @param {string}            filename - Suggested download filename.
 * @returns {Promise<boolean>} Whether the export was triggered successfully.
 */
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

/**
 * Return a promise that resolves once the iframe fires its 'load' event.
 * @param {HTMLIFrameElement} frame
 * @returns {Promise<void>}
 */
function waitForFrameLoad(frame) {
  return new Promise((resolve) => {
    frame.addEventListener('load', () => resolve(), { once: true });
  });
}

/**
 * Wire download buttons that export the currently visible (or a specific)
 * Plotly chart from an analysis iframe as a PNG image.
 */
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

/**
 * Parse free-text warning messages into structured metadata.
 * Maps common patterns (duplicates, missing fields, invalid values, orphan links)
 * to a category, severity level, and suggested fix.
 * @param {string} text - Raw warning string from the server.
 * @returns {{category: string, severity: string, row: string, field: string, issue: string, fix: string, why: string}}
 */
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

/**
 * Populate the warning insights panel: classify each row, build summary
 * counts, group-by-field table, and wire severity filter buttons.
 */
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

/**
 * Toggle the sidebar between expanded and collapsed rail view.
 * Persists state to localStorage so it survives page navigations.
 */
function initSidebarCollapseToggle() {
  const toggleBtn = document.getElementById('sidebarRailToggle');
  const body = document.body;
  if (!toggleBtn || !body || !body.classList.contains('staging-page')) return;

  const key = 'stagingSidebarCollapsed';
  const setState = (collapsed) => {
    body.classList.toggle('sidebar-collapsed', collapsed);
    toggleBtn.setAttribute('aria-pressed', collapsed ? 'true' : 'false');
    toggleBtn.setAttribute('aria-label', collapsed ? 'Show sidebar' : 'Hide sidebar');
    toggleBtn.innerHTML = collapsed ? '&#x25B6;' : '&#x25C0;';
  };

  setState(localStorage.getItem(key) === 'true');

  toggleBtn.addEventListener('click', () => {
    const next = !body.classList.contains('sidebar-collapsed');
    setState(next);
    localStorage.setItem(key, next ? 'true' : 'false');
  });
}

/**
 * Initialise the Top-10 variant dashboard table: column sorting,
 * detail modal (with copy/download/jump actions), and CSV export.
 */
function initTop10TableTools() {
  const table = document.querySelector('.js-top10-dashboard-table');
  if (!table) return;
  const tbody = table.querySelector('tbody');
  if (!tbody) return;

  /**
   * Extract a sortable value from a table row's data attributes.
   * @param {HTMLElement} row  - <tr> with data-* attributes.
   * @param {string}      key  - Dataset key to read.
   * @param {string}      type - 'number' or 'string'.
   * @returns {number|string}
   */
  const parseCellValue = (row, key, type) => {
    const raw = row.dataset[key] || '';
    if (type === 'number') {
      const value = Number(raw);
      return Number.isFinite(value) ? value : Number.NEGATIVE_INFINITY;
    }
    return raw.toLowerCase();
  };

  const clearSortState = () => {
    table.querySelectorAll('.js-top10-sort').forEach((btn) => {
      btn.classList.remove('is-sorted');
      btn.dataset.sortOrder = '';
      btn.setAttribute('aria-sort', 'none');
    });
  };

  table.querySelectorAll('.js-top10-sort').forEach((btn) => {
    btn.addEventListener('click', () => {
      const key = btn.getAttribute('data-sort-key');
      const type = btn.getAttribute('data-sort-type') || 'string';
      if (!key) return;

      const nextOrder = btn.dataset.sortOrder === 'asc' ? 'desc' : 'asc';
      const rows = Array.from(tbody.querySelectorAll('tr'));
      rows.sort((a, b) => {
        const av = parseCellValue(a, key, type);
        const bv = parseCellValue(b, key, type);
        if (av === bv) return 0;
        if (nextOrder === 'asc') return av > bv ? 1 : -1;
        return av < bv ? 1 : -1;
      });
      rows.forEach((row) => tbody.appendChild(row));

      clearSortState();
      btn.classList.add('is-sorted');
      btn.dataset.sortOrder = nextOrder;
      btn.setAttribute('aria-sort', nextOrder === 'asc' ? 'ascending' : 'descending');
    });
  });

  const modal = document.getElementById('top10VariantModal');
  const modalCard = modal ? modal.querySelector('.variant-modal__card') : null;
  const modalCloseButtons = modal ? Array.from(modal.querySelectorAll('.js-top10-modal-close')) : [];
  const summaryCopyBtn = modal ? modal.querySelector('.js-top10-copy-summary') : null;
  const rowDownloadBtn = modal ? modal.querySelector('.js-top10-download-row') : null;
  const mutationDownloadBtn = modal ? modal.querySelector('.js-top10-download-mutations') : null;
  const jumpButtons = modal ? Array.from(modal.querySelectorAll('.js-top10-jump')) : [];
  const listCopyButtons = modal ? Array.from(modal.querySelectorAll('.js-top10-copy-list')) : [];
  const detailField = (key) => (modal ? modal.querySelector(`[data-top10-detail="${key}"]`) : null);
  const chipField = (key) => (modal ? modal.querySelector(`[data-top10-chip="${key}"]`) : null);
  const listField = (key) => (modal ? modal.querySelector(`[data-top10-list="${key}"]`) : null);
  let lastFocusedRow = null;
  let activeModalState = null;

  const asNumber = (raw) => {
    const value = Number(raw);
    return Number.isFinite(value) ? value : null;
  };

  /** Return the highest activity_score in the current table body. */
  const maxTop10Score = () => {
    const values = Array.from(tbody.querySelectorAll('tr'))
      .map((row) => asNumber(row.dataset.activity_score))
      .filter((value) => value !== null);
    return values.length ? Math.max(...values) : null;
  };

  /** Classify mutation count into a human-readable divergence band. */
  const mutationBandLabel = (count) => {
    if (count === null) return 'Unknown';
    if (count === 0) return 'WT-like';
    if (count <= 2) return 'Low drift';
    if (count <= 5) return 'Moderate divergence';
    return 'High divergence';
  };

  const escapeCsvValue = (value) => `"${String(value ?? '').replace(/"/g, '""')}"`;

  const parseDelimitedList = (raw) => {
    if (!raw) return [];
    return raw
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);
  };

  /** Parse a mutation change token (e.g. "A42G") into position, WT→Mut, and type. */
  const parseChangeToken = (token) => {
    const match = token.match(/^([A-Za-z*])(\d+)([A-Za-z*])$/);
    if (!match) {
      return { position: '-', wtMut: token, type: 'unknown' };
    }
    const wt = match[1];
    const pos = match[2];
    const mut = match[3];
    return {
      position: pos,
      wtMut: `${wt}->${mut}`,
      type: wt === mut ? 'synonymous' : 'non-synonymous',
    };
  };

  /** Derive an overall mutation type label from synonym/non-synonym counts. */
  const mutationTypeFromCounts = (total, syn, nonSyn) => {
    if (total === null) return 'Unknown';
    if (total === 0) return 'No mutation detected';
    if (syn !== null && nonSyn !== null) {
      if (syn > 0 && nonSyn > 0) return 'Mixed (synonymous + non-synonymous)';
      if (nonSyn > 0) return 'Non-synonymous';
      if (syn > 0) return 'Synonymous-only';
    }
    return 'Mutated (type split unavailable)';
  };

  /** Classify a variant's score ratio relative to the top performer. */
  const performanceBandLabel = (ratio) => {
    if (ratio === null) return 'Unavailable';
    if (ratio >= 0.97) return 'Top-tier';
    if (ratio >= 0.9) return 'Strong';
    if (ratio >= 0.8) return 'Competitive';
    return 'Lower within Top 10';
  };

  const setDetail = (key, value) => {
    const target = detailField(key);
    if (target) target.textContent = value;
  };

  const setChip = (key, value) => {
    const target = chipField(key);
    if (target) target.textContent = value;
  };

  /**
   * Render a list of items with a "show more" toggle when exceeding 8 entries.
   * @param {string}   key        - data-top10-list key for the host element.
   * @param {string[]} items      - Values to display.
   * @param {string}   emptyLabel - Fallback text when items is empty.
   * @param {boolean}  [asChips]  - Render as chip tokens instead of comma-separated.
   */
  const setExpandableList = (key, items, emptyLabel, asChips = false) => {
    const host = listField(key);
    if (!host) return;
    host.innerHTML = '';
    if (!items.length) {
      host.textContent = emptyLabel;
      return;
    }

    const visibleCount = 8;
    const shown = items.slice(0, visibleCount);
    const hidden = items.slice(visibleCount);

    const visibleWrap = document.createElement('div');
    if (asChips) visibleWrap.className = 'variant-modal__chips-list';
    shown.forEach((item, index) => {
      if (asChips) {
        const chip = document.createElement('span');
        chip.className = 'variant-modal__token';
        chip.textContent = item;
        visibleWrap.appendChild(chip);
      } else {
        visibleWrap.appendChild(document.createTextNode(item));
        if (index < shown.length - 1) visibleWrap.appendChild(document.createTextNode(', '));
      }
    });
    host.appendChild(visibleWrap);

    if (!hidden.length) return;

    const hiddenWrap = document.createElement('div');
    hiddenWrap.className = asChips ? 'variant-modal__chips-list variant-modal__hidden' : 'variant-modal__hidden';
    hidden.forEach((item, index) => {
      if (asChips) {
        const chip = document.createElement('span');
        chip.className = 'variant-modal__token';
        chip.textContent = item;
        hiddenWrap.appendChild(chip);
      } else {
        hiddenWrap.appendChild(document.createTextNode(item));
        if (index < hidden.length - 1) hiddenWrap.appendChild(document.createTextNode(', '));
      }
    });
    host.appendChild(hiddenWrap);

    const moreBtn = document.createElement('button');
    moreBtn.type = 'button';
    moreBtn.className = 'variant-modal__more';
    moreBtn.textContent = `+${hidden.length} more`;
    moreBtn.addEventListener('click', () => {
      const collapsed = hiddenWrap.classList.contains('variant-modal__hidden');
      hiddenWrap.classList.toggle('variant-modal__hidden', !collapsed);
      moreBtn.textContent = collapsed ? 'Show less' : `+${hidden.length} more`;
    });
    host.appendChild(moreBtn);
  };

  /** Populate the feature-table body with parsed mutation change tokens. */
  const renderFeatureTable = (changes, generation) => {
    const tbodyTarget = detailField('feature_table_body');
    if (!tbodyTarget) return;
    tbodyTarget.innerHTML = '';
    if (!changes.length) {
      tbodyTarget.innerHTML = '<tr><td colspan="5">No mutation features available.</td></tr>';
      return;
    }
    changes.forEach((token) => {
      const parsed = parseChangeToken(token);
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${parsed.position}</td><td>${parsed.wtMut}</td><td>${parsed.type}</td><td>${generation || '-'}</td><td>-</td>`;
      tbodyTarget.appendChild(tr);
    });
  };

  const switchCoreTab = (targetId) => {
    const btn = document.querySelector(`.js-core-tab-btn[data-tab-target="${targetId}"]`);
    if (!btn) return false;
    btn.click();
    const section = document.getElementById('results-core');
    if (section) section.scrollIntoView({ behavior: 'smooth', block: 'start' });
    return true;
  };

  const switchAdvancedTabByKeyword = (keyword) => {
    const btn = Array.from(document.querySelectorAll('.js-advanced-tab-btn[data-title]')).find((node) =>
      (node.getAttribute('data-title') || '').toLowerCase().includes(keyword)
    );
    if (!btn) return false;
    btn.click();
    const section = document.getElementById('results-advanced');
    if (section) section.scrollIntoView({ behavior: 'smooth', block: 'start' });
    return true;
  };

  const setJumpAvailability = () => {
    jumpButtons.forEach((btn) => {
      const target = btn.getAttribute('data-jump-target') || '';
      let available = false;
      if (target === 'lineage') available = Boolean(document.querySelector('.js-core-tab-btn[data-tab-target="core-lineage"]'));
      if (target === 'hotspots') available = Boolean(Array.from(document.querySelectorAll('.js-advanced-tab-btn[data-title]')).find((n) => (n.getAttribute('data-title') || '').toLowerCase().includes('hotspot')));
      if (target === 'fingerprint') available = Boolean(Array.from(document.querySelectorAll('.js-advanced-tab-btn[data-title]')).find((n) => (n.getAttribute('data-title') || '').toLowerCase().includes('fingerprint')));
      btn.disabled = !available;
      btn.title = available ? '' : 'Visualisation not available for this run.';
    });
  };

  /**
   * Collect variant metadata from a table row's data attributes,
   * populate the modal fields, and show it.
   * @param {HTMLElement} row - The <tr> element clicked by the user.
   */
  const openModalForRow = (row) => {
    if (!modal || !modalCard) return;

    const rank = row.dataset.rank || 'N/A';
    const generationNumber = asNumber(row.dataset.generation);
    const generation = generationNumber !== null ? `G${generationNumber}` : 'N/A';
    const variant = row.dataset.variant_index || 'N/A';
    const variantId = row.dataset.variant_id || 'N/A';
    const scoreText = row.dataset.activity_score_text || 'N/A';
    const scoreValue = asNumber(row.dataset.activity_score);
    const mutationCount = asNumber(row.dataset.total_mutations);
    const synCount = asNumber(row.dataset.synMutations);
    const nonSynCount = asNumber(row.dataset.nonSynMutations);
    const mutationTypeRaw = (row.dataset.mutationType || '').trim();
    const mutationSource = (row.dataset.mutationSource || '').trim() || 'Unknown';
    const mutationSitesRaw = (row.dataset.mutationSites || '').trim();
    const mutationChangesRaw = (row.dataset.mutationChanges || '').trim();
    const mutationSites = mutationSitesRaw && !/unknown|not available/i.test(mutationSitesRaw)
      ? parseDelimitedList(mutationSitesRaw)
      : [];
    const mutationChanges = mutationChangesRaw && !/unknown|not available/i.test(mutationChangesRaw)
      ? parseDelimitedList(mutationChangesRaw)
      : [];
    const identity = asNumber(row.dataset.seqIdentity);
    const coverage = asNumber(row.dataset.seqCoverage);
    const qcFlagged = row.dataset.qc_flagged === 'true';
    const qcNote = (row.dataset.qc_note || '').trim();

    const bestScore = maxTop10Score();
    const ratio = scoreValue !== null && bestScore !== null && bestScore > 0 ? (scoreValue / bestScore) : null;
    const relative = ratio !== null
      ? `${(ratio * 100).toFixed(1)}% of best (${performanceBandLabel(ratio)})`
      : 'N/A';
    const mutationLoad = mutationCount !== null ? `${Math.round(mutationCount)} vs WT` : 'N/A';
    const mutationType = mutationTypeRaw || mutationTypeFromCounts(mutationCount, synCount, nonSynCount);
    const mutationSplit = (synCount !== null && nonSynCount !== null)
      ? `Synonymous: ${Math.round(synCount)}, Non-synonymous: ${Math.round(nonSynCount)}`
      : 'Not available';
    const mutationBand = mutationBandLabel(mutationCount);
    const qcStatus = qcFlagged
      ? `Flagged${qcNote && qcNote.toLowerCase() !== 'ok' ? `: ${qcNote}` : ''}`
      : (qcNote ? `Pass (${qcNote})` : 'Pass');
    const qcReasons = qcFlagged ? (qcNote || 'qc_stage4 flag present') : 'None';
    const dataCoverage = coverage !== null ? `${coverage.toFixed(1)}%` : 'Not available';
    const identityPct = identity !== null ? `${identity.toFixed(1)}%` : 'Not available';

    setChip('generation', generation);
    setChip('rank', `Rank #${rank}`);
    setChip('activity', `Activity ${scoreText}`);
    setChip('mutations', mutationLoad);
    setChip('qc', `QC: ${qcFlagged ? 'Flagged' : 'Pass'}`);
    setChip('tier', `Tier: ${mutationBand}`);

    setDetail('entry_subtitle', `Variant ${variant} (${generation}) - ID ${variantId}`);
    setDetail('variant', variant);
    setDetail('variant_id', variantId);
    setDetail('rank', rank);
    setDetail('generation', generation);
    setDetail('activity_score', scoreText);
    setDetail('relative_score', relative);
    setDetail('mutation_load', mutationLoad);
    setDetail('mutation_type', mutationType);
    setDetail('mutation_split', mutationSplit);
    setDetail('mutation_band', mutationBand);
    setDetail('qc_status', qcStatus);
    setDetail('qc_status_repeat', qcStatus);
    setDetail('qc_reasons', qcReasons);
    setDetail('mutation_source', mutationSource);
    setDetail('data_coverage', dataCoverage);
    setDetail('identity_pct', identityPct);

    setExpandableList('sites', mutationSites, mutationSitesRaw || 'None', false);
    setExpandableList('changes', mutationChanges, mutationChangesRaw || 'None', true);
    renderFeatureTable(mutationChanges, generation);

    activeModalState = {
      rank,
      generation,
      variant,
      variantId,
      scoreText,
      mutationLoad,
      mutationType,
      mutationSplit,
      mutationBand,
      qcStatus,
      qcReasons,
      mutationSource,
      dataCoverage,
      identityPct,
      mutationSites,
      mutationChanges,
      relative,
    };

    lastFocusedRow = row;
    setJumpAvailability();
    modal.hidden = false;
    modal.classList.add('is-open');
    modalCard.focus();
  };

  const closeModal = () => {
    if (!modal) return;
    modal.classList.remove('is-open');
    modal.hidden = true;
    if (lastFocusedRow && typeof lastFocusedRow.focus === 'function') {
      lastFocusedRow.focus();
    }
    activeModalState = null;
  };

  Array.from(tbody.querySelectorAll('tr.js-top10-row')).forEach((row) => {
    row.addEventListener('click', () => openModalForRow(row));
    row.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      openModalForRow(row);
    });
  });

  modalCloseButtons.forEach((btn) => {
    btn.addEventListener('click', () => closeModal());
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && modal && !modal.hidden) {
      closeModal();
    }
  });

  listCopyButtons.forEach((btn) => {
    btn.addEventListener('click', async () => {
      if (!activeModalState) return;
      const kind = btn.getAttribute('data-copy-list');
      const values = kind === 'sites' ? activeModalState.mutationSites : activeModalState.mutationChanges;
      const payload = values.length ? values.join(', ') : 'None';
      let copied = false;
      try {
        await navigator.clipboard.writeText(payload);
        copied = true;
      } catch (_) {
        copied = false;
      }
      const original = btn.textContent;
      btn.textContent = copied ? 'Copied' : 'Copy failed';
      window.setTimeout(() => {
        btn.textContent = original;
      }, 1200);
    });
  });

  if (summaryCopyBtn) {
    summaryCopyBtn.addEventListener('click', async () => {
      if (!activeModalState) return;
      const lines = [
        `Variant: ${activeModalState.variant}`,
        `Variant ID: ${activeModalState.variantId}`,
        `Generation: ${activeModalState.generation}`,
        `Rank: ${activeModalState.rank}`,
        `Activity score: ${activeModalState.scoreText}`,
        `Relative to top performer: ${activeModalState.relative}`,
        `Mutations vs WT: ${activeModalState.mutationLoad}`,
        `Synonymous / Non-synonymous: ${activeModalState.mutationSplit}`,
        `Divergence tier: ${activeModalState.mutationBand}`,
        `QC status: ${activeModalState.qcStatus}`,
      ].join('\n');
      let copied = false;
      try {
        await navigator.clipboard.writeText(lines);
        copied = true;
      } catch (_) {
        copied = false;
      }
      const original = summaryCopyBtn.textContent;
      summaryCopyBtn.textContent = copied ? 'Copied' : 'Copy failed';
      window.setTimeout(() => {
        summaryCopyBtn.textContent = original;
      }, 1200);
    });
  }

  /** Trigger a file download from an in-memory CSV string. */
  const downloadBlob = (filename, textValue) => {
    const blob = new Blob([textValue], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(link.href);
  };

  if (rowDownloadBtn) {
    rowDownloadBtn.addEventListener('click', () => {
      if (!activeModalState) return;
      const headers = ['variant', 'variant_id', 'generation', 'rank', 'activity_score', 'mutations_vs_wt', 'mutation_type', 'syn_non_syn_split', 'qc_status'];
      const values = [
        activeModalState.variant,
        activeModalState.variantId,
        activeModalState.generation,
        activeModalState.rank,
        activeModalState.scoreText,
        activeModalState.mutationLoad,
        activeModalState.mutationType,
        activeModalState.mutationSplit,
        activeModalState.qcStatus,
      ];
      const csv = `${headers.join(',')}\n${values.map(escapeCsvValue).join(',')}\n`;
      downloadBlob(`variant_${activeModalState.variant || 'entry'}.csv`, csv);
    });
  }

  if (mutationDownloadBtn) {
    mutationDownloadBtn.addEventListener('click', () => {
      if (!activeModalState) return;
      const rows = activeModalState.mutationChanges.map((token) => {
        const parsed = parseChangeToken(token);
        return [parsed.position, parsed.wtMut, parsed.type, activeModalState.generation, ''].map(escapeCsvValue).join(',');
      });
      const header = ['position', 'wt_to_mut', 'type', 'introduced_generation', 'notes'].join(',');
      const csv = `${header}\n${rows.join('\n')}\n`;
      downloadBlob(`variant_${activeModalState.variant || 'entry'}_mutations.csv`, csv);
    });
  }

  jumpButtons.forEach((btn) => {
    btn.addEventListener('click', () => {
      const target = btn.getAttribute('data-jump-target') || '';
      let moved = false;
      if (target === 'lineage') moved = switchCoreTab('core-lineage');
      if (target === 'hotspots') moved = switchAdvancedTabByKeyword('hotspot');
      if (target === 'fingerprint') moved = switchAdvancedTabByKeyword('fingerprint');
      if (moved) closeModal();
    });
  });

  const copyBtn = document.querySelector('.js-copy-top10-csv');
  if (copyBtn) {
    copyBtn.addEventListener('click', async () => {
      const headers = Array.from(table.querySelectorAll('thead th')).map((th) => {
        const btn = th.querySelector('button');
        return (btn ? btn.textContent : th.textContent || '').trim();
      });
      const rows = Array.from(tbody.querySelectorAll('tr')).map((row) =>
        Array.from(row.querySelectorAll('td')).map((td) => `"${(td.textContent || '').trim().replace(/"/g, '""')}"`).join(',')
      );
      const csvText = [headers.join(','), ...rows].join('\n');
      let copied = false;
      try {
        await navigator.clipboard.writeText(csvText);
        copied = true;
      } catch (_) {
        copied = false;
      }

      copyBtn.textContent = copied ? 'Copied' : 'Copy failed';
      window.setTimeout(() => {
        copyBtn.textContent = 'Copy as CSV';
      }, 1400);
    });
  }
}

/**
 * Initialise the core results tab bar (Top-10 / Lineage / etc.).
 * Clicking a tab button shows its associated panel.
 */
function initCoreResultsTabs() {
  const buttons = Array.from(document.querySelectorAll('.js-core-tab-btn[data-tab-target]'));
  const panels = Array.from(document.querySelectorAll('.js-core-tab-panel[id]'));
  if (!buttons.length || !panels.length) return;

  const setActive = (targetId) => {
    buttons.forEach((btn) => {
      const active = btn.getAttribute('data-tab-target') === targetId;
      btn.classList.toggle('is-active', active);
    });
    panels.forEach((panel) => {
      panel.classList.toggle('is-active', panel.id === targetId);
    });
  };

  buttons.forEach((btn) => {
    btn.addEventListener('click', () => {
      const targetId = btn.getAttribute('data-tab-target') || '';
      if (targetId) setActive(targetId);
    });
  });

  const initial = buttons.find((btn) => btn.classList.contains('is-active'));
  setActive(initial ? (initial.getAttribute('data-tab-target') || 'core-top10') : 'core-top10');
}

/**
 * Initialise the advanced visualisation tab bar.
 * Each tab loads its HTML source into a shared iframe and updates
 * the title, description, and download links.
 */
function initAdvancedVisualTabs() {
  const buttons = Array.from(document.querySelectorAll('.js-advanced-tab-btn[data-src]'));
  const frame = document.getElementById('advancedTabsFrame');
  const title = document.getElementById('advancedTabsTitle');
  const description = document.getElementById('advancedTabsDescription');
  const downloads = document.getElementById('advancedTabsDownloads');
  if (!buttons.length || !frame || !title || !description || !downloads) return;

  const applyLandscapeFrameTweaks = () => {
    try {
      const frameWindow = frame.contentWindow;
      const frameDoc = frame.contentDocument || (frameWindow && frameWindow.document);
      if (!frameWindow || !frameDoc) return;

      const modebar = frameDoc.querySelector('.modebar');
      if (modebar) {
        modebar.style.left = '10px';
        modebar.style.right = 'auto';
        modebar.style.top = '8px';
      }

      const plotRoot = frameDoc.querySelector('.js-plotly-plot');
      if (!plotRoot || !frameWindow.Plotly || typeof frameWindow.Plotly.relayout !== 'function') return;

      frameWindow.Plotly.relayout(plotRoot, {
        'updatemenus[0].direction': 'down',
        'updatemenus[0].x': 0.02,
        'updatemenus[0].xanchor': 'left',
        'updatemenus[0].y': 1.0,
        'updatemenus[0].yanchor': 'top',
        'updatemenus[0].bgcolor': 'rgba(255,255,255,0.88)',
        'updatemenus[0].bordercolor': 'rgba(148,163,184,0.7)',
        'updatemenus[0].pad.r': 4,
        'updatemenus[0].pad.t': 4,
      });
    } catch (_) {
      // Ignore cross-document or relayout errors; viewer still works.
    }
  };

  const renderDownloads = (src, png) => {
    downloads.innerHTML = '';
    const openLink = document.createElement('a');
    openLink.className = 'btn btn--sm btn--ghost';
    openLink.href = src;
    openLink.target = '_blank';
    openLink.rel = 'noopener';
    openLink.textContent = 'Open in new tab';
    downloads.appendChild(openLink);

    if (png) {
      const pngLink = document.createElement('a');
      pngLink.className = 'btn btn--sm btn--ghost';
      pngLink.href = png;
      pngLink.target = '_blank';
      pngLink.rel = 'noopener';
      pngLink.textContent = 'Download PNG';
      downloads.appendChild(pngLink);
    }
  };

  const setActive = (btn) => {
    const src = btn.getAttribute('data-src') || '';
    if (!src) return;

    buttons.forEach((item) => item.classList.toggle('is-active', item === btn));
    const nextTitle = btn.getAttribute('data-title') || 'Advanced visualisation';
    const nextDescription = btn.getAttribute('data-description') || '';
    const nextPng = btn.getAttribute('data-png') || '';
    const nextFrameSize = btn.getAttribute('data-frame-size') || '';
    const isLandscape = src.toLowerCase().includes('activity_landscape');

    title.textContent = nextTitle;
    description.textContent = nextDescription;
    frame.title = nextTitle;
    frame.classList.toggle('is-tall', nextFrameSize === 'tall');
    if (frame.getAttribute('src') !== src) {
      if (isLandscape) {
        frame.addEventListener('load', applyLandscapeFrameTweaks, { once: true });
      }
      frame.setAttribute('src', src);
    } else if (isLandscape) {
      applyLandscapeFrameTweaks();
    }
    renderDownloads(src, nextPng);
  };

  buttons.forEach((btn) => {
    btn.addEventListener('click', () => setActive(btn));
  });

  const initial = buttons.find((btn) => btn.classList.contains('is-active')) || buttons[0];
  if (initial) setActive(initial);
}

initTop10TableTools();
initCoreResultsTabs();
initAdvancedVisualTabs();
initSidebarCollapseToggle();
