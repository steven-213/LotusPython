(function () {
  function normalizeMoney(value) {
    if (value === null || value === undefined) {
      return "";
    }

    let text = String(value)
      .replace(/\$/g, "")
      .replace(/COP/gi, "")
      .replace(/\s+/g, "")
      .trim();

    if (!text) {
      return "";
    }

    let negative = false;
    if (text.startsWith("-")) {
      negative = true;
      text = text.slice(1);
    }

    if (text.includes(".") && text.includes(",")) {
      if (text.lastIndexOf(",") > text.lastIndexOf(".")) {
        text = text.replace(/\./g, "").replace(",", ".");
      } else {
        text = text.replace(/,/g, "");
      }
    } else if (text.includes(",")) {
      const parts = text.split(",");
      if (parts.length === 2 && parts[1].length > 0 && parts[1].length <= 2) {
        text = parts[0].replace(/\./g, "") + "." + parts[1];
      } else {
        text = text.replace(/,/g, "");
      }
    } else if (text.includes(".")) {
      const parts = text.split(".");
      if (!(parts.length === 2 && parts[1].length > 0 && parts[1].length <= 2)) {
        text = text.replace(/\./g, "");
      }
    }

    const numeric = Number(text);
    if (Number.isNaN(numeric)) {
      return "";
    }

    return (negative ? "-" : "") + String(numeric);
  }

  function formatMoney(value, withSymbol) {
    const normalized = normalizeMoney(value);
    if (!normalized) {
      return withSymbol ? "$ 0" : "";
    }

    const numeric = Number(normalized);
    if (Number.isNaN(numeric)) {
      return withSymbol ? "$ 0" : "";
    }

    const hasDecimals = Math.abs(numeric % 1) > 0;
    const formatted = new Intl.NumberFormat("es-CO", {
      minimumFractionDigits: hasDecimals ? 2 : 0,
      maximumFractionDigits: hasDecimals ? 2 : 0,
    }).format(numeric);

    return withSymbol ? "$ " + formatted : formatted;
  }

  function attachMoneyInput(input) {
    if (!input || input.dataset.moneyBound === "1") {
      return;
    }

    input.dataset.moneyBound = "1";

    input.addEventListener("input", function () {
      let cleaned = input.value.replace(/[^\d.,-]/g, "");
      if (cleaned.includes("-")) {
        cleaned = (cleaned.startsWith("-") ? "-" : "") + cleaned.replace(/-/g, "");
      }
      input.value = cleaned;
    });

    input.addEventListener("focus", function () {
      const normalized = normalizeMoney(input.value);
      if (normalized) {
        input.value = normalized;
      }
    });

    input.addEventListener("blur", function () {
      if (input.value.trim()) {
        input.value = formatMoney(input.value, false);
      }
    });

    if (input.value && input.value.trim()) {
      input.value = formatMoney(input.value, false);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-money='cop']").forEach(attachMoneyInput);
  });

  window.CopMoney = {
    formatDisplay: function (value) {
      return formatMoney(value, true);
    },
    formatInput: function (value) {
      return formatMoney(value, false);
    },
    normalize: normalizeMoney,
    bind: attachMoneyInput,
  };
})();
