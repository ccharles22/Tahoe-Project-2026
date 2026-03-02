document.addEventListener("DOMContentLoaded", () => {
  document.documentElement.classList.add("app-guidebar-transition-enabled");
  let isLeaving = false;

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
        <a class="app-guidebar__link app-guidebar__link--active" href="/guide/" aria-current="page">User guide</a>
      </nav>
    </div>
  `;

  header.before(guideBar);

  const buildDocsStrip = () => {
    const tabs = document.querySelector(".md-tabs");
    const nativeList = tabs ? tabs.querySelector(".md-tabs__list") : null;
    if (!tabs || !nativeList) {
      return [];
    }

    const nativeLinks = Array.from(nativeList.querySelectorAll(".md-tabs__item > .md-tabs__link"));
    if (!nativeLinks.length) {
      return [];
    }

    tabs.classList.add("app-guidebar-native-tabs-hidden");

    const strip = document.createElement("div");
    strip.className = "app-docs-tabs md-grid";
    strip.setAttribute("role", "navigation");
    strip.setAttribute("aria-label", "Documentation sections");
    strip.innerHTML = nativeLinks
      .map((link) => {
        const label = link.textContent.trim();
        const isActive =
          link.closest(".md-tabs__item")?.classList.contains("md-tabs__item--active") ||
          link.classList.contains("md-tabs__link--active");
        return `
          <a
            class="app-docs-tabs__link${isActive ? " app-docs-tabs__link--active" : ""}"
            href="${link.href}"
            ${isActive ? 'aria-current="page"' : ""}
          >${label}</a>
        `;
      })
      .join("");

    tabs.prepend(strip);
    return Array.from(strip.querySelectorAll(".app-docs-tabs__link"));
  };

  const docsStripLinks = buildDocsStrip();

  const buildDnaForTrack = (track) => {
    if (!track) return;

    const railWidth = track.parentElement ? track.parentElement.getBoundingClientRect().width : 120;
    const dnaRowHeight = 20;
    const rowCount = Math.max(16, Math.ceil((window.innerHeight * 1.12) / dnaRowHeight));
    const baseCount = Math.max(12, Math.ceil(railWidth / 10) + 8);
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

  let resizeFrame = null;
  const scheduleRebuild = () => {
    if (resizeFrame !== null) {
      window.cancelAnimationFrame(resizeFrame);
    }
    resizeFrame = window.requestAnimationFrame(() => {
      resizeFrame = null;
      rebuildDnaRails();
    });
  };

  rebuildDnaRails();
  window.addEventListener("resize", scheduleRebuild, { passive: true });

  const transitionLinks = docsStripLinks.length
    ? docsStripLinks
    : Array.from(document.querySelectorAll(".md-tabs__link"));

  transitionLinks.forEach((link) => {
    link.addEventListener("click", (event) => {
      if (
        isLeaving ||
        event.defaultPrevented ||
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey
      ) {
        return;
      }

      const href = link.getAttribute("href");
      if (!href || href.startsWith("#") || link.target === "_blank") {
        return;
      }

      const nextUrl = new URL(link.href, window.location.href);
      if (nextUrl.origin !== window.location.origin || nextUrl.href === window.location.href) {
        return;
      }

      event.preventDefault();
      isLeaving = true;
      document.documentElement.classList.add("app-guidebar-page-leaving");
      window.setTimeout(() => {
        window.location.href = nextUrl.href;
      }, 180);
    });
  });

  window.requestAnimationFrame(() => {
    document.documentElement.classList.add("app-guidebar-page-ready");
  });
});
