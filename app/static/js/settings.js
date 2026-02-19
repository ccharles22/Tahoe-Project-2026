/**
 * settings.js  —  Direct Evolution Monitoring
 * Vanilla ES6+. No auth logic, no secrets. Progressive enhancement only.
 * All server-side validation is the source of truth; this file improves UX.
 */

(function () {
  "use strict";

  /* ── Helpers ────────────────────────────────────────────────────────── */
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  /** Announce a message to screen readers via the live region. */
  function announce(msg) {
    const el = $("#status-announcer");
    if (!el) return;
    el.textContent = "";
    // Force a DOM reflow so the change is detected even for repeat messages
    requestAnimationFrame(() => (el.textContent = msg));
  }

  /* ── 1. Reveal / hide password toggle ──────────────────────────────── */
  $$(".btn-reveal").forEach((btn) => {
    const targetId = btn.dataset.target;
    const input = targetId ? document.getElementById(targetId) : null;
    if (!input) return;

    btn.addEventListener("click", () => {
      const isHidden = input.type === "password";
      input.type = isHidden ? "text" : "password";
      btn.setAttribute(
        "aria-label",
        isHidden ? "Hide password" : "Show password"
      );
      // Swap eye icon path to a "crossed" version when visible
      const path = btn.querySelector("path");
      if (path) {
        if (isHidden) {
          // "eye-off" icon paths
          path.setAttribute(
            "d",
            "M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"
          );
          const line = btn.querySelector("line, circle");
          if (!line) {
            // Add the strike-through line dynamically
            const strike = document.createElementNS(
              "http://www.w3.org/2000/svg",
              "line"
            );
            strike.setAttribute("x1", "1");
            strike.setAttribute("y1", "1");
            strike.setAttribute("x2", "23");
            strike.setAttribute("y2", "23");
            btn.querySelector("svg").appendChild(strike);
          }
        } else {
          // Restore original "eye" icon
          path.setAttribute(
            "d",
            "M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"
          );
          const strike = btn.querySelector("line");
          if (strike) strike.remove();
        }
      }
    });
  });

  /* ── 2. Password strength meter ─────────────────────────────────────── */
  const newPwInput = document.getElementById("new_password");
  const strengthEl = document.getElementById("pw-strength");

  if (newPwInput && strengthEl) {
    const fill = $(".pw-strength__fill", strengthEl);
    const label = $(".pw-strength__label", strengthEl);

    const levels = [
      { label: "Weak",    color: "#dc2626" },
      { label: "Fair",    color: "#f59e0b" },
      { label: "Good",    color: "#3b82f6" },
      { label: "Strong",  color: "#10b981" },
    ];

    function scorePassword(pw) {
      if (!pw) return 0;
      let score = 0;
      if (pw.length >= 8)  score++;
      if (pw.length >= 12) score++;
      if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) score++;
      if (/\d/.test(pw))   score++;
      if (/[^A-Za-z0-9]/.test(pw)) score++;
      return Math.min(4, Math.floor(score * 0.85)); // cap at 4, scale slightly
    }

    newPwInput.addEventListener("input", () => {
      const pw = newPwInput.value;
      if (!pw) {
        strengthEl.hidden = true;
        fill.removeAttribute("data-level");
        label.textContent = "";
        return;
      }
      strengthEl.hidden = false;
      const score = scorePassword(pw); // 0-4
      const lvlIdx = Math.max(0, score - 1); // map 1-4 → 0-3
      fill.setAttribute("data-level", score);
      label.textContent = score === 0 ? "Too short" : levels[lvlIdx].label;
      // Announce when level changes for screen readers
      announce(score === 0 ? "Password is too short" : `Password strength: ${levels[lvlIdx].label}`);
    });
  }

  /* ── 3. Inline client-side validation ───────────────────────────────── */
  /**
   * Shows an error under a field without replacing server-rendered errors.
   * Only runs on blur to avoid premature red-state while typing.
   */
  function setFieldError(input, errorContainerId, message) {
    const errEl = document.getElementById(errorContainerId);
    if (!errEl) return;

    if (message) {
      input.setAttribute("aria-invalid", "true");
      // If the error container is a <span> (empty live region), upgrade to visible
      if (errEl.tagName === "SPAN") {
        errEl.textContent = message;
      }
    } else {
      input.setAttribute("aria-invalid", "false");
      if (errEl.tagName === "SPAN") errEl.textContent = "";
    }
  }

  // Email format check
  const emailInput = document.getElementById("email");
  if (emailInput) {
    emailInput.addEventListener("blur", () => {
      const val = emailInput.value.trim();
      if (val && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val)) {
        setFieldError(emailInput, "err-email", "Please enter a valid email address.");
      } else {
        setFieldError(emailInput, "err-email", "");
      }
    });
  }

  // Username: no spaces, 3-32 chars
  const usernameInput = document.getElementById("username");
  if (usernameInput) {
    usernameInput.addEventListener("blur", () => {
      const val = usernameInput.value.trim();
      if (val.length < 3) {
        setFieldError(usernameInput, "err-username", "Username must be at least 3 characters.");
      } else if (val.length > 32) {
        setFieldError(usernameInput, "err-username", "Username must be 32 characters or fewer.");
      } else if (/\s/.test(val)) {
        setFieldError(usernameInput, "err-username", "Username cannot contain spaces.");
      } else {
        setFieldError(usernameInput, "err-username", "");
      }
    });
  }

  /* ── 4. Password-change guardrail ───────────────────────────────────── */
  /**
   * If user types in new_password but leaves current_password blank,
   * show an inline warning (server will also reject, but this saves a round-trip).
   */
  const currentPwInput = document.getElementById("current_password");

  if (newPwInput && currentPwInput) {
    function checkPasswordPair() {
      if (newPwInput.value && !currentPwInput.value) {
        setFieldError(
          currentPwInput,
          "err-current-pw",
          "You must enter your current password to set a new one."
        );
      } else {
        setFieldError(currentPwInput, "err-current-pw", "");
      }
    }

    newPwInput.addEventListener("blur", checkPasswordPair);
    currentPwInput.addEventListener("input", () => {
      // Clear error as soon as they start typing
      if (currentPwInput.value) {
        setFieldError(currentPwInput, "err-current-pw", "");
      }
    });
  }

  /* ── 5. Submit guard: prevent double-submit, indicate loading ─────── */
  const form = document.getElementById("settings-form");
  const submitBtn = document.getElementById("submit-btn");

  if (form && submitBtn) {
    form.addEventListener("submit", (e) => {
      // Re-run critical checks before submit
      if (newPwInput && currentPwInput) {
        if (newPwInput.value && !currentPwInput.value) {
          e.preventDefault();
          currentPwInput.focus();
          announce("Please enter your current password before saving.");
          return;
        }
      }

      // Disable button + show loading state
      submitBtn.setAttribute("aria-busy", "true");
      submitBtn.textContent = "Saving…";
      submitBtn.disabled = true;
    });
  }

  /* ── 6. Focus management after server-side success ─────────────────── */
  /**
   * If a success flash is present (server redirected back), move focus to it
   * so screen reader users are immediately informed of the outcome.
   */
  const flashRegion = document.getElementById("flash-region");
  if (flashRegion && flashRegion.querySelector(".flash--success")) {
    // Brief delay to let the page fully render
    setTimeout(() => {
      flashRegion.setAttribute("tabindex", "-1");
      flashRegion.focus();
    }, 100);
    announce("Settings saved successfully.");
  }

})();
