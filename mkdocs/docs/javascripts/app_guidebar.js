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
        <a class="app-guidebar__link app-guidebar__link--active" href="/guide/" aria-current="page">User guide</a>
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

  const rebuildDnaRails = () => {
    document.querySelectorAll("[data-app-guidebar-dna-track]").forEach((track) => {
      buildDnaForTrack(track);
    });
  };

  rebuildDnaRails();
  window.addEventListener("resize", rebuildDnaRails);
});
