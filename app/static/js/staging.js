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

  const isLocalHost = ['127.0.0.1', 'localhost'].includes(window.location.hostname);

  const readJsonPayload = async (response) => {
    const contentType = (response.headers.get('content-type') || '').toLowerCase();
    if (!contentType.includes('application/json')) {
      return null;
    }
    return response.json();
  };

  const navigateToUrl = (rawTarget) => {
    const targetUrl = new URL(rawTarget || window.location.href, window.location.href);
    targetUrl.searchParams.set('_refresh', String(Date.now()));
    window.location.assign(targetUrl.toString());
  };

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

function initTop10TableTools() {
  const table = document.querySelector('.js-top10-dashboard-table');
  if (!table) return;
  const tbody = table.querySelector('tbody');
  if (!tbody) return;

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

  const copyBtn = document.querySelector('.js-copy-top10-csv');
  if (!copyBtn) return;
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

function initAdvancedVisualTabs() {
  const buttons = Array.from(document.querySelectorAll('.js-advanced-tab-btn[data-src]'));
  const frame = document.getElementById('advancedTabsFrame');
  const title = document.getElementById('advancedTabsTitle');
  const description = document.getElementById('advancedTabsDescription');
  const downloads = document.getElementById('advancedTabsDownloads');
  if (!buttons.length || !frame || !title || !description || !downloads) return;

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

    title.textContent = nextTitle;
    description.textContent = nextDescription;
    frame.title = nextTitle;
    if (frame.getAttribute('src') !== src) {
      frame.setAttribute('src', src);
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
