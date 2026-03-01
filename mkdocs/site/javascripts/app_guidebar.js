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

  const docsTabsGrid = document.querySelector(".md-tabs .md-grid");
  if (docsTabsGrid && !docsTabsGrid.querySelector(".app-docs-switcher")) {
    const sections = [
      { label: "Home Guide", href: "/docs/" },
      { label: "Parsing & QC", href: "/docs/parsing_qc/" },
      { label: "Database & Schema", href: "/docs/postgresql_visualization/database/" },
      { label: "Metric Computations", href: "/docs/postgresql_visualization/metrics/" },
      { label: "Visualisation Guide", href: "/docs/postgresql_visualization/" },
      { label: "Bonus Visualisations", href: "/docs/bonus_visualisations/" },
      { label: "Ownership Notes", href: "/docs/parsing_qc/OWNERS/" },
    ];

    const currentPath = window.location.pathname;
    let currentHref = sections[0].href;
    for (const section of sections) {
      if (currentPath.startsWith(section.href) && section.href.length >= currentHref.length) {
        currentHref = section.href;
      }
    }

    const switcher = document.createElement("div");
    switcher.className = "app-docs-switcher";

    const label = document.createElement("label");
    label.className = "app-docs-switcher__label";
    label.setAttribute("for", "app-docs-switcher-select");
    label.textContent = "Go to";

    const select = document.createElement("select");
    select.id = "app-docs-switcher-select";
    select.className = "app-docs-switcher__select";
    select.setAttribute("aria-label", "Switch documentation section");

    for (const section of sections) {
      const option = document.createElement("option");
      option.value = section.href;
      option.textContent = section.label;
      if (section.href === currentHref) {
        option.selected = true;
      }
      select.append(option);
    }

    select.addEventListener("change", () => {
      if (select.value) {
        window.location.href = select.value;
      }
    });

    switcher.append(label, select);
    docsTabsGrid.append(switcher);
  }

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

  const rebuildDnaRails = () => {
    document.querySelectorAll("[data-app-guidebar-dna-track]").forEach((track) => {
      buildDnaForTrack(track);
    });
  };

  rebuildDnaRails();
  window.addEventListener("resize", rebuildDnaRails);
});
