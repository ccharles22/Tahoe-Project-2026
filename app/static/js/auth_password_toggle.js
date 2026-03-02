/**
 * auth_password_toggle.js
 * Shared password reveal toggles for auth forms on non-settings pages.
 */

(function () {
  "use strict";

  document.querySelectorAll(".btn-reveal").forEach((btn) => {
    const targetId = btn.getAttribute("data-target");
    const input = targetId ? document.getElementById(targetId) : null;
    if (!input) return;

    btn.addEventListener("click", () => {
      const hidden = input.type === "password";
      input.type = hidden ? "text" : "password";
      btn.setAttribute("aria-label", hidden ? "Hide password" : "Show password");

      const svg = btn.querySelector("svg");
      const path = btn.querySelector("path");
      if (!svg || !path) return;

      const existingCircle = btn.querySelector("circle");
      const existingStrike = btn.querySelector("line[data-strike='1']");

      if (hidden) {
        // Visible state: switch to the "eye-off" style.
        path.setAttribute(
          "d",
          "M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"
        );
        if (existingCircle) existingCircle.remove();
        if (!existingStrike) {
          const strike = document.createElementNS("http://www.w3.org/2000/svg", "line");
          strike.setAttribute("x1", "1");
          strike.setAttribute("y1", "1");
          strike.setAttribute("x2", "23");
          strike.setAttribute("y2", "23");
          strike.setAttribute("data-strike", "1");
          svg.appendChild(strike);
        }
      } else {
        // Hidden state: restore standard eye icon.
        path.setAttribute("d", "M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z");
        if (existingStrike) existingStrike.remove();
        if (!btn.querySelector("circle")) {
          const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
          circle.setAttribute("cx", "12");
          circle.setAttribute("cy", "12");
          circle.setAttribute("r", "3");
          svg.appendChild(circle);
        }
      }
    });
  });
})();
