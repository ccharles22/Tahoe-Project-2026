document.addEventListener("DOMContentLoaded", () => {
  const header = document.querySelector(".md-header");
  if (!header || document.querySelector(".app-guidebar")) {
    return;
  }

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const createRail = (side) => {
    const rail = document.createElement("div");
    rail.className = `app-guidebar-dna-rail app-guidebar-dna-rail--${side}`;
    rail.setAttribute("aria-hidden", "true");
    rail.innerHTML = `
      <div class="app-guidebar-dna-rail__dna-track" data-app-guidebar-dna-track="${side}"></div>
      <div class="app-guidebar-dna-rail__context-track" data-app-guidebar-context-track="${side}"></div>
    `;
    return rail;
  };

  const leftRail = createRail("left");
  const rightRail = createRail("right");
  document.body.prepend(rightRail);
  document.body.prepend(leftRail);

  const guideBar = document.createElement("div");
  guideBar.className = "app-guidebar";
  guideBar.innerHTML = `
    <div class="app-guidebar__inner md-grid">
      <a class="app-guidebar__brand" href="/auth/" aria-label="Return to homepage">
        <img
          src="/static/img/team_tahoe_logo_nav.png"
          alt="Direct Evolution Monitoring Portal"
          loading="eager"
          decoding="async"
        >
      </a>
      <nav class="app-guidebar__nav" aria-label="Application navigation">
        <a class="app-guidebar__link" href="/auth/">Home</a>
        <a class="app-guidebar__link" href="/staging/">Workspace</a>
        <a class="app-guidebar__link app-guidebar__link--active" href="/guide/" aria-current="page">User Guide</a>
      </nav>
    </div>
  `;

  header.before(guideBar);

  const buildDnaForTrack = (track) => {
    if (!track) return;

    const railWidth = track.parentElement ? track.parentElement.getBoundingClientRect().width : 120;
    const dnaRowHeight = 18;
    const rowCount = Math.max(20, Math.ceil((window.innerHeight * 1.35) / dnaRowHeight));
    const baseCount = Math.max(14, Math.ceil(railWidth / 8) + 10);
    const bases = ["A", "C", "G", "T"];

    const createRow = () => {
      let row = "";
      for (let idx = 0; idx < baseCount; idx += 1) {
        const base = bases[Math.floor(Math.random() * bases.length)];
        row += `<span class="app-guidebar-dna-rail__base--${base}">${base}</span>`;
      }
      return `<span class="app-guidebar-dna-rail__row">${row}</span>`;
    };

    let firstSet = "";
    for (let idx = 0; idx < rowCount; idx += 1) {
      firstSet += createRow();
    }

    track.innerHTML = `${firstSet}${firstSet}`;
    if (reduceMotion) {
      track.style.animation = "none";
      track.style.transform = "rotate(-3deg) scale(1.02)";
    }
  };

  const buildContextForTrack = (track, side) => {
    if (!track) return;

    const tocHeadings = Array.from(
      document.querySelectorAll(".md-sidebar--secondary .md-nav__link .md-ellipsis")
    )
      .map((node) => node.textContent.trim())
      .filter(Boolean)
      .slice(0, 8);

    const pageTitle =
      document.querySelector(".md-content h1")?.textContent.trim() ||
      document.title.replace(/\s*-\s*Direct Evolution Monitoring Portal\s*$/i, "").trim() ||
      "Documentation";

    const path = window.location.pathname;
    let contextTerms;

    if (path.includes("/postgresql_visualization/metrics/")) {
      contextTerms = [
        "raw measurements",
        "normalized ratios",
        "derived activity_score",
        "WT baselines",
        "generation-median fallback",
        "ranking and report outputs",
      ];
    } else if (path.includes("/activity_score_calculations/")) {
      contextTerms = [
        "dna_yield_norm",
        "protein_yield_norm",
        "activity_score",
        "WT normalization",
        "median normalization",
        "interpret > 1 as improved efficiency",
      ];
    } else if (path.includes("/metric_storage_and_types/")) {
      contextTerms = [
        "metrics table",
        "metric_definitions",
        "raw normalized derived",
        "upsert behavior",
        "ratio units",
      ];
    } else if (path.includes("/metric_qc_and_validation/")) {
      contextTerms = [
        "missing raw values",
        "invalid WT baseline",
        "fallback invalid rows",
        "validate activity_score coverage",
        "check top10 consistency",
      ];
    } else if (path.includes("/plots_")) {
      contextTerms = [
        "interpret the plot",
        "trace experiment trends",
        "compare outputs",
        "cross-check ranking and lineage",
      ];
    } else {
      contextTerms = [
        pageTitle,
        "documentation workflow",
        "read, interpret, verify",
      ];
    }

    const leftLines = [
      "Table of contents",
      ...tocHeadings.length ? tocHeadings : ["Overview", "Key sections", "How to use this page"],
    ];
    const rightLines = [
      pageTitle,
      ...contextTerms,
    ];

    const source = side === "left" ? leftLines : rightLines;
    const desiredCount = Math.max(14, Math.ceil(window.innerHeight / 70));
    const lines = [];
    for (let idx = 0; idx < desiredCount; idx += 1) {
      lines.push(source[idx % source.length]);
    }

    track.innerHTML = lines
      .map((line) => `<span class="app-guidebar-dna-rail__context-line">${line}</span>`)
      .join("");

    if (reduceMotion) {
      track.style.animation = "none";
      track.style.transform = side === "left" ? "translateY(0)" : "translateY(0)";
    }
  };

  const rebuildDnaRails = () => {
    document.querySelectorAll("[data-app-guidebar-dna-track]").forEach((track) => {
      buildDnaForTrack(track);
    });
    document.querySelectorAll("[data-app-guidebar-context-track]").forEach((track) => {
      const side = track.getAttribute("data-app-guidebar-context-track");
      buildContextForTrack(track, side);
    });
  };

  rebuildDnaRails();
  window.addEventListener("resize", rebuildDnaRails);
});
