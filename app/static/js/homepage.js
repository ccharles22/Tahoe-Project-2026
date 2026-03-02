(() => {
  function initHomeMotion() {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const hasGSAP = Boolean(window.gsap);
    const gsap = window.gsap;
    const heroCopy = document.querySelector(".home-hero__copy");
    const heroBits = document.querySelectorAll(
      ".home-hero__eyebrow, .home-hero__title, .home-hero__sub, .home-hero__actions .btn"
    );
    const stagePanel = document.querySelector(".home-stage");
    const stageCards = document.querySelectorAll(".home-stage__card");
    const stageCardsList = Array.from(stageCards);
    const pipelineItems = document.querySelectorAll(".home-pipeline__item");
    const stageVisual = document.querySelector("[data-home-stage-visual]");
    const stageVisualTitle = document.querySelector("[data-home-stage-visual-title]");
    const dnaTrack = document.querySelector("[data-home-dna-track]");
    const homeNav = document.querySelector(".home-nav");
    const heroSection = document.querySelector(".home-hero");
    const resultsTrack = document.querySelector("[data-home-carousel-track]");
    const resultsDots = document.querySelector("[data-home-carousel-dots]");
    const resultsPreview = document.querySelector(".home-results-preview");
    let activeStageId = "";
    const stageTitles = {
      "fetch-wt": "Fetch WT",
      "validate": "Validate Plasmid",
      "upload": "Upload Data",
      "analyse": "Run Analysis",
      "sequence": "Process Sequences",
    };

    function buildDnaBackground() {
      if (!dnaTrack) return;

      const dnaRowHeight = window.innerWidth <= 640 ? 19 : 22;
      const rowCount = Math.max(24, Math.ceil((window.innerHeight * 1.9) / dnaRowHeight));
      const baseCount = Math.max(132, Math.ceil(window.innerWidth / 10) + 44);
      const bases = ["A", "C", "G", "T"];

      const createRow = () => {
        let row = "";
        for (let idx = 0; idx < baseCount; idx += 1) {
          const base = bases[Math.floor(Math.random() * bases.length)];
          row += `<span class="home-hero__dna-base--${base}">${base}</span>`;
        }
        return `<span class="home-hero__dna-row">${row}</span>`;
      };

      let firstSet = "";
      for (let idx = 0; idx < rowCount; idx += 1) {
        firstSet += createRow();
      }
      dnaTrack.innerHTML = `${firstSet}${firstSet}`;
      if (reduceMotion) {
        dnaTrack.style.transform = "rotate(0deg) scale(1.02)";
      }
    }

    function setActiveStage(stageId) {
      if (!stageId) return;
      if (stageId === activeStageId) return;
      activeStageId = stageId;
      stageCards.forEach((card) => card.classList.toggle("is-active", card.dataset.stage === stageId));
      pipelineItems.forEach((it) => it.classList.remove("is-active"));
      const matchingItem = document.querySelector(`.home-pipeline__item[data-stage="${stageId}"]`);
      if (matchingItem) matchingItem.classList.add("is-active");
      if (stageVisual) {
        stageVisual.dataset.stage = stageId;
      }
      if (stageVisualTitle && stageTitles[stageId]) {
        stageVisualTitle.textContent = stageTitles[stageId];
      }
    }

    pipelineItems.forEach((item) => {
      const activateItem = () => {
        const stageId = item.dataset.stage;
        const card = document.querySelector(`.home-stage__card[data-stage="${stageId}"]`);
        if (!card) return;
        card.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "center" });
        setActiveStage(stageId);
      };

      item.addEventListener("click", activateItem);
      item.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        activateItem();
      });
    });

    stageCards.forEach((card) => {
      card.addEventListener("click", (event) => {
        if (event.target.closest("a, button")) return;
        const stageId = card.dataset.stage;
        if (!stageId) return;
        setActiveStage(stageId);
      });
    });

    if (stageCards.length) {
      setActiveStage(stageCards[0].dataset.stage);
    }

    buildDnaBackground();
    window.addEventListener("resize", buildDnaBackground);

    const updateNavContrast = () => {
      if (!homeNav || !heroSection) return;
      const navBottom = homeNav.getBoundingClientRect().bottom;
      const heroBottom = heroSection.getBoundingClientRect().bottom;
      const onDark = navBottom <= heroBottom;
      homeNav.classList.toggle("home-nav--on-dark", onDark);
    };

    window.addEventListener("scroll", updateNavContrast, { passive: true });
    window.addEventListener("resize", updateNavContrast);
    updateNavContrast();

    if (resultsTrack) {
      const resultsCards = Array.from(resultsTrack.querySelectorAll(".home-results-card"));
      const dotElements = [];
      let wheelLock = false;
      let snapRaf = 0;

      const closestCardIndex = () => {
        if (!resultsCards.length) return 0;
        const left = resultsTrack.scrollLeft;
        let bestIdx = 0;
        let bestDelta = Infinity;
        resultsCards.forEach((card, idx) => {
          const delta = Math.abs(card.offsetLeft - left);
          if (delta < bestDelta) {
            bestDelta = delta;
            bestIdx = idx;
          }
        });
        return bestIdx;
      };

      const snapToCard = (idx) => {
        if (!resultsCards.length) return;
        const clamped = Math.max(0, Math.min(resultsCards.length - 1, idx));
        resultsTrack.scrollTo({
          left: resultsCards[clamped].offsetLeft,
          behavior: "auto",
        });
        updateActiveDot(clamped);
      };

      const updateActiveDot = (activeIdx) => {
        if (!dotElements.length) return;
        dotElements.forEach((dot, idx) => {
          dot.classList.toggle("is-active", idx === activeIdx);
        });
      };

      if (resultsDots && resultsCards.length > 1) {
        resultsCards.forEach((_, idx) => {
          const dot = document.createElement("span");
          dot.className = "home-results-dot";
          dotElements.push(dot);
          resultsDots.appendChild(dot);
          if (idx === 0) dot.classList.add("is-active");
        });
      }

      resultsTrack.addEventListener("wheel", (event) => {
        const absY = Math.abs(event.deltaY);
        const absX = Math.abs(event.deltaX);
        if (absY < 4 && absX < 4) return;
        event.preventDefault();
        if (wheelLock) return;
        wheelLock = true;

        const currentIdx = closestCardIndex();
        const direction = (absX > absY ? event.deltaX : event.deltaY) > 0 ? 1 : -1;
        snapToCard(currentIdx + direction);

        window.setTimeout(() => {
          wheelLock = false;
        }, 120);
      }, { passive: false });

      let isPointerDown = false;
      let dragStartX = 0;
      let dragStartScroll = 0;

      resultsTrack.addEventListener("pointerdown", (event) => {
        isPointerDown = true;
        dragStartX = event.clientX;
        dragStartScroll = resultsTrack.scrollLeft;
        resultsTrack.classList.add("is-dragging");
        resultsTrack.setPointerCapture(event.pointerId);
      });

      resultsTrack.addEventListener("pointermove", (event) => {
        if (!isPointerDown) return;
        const delta = event.clientX - dragStartX;
        resultsTrack.scrollLeft = dragStartScroll - delta;
      });

      const endDrag = (event) => {
        if (!isPointerDown) return;
        isPointerDown = false;
        resultsTrack.classList.remove("is-dragging");
        if (event && event.pointerId != null && resultsTrack.hasPointerCapture(event.pointerId)) {
          resultsTrack.releasePointerCapture(event.pointerId);
        }
      };

      resultsTrack.addEventListener("pointerup", endDrag);
      resultsTrack.addEventListener("pointercancel", endDrag);
      resultsTrack.addEventListener("pointerleave", endDrag);

      resultsTrack.addEventListener("scroll", () => {
        if (!dotElements.length) return;
        if (snapRaf) cancelAnimationFrame(snapRaf);
        snapRaf = requestAnimationFrame(() => {
          snapRaf = 0;
          updateActiveDot(closestCardIndex());
        });
      }, { passive: true });

      window.addEventListener("resize", () => {
        snapToCard(closestCardIndex());
      });
    }

    if (stageCards.length) {
      let rafScheduled = false;
      const syncActiveStageFromScroll = () => {
        if (rafScheduled) return;
        rafScheduled = true;
        window.requestAnimationFrame(() => {
          rafScheduled = false;
          const targetY = window.innerHeight * 0.52;
          let closestCard = null;
          let closestDistance = Infinity;

          stageCardsList.forEach((card) => {
            const rect = card.getBoundingClientRect();
            const centerY = rect.top + rect.height / 2;
            const distance = Math.abs(centerY - targetY);
            if (distance < closestDistance) {
              closestDistance = distance;
              closestCard = card;
            }
          });

          if (closestCard && closestCard.dataset.stage) {
            setActiveStage(closestCard.dataset.stage);
          }

          if (resultsPreview && activeStageId !== "analyse") {
            const lockBoundary = Math.max(0, resultsPreview.offsetTop - 1);
            if (window.scrollY > lockBoundary) {
              window.scrollTo(0, lockBoundary);
            }
          }
        });
      };

      window.addEventListener("scroll", syncActiveStageFromScroll, { passive: true });
      window.addEventListener("resize", syncActiveStageFromScroll);
      syncActiveStageFromScroll();
    }

    if (reduceMotion || !hasGSAP) return;

    const tl = gsap.timeline({ defaults: { ease: "power2.out" } });

    tl.from(".home-nav", { y: -12, autoAlpha: 0, duration: 0.45, clearProps: "all" });

    if (heroCopy && heroBits.length) {
      tl.from(
        heroBits,
        {
          y: 18,
          autoAlpha: 0,
          duration: 0.55,
          stagger: 0.08,
          clearProps: "all",
        },
        "-=0.18"
      );
    }

    if (stagePanel) {
      tl.from(
        stagePanel,
        {
          y: 24,
          autoAlpha: 0,
          duration: 0.52,
          clearProps: "all",
        },
        "-=0.25"
      );
    }

    if (stageCards.length) {
      tl.from(
        stageCards,
        {
          y: 12,
          autoAlpha: 0,
          duration: 0.36,
          stagger: 0.04,
          clearProps: "all",
        },
        "<"
      );
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initHomeMotion);
  } else {
    initHomeMotion();
  }
})();
