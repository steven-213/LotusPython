document.addEventListener("DOMContentLoaded", function () {
  function formatMoney(value) {
    if (window.CopMoney && typeof window.CopMoney.formatDisplay === "function") {
      return window.CopMoney.formatDisplay(value || 0);
    }
    const amount = Number(value || 0);
    return "$ " + amount.toLocaleString("es-CO", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function setAmountValue(input, amount) {
    if (!input) {
      return;
    }
    const numericAmount = Number(amount || 0);
    if (input.type === "number") {
      input.value = numericAmount.toFixed(2);
      return;
    }
    if (window.CopMoney && typeof window.CopMoney.formatInput === "function") {
      input.value = window.CopMoney.formatInput(numericAmount);
      return;
    }
    input.value = numericAmount.toFixed(0);
  }

  document.querySelectorAll("[data-product-cart]").forEach(function (cart) {
    const form = cart.closest("form");
    const picker = cart.querySelector("[data-product-picker]");
    const quantityInput = cart.querySelector("[data-product-quantity]");
    const addButton = cart.querySelector("[data-add-product]");
    const list = cart.querySelector("[data-product-list]");
    const emptyState = cart.querySelector("[data-product-empty]");
    const hiddenInputs = cart.querySelector("[data-product-hidden-inputs]");
    const productTotalLabel = cart.querySelector("[data-product-total-label]");
    const invoiceTotalLabel = cart.querySelector("[data-invoice-total-label]");
    const selectedProductNameLabel = cart.querySelector("[data-product-name-label]");
    const selectedProductPriceLabel = cart.querySelector("[data-product-price-label]");
    const selectedProductStockLabel = cart.querySelector("[data-product-stock-label]");
    const amountInput = form ? form.querySelector("input[name='monto']") : null;
    const serviceBalance = Number(cart.dataset.serviceBalance || 0);
    const items = [];

    function currentProductTotal() {
      return items.reduce(function (total, item) {
        return total + item.price * item.quantity;
      }, 0);
    }

    function updateSuggestedAmount() {
      const suggestedAmount = serviceBalance + currentProductTotal();
      if (form) {
        form.dataset.currentSuggestedAmount = String(suggestedAmount);
      }
      if (amountInput) {
        amountInput.removeAttribute("max");
      }
      if (!amountInput || amountInput.dataset.userEdited === "1") {
        return;
      }
      setAmountValue(amountInput, suggestedAmount);
    }

    function updateSelectedProductSummary() {
      const option = picker ? picker.options[picker.selectedIndex] : null;
      if (!option || !option.value) {
        if (selectedProductNameLabel) {
          selectedProductNameLabel.textContent = "Sin seleccionar";
        }
        if (selectedProductPriceLabel) {
          selectedProductPriceLabel.textContent = formatMoney(0);
        }
        if (selectedProductStockLabel) {
          selectedProductStockLabel.textContent = "0";
        }
        return;
      }

      if (selectedProductNameLabel) {
        selectedProductNameLabel.textContent = option.dataset.name || option.textContent.trim();
      }
      if (selectedProductPriceLabel) {
        selectedProductPriceLabel.textContent = formatMoney(Number(option.dataset.price || 0));
      }
      if (selectedProductStockLabel) {
        selectedProductStockLabel.textContent = String(Number(option.dataset.stock || 0));
      }
    }

    function render() {
      const productTotal = currentProductTotal();
      const invoiceTotal = serviceBalance + productTotal;
      productTotalLabel.textContent = formatMoney(productTotal);
      invoiceTotalLabel.textContent = formatMoney(invoiceTotal);
      emptyState.style.display = items.length ? "none" : "flex";
      list.innerHTML = "";
      hiddenInputs.innerHTML = "";

      items.forEach(function (item, index) {
        const line = document.createElement("article");
        line.className = "product-cart-line";
        line.innerHTML =
          "<div>" +
          "<strong>" + item.name + "</strong>" +
          "<p>Cantidad: " + item.quantity + " | Precio unitario: " + formatMoney(item.price) + " | Stock ref. " + item.stock + "</p>" +
          "</div>" +
          "<div class='product-cart-actions'>" +
          "<strong>" + formatMoney(item.quantity * item.price) + "</strong>" +
          "<button type='button' class='btn-danger-soft product-cart-remove' data-remove-index='" + index + "'>Quitar</button>" +
          "</div>";
        list.appendChild(line);

        const productInput = document.createElement("input");
        productInput.type = "hidden";
        productInput.name = "producto_id[]";
        productInput.value = String(item.id);
        hiddenInputs.appendChild(productInput);

        const quantityHidden = document.createElement("input");
        quantityHidden.type = "hidden";
        quantityHidden.name = "cantidad_producto[]";
        quantityHidden.value = String(item.quantity);
        hiddenInputs.appendChild(quantityHidden);
      });

      updateSuggestedAmount();
    }

    function addProduct() {
      const option = picker.options[picker.selectedIndex];
      const quantity = Number(quantityInput.value || 0);
      if (!option || !option.value) {
        picker.setCustomValidity("Selecciona un producto para agregar.");
        picker.reportValidity();
        return;
      }
      picker.setCustomValidity("");
      if (!Number.isInteger(quantity) || quantity <= 0) {
        quantityInput.setCustomValidity("La cantidad debe ser mayor a cero.");
        quantityInput.reportValidity();
        return;
      }
      quantityInput.setCustomValidity("");

      const existing = items.find(function (item) {
        return item.id === Number(option.value);
      });
      if (existing) {
        existing.quantity += quantity;
      } else {
        items.push({
          id: Number(option.value),
          name: option.dataset.name || option.textContent.trim(),
          price: parseFloat(option.dataset.price) || 0,
          stock: Number(option.dataset.stock || 0),
          quantity: quantity,
        });
      }

      picker.value = "";
      quantityInput.value = "1";
      updateSelectedProductSummary();
      render();
    }

    addButton.addEventListener("click", addProduct);
    picker.addEventListener("change", updateSelectedProductSummary);
    list.addEventListener("click", function (event) {
      const button = event.target.closest("[data-remove-index]");
      if (!button) {
        return;
      }
      const index = Number(button.dataset.removeIndex);
      items.splice(index, 1);
      render();
    });

    if (amountInput) {
      amountInput.addEventListener("input", function () {
        amountInput.dataset.userEdited = "1";
      });
    }

    updateSelectedProductSummary();
    render();
  });
});
