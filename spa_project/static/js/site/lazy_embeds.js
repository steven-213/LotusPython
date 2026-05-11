(function () {
  function loadEmbed(container) {
    if (!container || container.dataset.embedLoaded === "1") {
      return;
    }

    const iframe = container.querySelector("iframe[data-src]");
    if (!iframe) {
      return;
    }

    iframe.src = iframe.dataset.src;
    container.dataset.embedLoaded = "1";
    container.classList.add("is-loaded");
  }

  function initLazyEmbeds() {
    const containers = Array.from(document.querySelectorAll("[data-lazy-embed]"));
    if (!containers.length) {
      return;
    }

    containers.forEach(function (container) {
      const trigger = container.querySelector("[data-load-embed]");
      if (trigger) {
        trigger.addEventListener("click", function () {
          loadEmbed(container);
        });
      }
    });

    if (!("IntersectionObserver" in window)) {
      return;
    }

    const observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) {
            return;
          }

          loadEmbed(entry.target);
          observer.unobserve(entry.target);
        });
      },
      {
        rootMargin: "180px 0px",
      }
    );

    containers.forEach(function (container) {
      observer.observe(container);
    });
  }

  document.addEventListener("DOMContentLoaded", initLazyEmbeds);
})();
