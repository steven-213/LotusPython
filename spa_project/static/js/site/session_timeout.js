(() => {
  const configNode = document.getElementById("session-timeout-data");
  if (!configNode) {
    return;
  }

  const expiresAt = Number(configNode.dataset.expiresAt || 0);
  const redirectUrl = configNode.dataset.redirectUrl || "";
  if (!expiresAt || !redirectUrl) {
    return;
  }

  let timeoutId = null;

  const redirectIfExpired = () => {
    if (Date.now() >= expiresAt * 1000) {
      window.location.replace(redirectUrl);
    }
  };

  const scheduleRedirect = () => {
    if (timeoutId) {
      window.clearTimeout(timeoutId);
    }

    const remainingMs = (expiresAt * 1000) - Date.now();
    if (remainingMs <= 0) {
      redirectIfExpired();
      return;
    }

    timeoutId = window.setTimeout(redirectIfExpired, remainingMs + 200);
  };

  scheduleRedirect();

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
      redirectIfExpired();
      scheduleRedirect();
    }
  });

  window.addEventListener("pageshow", () => {
    redirectIfExpired();
    scheduleRedirect();
  });
})();
