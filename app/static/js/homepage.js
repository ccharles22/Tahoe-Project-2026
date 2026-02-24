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
    const pipelineItems = document.querySelectorAll(".home-pipeline__item");

    function setActiveStage(stageId) {
      if (!stageId) return;
      stageCards.forEach((card) => card.classList.toggle("is-active", card.dataset.stage === stageId));
      pipelineItems.forEach((it) => it.classList.remove("is-active"));
      const matchingItem = document.querySelector(`.home-pipeline__item[data-stage="${stageId}"]`);
      if (matchingItem) matchingItem.classList.add("is-active");
    }

    pipelineItems.forEach((item) => {
      item.addEventListener("click", () => {
        const stageId = item.dataset.stage;
        const card = document.querySelector(`.home-stage__card[data-stage="${stageId}"]`);
        if (!card) return;
        card.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
        setActiveStage(stageId);
      });
    });

    if (stageCards.length) {
      setActiveStage(stageCards[0].dataset.stage);
    }

    if (stageCards.length && "IntersectionObserver" in window) {
      const observer = new IntersectionObserver(
        (entries) => {
          const visible = entries
            .filter((entry) => entry.isIntersecting)
            .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
          if (visible.length) {
            setActiveStage(visible[0].target.dataset.stage);
          }
        },
        {
          root: null,
          rootMargin: "-55% 0px -10% 0px",
          threshold: [0.2, 0.4, 0.6],
        }
      );
      stageCards.forEach((card) => observer.observe(card));
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
        "-=0.32"
      );
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initHomeMotion);
  } else {
    initHomeMotion();
  }
})();
