document.addEventListener("DOMContentLoaded", () => {
  document.documentElement.classList.add("app-guidebar-transition-enabled");

  const header = document.querySelector(".md-header");
  if (!header || document.querySelector(".app-guidebar")) {
    return;
  }

  const guideIconMarkup = `
    <svg class="app-guidebar__docs-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M7 3.5h7.6L19 7.9V19a1.5 1.5 0 0 1-1.5 1.5h-10A1.5 1.5 0 0 1 6 19V5a1.5 1.5 0 0 1 1-1.4Z"></path>
      <path d="M14.5 3.5V8H19"></path>
      <path d="M9 11h6M9 14.5h6M9 18h4.5"></path>
    </svg>
  `;

  document.querySelectorAll(".md-logo").forEach((logo) => {
    logo.innerHTML = guideIconMarkup;
  });

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

  document.querySelectorAll(".md-tabs__link").forEach((link) => {
    link.addEventListener("click", (event) => {
      if (
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

      document.documentElement.classList.add("app-guidebar-page-leaving");
    });
  });

  window.requestAnimationFrame(() => {
    document.documentElement.classList.add("app-guidebar-page-ready");
  });
});
