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
  const navEntry = performance.getEntriesByType("navigation")[0];
  const isReload = (navEntry && navEntry.type === "reload") || (performance.navigation && performance.navigation.type === 1);

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

  if (openAuth && !isReload) openSheet(openAuth, { instant: true });
})();
