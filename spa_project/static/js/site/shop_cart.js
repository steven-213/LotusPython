(function () {
  const CART_KEY = "lotus_cart";
  const WARNING_KEY = "lotus_checkout_warning";

  function parseJsonScript(id) {
    const node = document.getElementById(id);
    if (!node) {
      return null;
    }

    try {
      return JSON.parse(node.textContent);
    } catch (error) {
      return null;
    }
  }

  function getCookie(name) {
    const cookie = document.cookie
      .split(";")
      .map((item) => item.trim())
      .find((item) => item.startsWith(name + "="));

    if (!cookie) {
      return "";
    }

    return decodeURIComponent(cookie.split("=")[1] || "");
  }

  function formatearMoneda(valor) {
    if (window.CopMoney && typeof window.CopMoney.formatDisplay === "function") {
      return window.CopMoney.formatDisplay(valor);
    }

    return new Intl.NumberFormat("es-CO", {
      style: "currency",
      currency: "COP",
      maximumFractionDigits: 0,
    }).format(valor);
  }

  function initShopCart() {
    const stockCatalogo = parseJsonScript("shop-stock-data");
    const checkoutConfig = parseJsonScript("shop-config-data");
    if (!stockCatalogo || !checkoutConfig) {
      return;
    }

    let carrito = [];

    function leerCarrito() {
      try {
        const data = JSON.parse(localStorage.getItem(CART_KEY));
        return Array.isArray(data) ? data : [];
      } catch (error) {
        return [];
      }
    }

    function guardarCarrito() {
      localStorage.setItem(CART_KEY, JSON.stringify(carrito));
    }

    function mostrarFeedback(mensaje, estado) {
      const caja = document.getElementById("cart-feedback");
      if (!caja) {
        return;
      }

      if (!mensaje) {
        caja.hidden = true;
        caja.textContent = "";
        caja.dataset.state = "";
        return;
      }

      caja.hidden = false;
      caja.dataset.state = estado || "info";
      caja.textContent = mensaje;
    }

    function sanitizarCarrito() {
      carrito = carrito
        .filter((item) => stockCatalogo[item.id])
        .map((item) => {
          const stock = Math.max(0, Number(stockCatalogo[item.id] || 0));
          const cantidad = Math.max(1, Math.min(Number(item.cantidad || 1), stock));
          return { ...item, cantidad };
        })
        .filter((item) => item.cantidad > 0);

      guardarCarrito();
    }

    function eliminarDelCarrito(id) {
      carrito = carrito.filter((item) => item.id !== id);
      guardarCarrito();
      renderizarCarrito();
      mostrarFeedback("Producto retirado del carrito.", "info");
    }

    function vaciarCarrito() {
      if (!carrito.length) {
        mostrarFeedback("El carrito ya esta vacio.", "info");
        return;
      }

      carrito = [];
      guardarCarrito();
      renderizarCarrito();
      mostrarFeedback("El carrito se vacio correctamente.", "info");
    }

    function renderizarCarrito() {
      const contenedor = document.getElementById("cart-items-list");
      const totalNodo = document.getElementById("cart-total");
      const contadorNodo = document.getElementById("cart-count");

      if (!contenedor || !totalNodo || !contadorNodo) {
        return;
      }

      contenedor.innerHTML = "";
      let total = 0;
      let unidades = 0;

      if (!carrito.length) {
        contenedor.innerHTML =
          '<div class="shop-cart-empty"><i class="bi bi-bag"></i><p>Tu carrito esta vacio por ahora.</p></div>';
        totalNodo.textContent = formatearMoneda(0);
        contadorNodo.textContent = "0";
        return;
      }

      carrito.forEach((item) => {
        total += Number(item.precio) * Number(item.cantidad);
        unidades += Number(item.cantidad);

        const fila = document.createElement("article");
        fila.className = "shop-cart-item";
        const copy = document.createElement("div");
        copy.className = "shop-cart-item-copy";

        const title = document.createElement("strong");
        title.textContent = item.nombre;
        copy.appendChild(title);

        const meta = document.createElement("span");
        meta.textContent = item.cantidad + " x " + formatearMoneda(item.precio);
        copy.appendChild(meta);

        const button = document.createElement("button");
        button.type = "button";
        button.className = "shop-cart-remove";
        button.setAttribute("aria-label", "Eliminar " + item.nombre);

        const icon = document.createElement("i");
        icon.className = "bi bi-x-circle-fill";
        button.appendChild(icon);

        fila.appendChild(copy);
        fila.appendChild(button);

        button.addEventListener("click", function () {
          eliminarDelCarrito(item.id);
        });
        contenedor.appendChild(fila);
      });

      totalNodo.textContent = formatearMoneda(total);
      contadorNodo.textContent = String(unidades);
    }

    window.agregarAlCarrito = function (id, nombre, precio, stockMaximo) {
      const input = document.getElementById("qty-" + id);
      const cantidadNueva = Math.max(1, Number.parseInt(input.value, 10) || 1);
      const maximo = Math.max(0, Number(stockMaximo || 0));

      if (maximo <= 0) {
        mostrarFeedback("Ese producto ya no tiene stock disponible.", "error");
        return;
      }

      const index = carrito.findIndex((item) => item.id === id);
      const cantidadActual = index >= 0 ? carrito[index].cantidad : 0;

      if (cantidadActual + cantidadNueva > maximo) {
        mostrarFeedback("Solo quedan " + maximo + " unidades de " + nombre + ".", "error");
        return;
      }

      if (index >= 0) {
        carrito[index].cantidad += cantidadNueva;
      } else {
        carrito.push({
          id: id,
          nombre: nombre,
          precio: Number.parseFloat(precio),
          cantidad: cantidadNueva,
        });
      }

      guardarCarrito();
      renderizarCarrito();
      mostrarFeedback(nombre + " se agrego al carrito.", "success");
      input.value = "1";
    };

    window.vaciarCarrito = vaciarCarrito;

    window.procederAlPago = async function () {
      if (!carrito.length) {
        mostrarFeedback("Agrega al menos un producto antes de procesar el pedido.", "error");
        return;
      }

      const boton = document.getElementById("cart-submit");
      const metodo = document.getElementById("metodo_pago").value;
      const telefono = document.getElementById("telefono_cliente").value.trim();
      const direccion = document.getElementById("direccion_cliente").value.trim();

      boton.disabled = true;
      boton.innerHTML = '<i class="bi bi-hourglass-split"></i> Procesando...';
      mostrarFeedback("Validando tu pedido con el inventario disponible...", "info");

      try {
        const response = await fetch(checkoutConfig.processUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": checkoutConfig.csrfToken || getCookie("csrftoken"),
          },
          body: JSON.stringify({
            carrito: carrito,
            metodo_pago: metodo,
            telefono: telefono,
            direccion: direccion,
          }),
        });

        const data = await response.json();

        if (data.redirect_url) {
          window.location.href = data.redirect_url;
          return;
        }

        if (!response.ok || data.status !== "success") {
          throw new Error(data.message || "No se pudo registrar la compra.");
        }

        localStorage.removeItem(CART_KEY);
        if (data.warning) {
          sessionStorage.setItem(WARNING_KEY, data.warning);
        } else {
          sessionStorage.removeItem(WARNING_KEY);
        }
        window.location.href = checkoutConfig.resultUrl;
      } catch (error) {
        mostrarFeedback(error.message || "No se pudo procesar el pedido.", "error");
      } finally {
        boton.disabled = false;
        boton.innerHTML = '<i class="bi bi-bag-check"></i> Procesar pedido';
      }
    };

    carrito = leerCarrito();
    sanitizarCarrito();
    renderizarCarrito();
  }

  document.addEventListener("DOMContentLoaded", initShopCart);
})();
