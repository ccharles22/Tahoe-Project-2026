/**
 * homepage_auth.js
 * Controls the auth drawer shown from homepage sign-in and sign-up actions.
 */

(() => {
  const sheet = document.getElementById("auth-sheet");
  if (!sheet) return;

  const tabs = [...sheet.querySelectorAll("[data-auth-tab]")];
  const views = [...sheet.querySelectorAll("[data-auth-view]")];
  const openers = [...document.querySelectorAll("[data-auth-open]")];
  const closeButton = sheet.querySelector(".auth-sheet__close");
  const backdrop = sheet.querySelector(".auth-sheet__backdrop");
  const openAuth = (document.body.getAttribute("data-open-auth") || "").trim();

  // Detect page reloads (F5 / cmd-R) to avoid re-opening the sheet on refresh
  const navEntry = performance.getEntriesByType("navigation")[0];
  const isReload = (navEntry && navEntry.type === "reload") || (performance.navigation && performance.navigation.type === 1);

  /**
   * Switch the visible tab inside the auth sheet.
   * @param {string} name - Tab identifier ("register" or "login").
   */
  function setTab(name) {
    const target = name === "register" ? "register" : "login";
    tabs.forEach((btn) => {
      const active = btn.getAttribute("data-auth-tab") === target;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });
    views.forEach((view) => {
      view.classList.toggle("is-active", view.getAttribute("data-auth-view") === target);
    });
  }

  /**
   * Reveal the auth sheet with a specific tab selected.
   * @param {string} panel  - Tab to activate on open ("login" | "register").
   * @param {Object} [options]
   * @param {boolean} [options.instant] - Skip the opening animation.
   */
  function openSheet(panel, options = {}) {
    const instant = Boolean(options.instant);
    setTab(panel);
    sheet.classList.toggle("is-instant", instant);
    sheet.classList.add("is-open");
    sheet.setAttribute("aria-hidden", "false");
    document.body.classList.add("auth-sheet-open");
    if (instant) {
      requestAnimationFrame(() => sheet.classList.remove("is-instant"));
    }
  }

  /** Hide the auth sheet and restore body scroll. */
  function closeSheet() {
    sheet.classList.remove("is-open");
    sheet.setAttribute("aria-hidden", "true");
    document.body.classList.remove("auth-sheet-open");
  }

  openers.forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      if (sheet.classList.contains("is-open")) return;
      openSheet(link.getAttribute("data-auth-open"));
    });
  });

  tabs.forEach((btn) => {
    btn.addEventListener("click", (event) => {
      event.preventDefault();
      setTab(btn.getAttribute("data-auth-tab"));
    });
  });

  if (closeButton) closeButton.addEventListener("click", closeSheet);

  // Keep panel open unless user explicitly presses the X button.
  if (backdrop) {
    backdrop.addEventListener("click", (event) => {
      event.preventDefault();
    });
  }

  // Auto-open the sheet on first load when the server requests it via data attribute
  if (openAuth && !isReload) openSheet(openAuth, { instant: true });
})();
