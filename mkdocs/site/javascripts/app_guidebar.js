document.addEventListener("DOMContentLoaded", () => {
  const container = document.querySelector(".md-container");
  if (!container || container.querySelector(".app-guidebar")) {
    return;
  }

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

  container.prepend(guideBar);
});
