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
  }

  document.addEventListener("DOMContentLoaded", initLazyEmbeds);
})();
