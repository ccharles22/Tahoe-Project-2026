/**
 * homepage.js
 * Homepage-only motion, stage-card interactions, and results carousel behavior.
 */

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
    const authDnaTracks = document.querySelectorAll("[data-auth-dna-track]");
    const homeNav = document.querySelector(".home-nav");
    const heroSection = document.querySelector(".home-hero");
    const resultsCarousel = document.querySelector("[data-home-results-carousel]");
    const resultsTrack = document.querySelector("[data-home-results-track]");
    const resultsCounter = document.querySelector("[data-home-results-counter]");
    const resultsPreview = document.querySelector(".home-results-preview");
    let activeStageId = "";
    const stageTitles = {
      "fetch-wt": "Fetch WT",
      "validate": "Validate Plasmid",
      "upload": "Upload Data",
      "analyse": "Run Analysis",
      "sequence": "Process Sequences",
    };

    function buildDnaTrack(track, { rowHeight, minRows, heightScale, widthFactor, widthOffset } = {}) {
      if (!track) return;

      const dnaRowHeight = window.innerWidth <= 640 ? rowHeight - 2 : rowHeight;
      const rowCount = Math.max(minRows, Math.ceil((window.innerHeight * heightScale) / dnaRowHeight));
      const baseCount = Math.max(96, Math.ceil(window.innerWidth / (10 / widthFactor)) + widthOffset);
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
      track.innerHTML = `${firstSet}${firstSet}`;
      if (reduceMotion) {
        track.style.transform = "rotate(0deg) scale(1.02)";
      }
    }

    function buildDnaBackground() {
      buildDnaTrack(dnaTrack, {
        rowHeight: 22,
        minRows: 24,
        heightScale: 1.9,
        widthFactor: 1,
        widthOffset: 44,
      });

      authDnaTracks.forEach((track) => {
        buildDnaTrack(track, {
          rowHeight: 20,
          minRows: 22,
          heightScale: 1.6,
          widthFactor: 0.88,
          widthOffset: 28,
        });
      });
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
      homeNav.classList.toggle("home-nav--compact", window.scrollY > 8);
    };

    window.addEventListener("scroll", updateNavContrast, { passive: true });
    window.addEventListener("resize", updateNavContrast);
    updateNavContrast();

    if (resultsCarousel && resultsTrack) {
      const sourceCards = Array.from(resultsTrack.querySelectorAll(".home-results-card"));
      const totalCards = sourceCards.length;
      if (totalCards > 0) {
        const firstClone = sourceCards[0].cloneNode(true);
        const lastClone = sourceCards[totalCards - 1].cloneNode(true);
        firstClone.classList.add("is-clone");
        lastClone.classList.add("is-clone");
        resultsTrack.insertBefore(lastClone, sourceCards[0]);
        resultsTrack.appendChild(firstClone);
      }

      const allCards = Array.from(resultsTrack.querySelectorAll(".home-results-card"));
      if (allCards.length >= 3) {

      let activePhysicalIndex = 1;
      let wheelLock = false;
      let rafId = 0;
      let isProgrammaticScroll = false;

      const toLogicalIndex = (physicalIdx) => {
        if (physicalIdx <= 0) return totalCards - 1;
        if (physicalIdx >= allCards.length - 1) return 0;
        return physicalIdx - 1;
      };

      const cardCenterTarget = (card) =>
        card.offsetLeft - ((resultsCarousel.clientWidth - card.offsetWidth) / 2);

      const closestPhysicalIndex = () => {
        const viewportCenter = resultsCarousel.scrollLeft + (resultsCarousel.clientWidth / 2);
        let bestIdx = 0;
        let bestDelta = Number.POSITIVE_INFINITY;
        allCards.forEach((card, idx) => {
          const cardCenter = card.offsetLeft + (card.offsetWidth / 2);
          const delta = Math.abs(cardCenter - viewportCenter);
          if (delta < bestDelta) {
            bestDelta = delta;
            bestIdx = idx;
          }
        });
        return bestIdx;
      };

      const updateCounter = (physicalIdx) => {
        if (!resultsCounter) return;
        const logicalIdx = toLogicalIndex(physicalIdx);
        const title = allCards[physicalIdx].dataset.resultTitle || "";
        resultsCounter.textContent = `${logicalIdx + 1} / ${totalCards} - ${title}`;
      };

      const updateCardStates = (physicalIdx) => {
        const logicalIdx = toLogicalIndex(physicalIdx);
        const prevLogical = (logicalIdx - 1 + totalCards) % totalCards;
        const nextLogical = (logicalIdx + 1) % totalCards;
        const isEdgeClone = physicalIdx === 0 || physicalIdx === allCards.length - 1;

        allCards.forEach((card, idx) => {
          const cardLogical = toLogicalIndex(idx);
          const isActive = idx === physicalIdx;
          const isSide = !isActive && !isEdgeClone && (cardLogical === prevLogical || cardLogical === nextLogical);
          card.classList.toggle("is-active", isActive);
          card.classList.toggle("is-side", isSide);
        });

        updateCounter(physicalIdx);
      };

      const jumpToPhysical = (physicalIdx) => {
        const card = allCards[physicalIdx];
        if (!card) return;
        isProgrammaticScroll = true;
        resultsCarousel.scrollTo({
          left: cardCenterTarget(card),
          behavior: "auto",
        });
        activePhysicalIndex = physicalIdx;
        updateCardStates(physicalIdx);
        requestAnimationFrame(() => {
          isProgrammaticScroll = false;
        });
      };

      const snapToPhysical = (physicalIdx, behavior = "smooth") => {
        const clamped = Math.max(0, Math.min(allCards.length - 1, physicalIdx));
        const card = allCards[clamped];
        if (!card) return;
        activePhysicalIndex = clamped;
        resultsCarousel.scrollTo({
          left: cardCenterTarget(card),
          behavior,
        });
        updateCardStates(clamped);
      };

      const handleLoopEdge = () => {
        if (activePhysicalIndex === 0) {
          jumpToPhysical(totalCards);
          return;
        }
        if (activePhysicalIndex === allCards.length - 1) {
          jumpToPhysical(1);
        }
      };

      resultsCarousel.addEventListener("wheel", (event) => {
        const absY = Math.abs(event.deltaY);
        const absX = Math.abs(event.deltaX);
        if (absY < 3 && absX < 3) return;
        event.preventDefault();
        if (wheelLock) return;
        wheelLock = true;

        const direction = (absX > absY ? event.deltaX : event.deltaY) > 0 ? 1 : -1;
        snapToPhysical(activePhysicalIndex + direction, reduceMotion ? "auto" : "smooth");

        window.setTimeout(() => {
          wheelLock = false;
        }, 170);
      }, { passive: false });

      resultsCarousel.addEventListener("scroll", () => {
        if (isProgrammaticScroll) return;
        if (rafId) cancelAnimationFrame(rafId);
        rafId = requestAnimationFrame(() => {
          rafId = 0;
          const nearestIdx = closestPhysicalIndex();
          if (nearestIdx !== activePhysicalIndex) {
            activePhysicalIndex = nearestIdx;
            updateCardStates(nearestIdx);
          }
          handleLoopEdge();
        });
      }, { passive: true });

      window.addEventListener("resize", () => {
        jumpToPhysical(activePhysicalIndex);
      });

        jumpToPhysical(1);
      }
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

  function initResultsPreviewResize() {
    const iframes = document.querySelectorAll('.home-results-embed');
    
    iframes.forEach((iframe) => {
      iframe.addEventListener('load', () => {
        try {
          const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
          const plotlyDiv = iframeDoc.querySelector('.plotly-graph-div, .js-plotly-plot');
          
          if (plotlyDiv && iframe.contentWindow.Plotly) {
            const resizePlot = () => {
              iframe.contentWindow.Plotly.Plots.resize(plotlyDiv);
            };
            
            resizePlot();
            window.addEventListener('resize', resizePlot);
            
            const container = iframeDoc.querySelector('.plot-container, .plotly');
            if (container) {
              container.style.width = '100%';
              container.style.height = '100%';
            }
          }
          
          iframeDoc.body.style.margin = '0';
          iframeDoc.body.style.padding = '0';
          iframeDoc.body.style.overflow = 'hidden';
          
          const html = iframeDoc.documentElement;
          if (html) {
            html.style.overflow = 'hidden';
          }
        } catch (e) {
          // Cross-origin restriction, cannot access iframe content
        }
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      initHomeMotion();
      initResultsPreviewResize();
    });
  } else {
    initHomeMotion();
    initResultsPreviewResize();
  }
})();
