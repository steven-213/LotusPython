from apps.common.seo import build_site_meta
from django.urls import NoReverseMatch, reverse


ADMIN_VIEW_NAMES = {
    "sesiones": {
        "admin_dashboard",
    },
    "inventario": {
        "dashboard",
        "producto_lista",
        "producto_importar_csv",
        "producto_nuevo",
        "producto_editar",
        "producto_detalle",
        "producto_eliminar",
        "compra_lista",
        "compra_nueva",
        "compra_editar",
        "compra_detalle",
        "compra_eliminar",
        "proveedor_lista",
        "proveedor_nuevo",
        "proveedor_editar",
        "proveedor_detalle",
        "proveedor_eliminar",
        "devolucion_lista",
        "devolucion_nueva",
        "devolucion_detalle",
        "devolucion_eliminar",
    },
    "ventas": {
        "venta_lista",
        "venta_listado",
        "venta_nueva",
        "venta_detalle",
        "venta_validaciones",
    },
    "citas": {
        "dashboard",
        "almanaque",
        "calendario",
        "agenda",
        "reserva_nueva",
        "reserva_detalle",
        "reserva_editar",
        "reserva_cancelar",
        "reserva_confirmar",
        "reserva_iniciar",
        "reserva_finalizar",
        "reserva_no_asistio",
        "reserva_registrar_pago",
        "servicio_lista",
        "servicio_nuevo",
        "servicio_editar",
        "servicio_eliminar",
    },
}


def _safe_reverse(view_name: str) -> str:
    try:
        return reverse(view_name)
    except NoReverseMatch:
        return ""


def _build_item(namespace: str, current_url_name: str, *, label: str, icon: str, view_name: str, active_urls: set[str]):
    url = _safe_reverse(view_name)
    if not url:
        return None

    return {
        "label": label,
        "icon": icon,
        "url": url,
        "is_active": namespace == view_name.split(":")[0] and current_url_name in active_urls,
    }


def _module_sidebar_map(namespace: str, url_name: str):
    return {
        "inventario": {
            "title": "Inventario",
            "eyebrow": "Modulo activo",
            "copy": "Accede solo a productos, compras, proveedores y devoluciones de este modulo.",
            "items": [
                _build_item(
                    namespace,
                    url_name,
                    label="Inicio del modulo",
                    icon="bi-grid-1x2",
                    view_name="inventario:dashboard",
                    active_urls={"dashboard"},
                ),
                _build_item(
                    namespace,
                    url_name,
                    label="Productos",
                    icon="bi-box-seam",
                    view_name="inventario:producto_lista",
                    active_urls={
                        "producto_lista",
                        "producto_importar_csv",
                        "producto_nuevo",
                        "producto_editar",
                        "producto_detalle",
                        "producto_eliminar",
                    },
                ),
                _build_item(
                    namespace,
                    url_name,
                    label="Compras",
                    icon="bi-cart-check",
                    view_name="inventario:compra_lista",
                    active_urls={
                        "compra_lista",
                        "compra_nueva",
                        "compra_editar",
                        "compra_detalle",
                        "compra_eliminar",
                    },
                ),
                _build_item(
                    namespace,
                    url_name,
                    label="Proveedores",
                    icon="bi-truck",
                    view_name="inventario:proveedor_lista",
                    active_urls={
                        "proveedor_lista",
                        "proveedor_nuevo",
                        "proveedor_editar",
                        "proveedor_detalle",
                        "proveedor_eliminar",
                    },
                ),
                _build_item(
                    namespace,
                    url_name,
                    label="Devoluciones",
                    icon="bi-arrow-return-left",
                    view_name="inventario:devolucion_lista",
                    active_urls={
                        "devolucion_lista",
                        "devolucion_nueva",
                        "devolucion_detalle",
                        "devolucion_eliminar",
                    },
                ),
            ],
        },
        "ventas": {
            "title": "Ventas",
            "eyebrow": "Modulo activo",
            "copy": "Mantén a la mano solo los accesos que pertenecen al flujo de ventas.",
            "items": [
                _build_item(
                    namespace,
                    url_name,
                    label="Ventas",
                    icon="bi-receipt",
                    view_name="ventas:venta_lista",
                    active_urls={"venta_lista", "venta_listado", "venta_detalle", "venta_validaciones"},
                ),
                _build_item(
                    namespace,
                    url_name,
                    label="Nueva venta",
                    icon="bi-plus-circle",
                    view_name="ventas:venta_nueva",
                    active_urls={"venta_nueva"},
                ),
            ],
        },
        "citas": {
            "title": "Citas",
            "eyebrow": "Modulo activo",
            "copy": "Navega entre dashboard, almanaque, reservas y servicios del modulo de citas.",
            "items": [
                _build_item(
                    namespace,
                    url_name,
                    label="Dashboard",
                    icon="bi-speedometer2",
                    view_name="citas:dashboard",
                    active_urls={
                        "dashboard",
                        "reserva_detalle",
                        "reserva_editar",
                        "reserva_cancelar",
                        "reserva_confirmar",
                        "reserva_iniciar",
                        "reserva_finalizar",
                        "reserva_no_asistio",
                        "reserva_registrar_pago",
                    },
                ),
                _build_item(
                    namespace,
                    url_name,
                    label="Almanaque",
                    icon="bi-calendar-event",
                    view_name="citas:almanaque",
                    active_urls={
                        "almanaque",
                        "calendario",
                        "agenda",
                    },
                ),
                _build_item(
                    namespace,
                    url_name,
                    label="Nueva reserva",
                    icon="bi-calendar-plus",
                    view_name="citas:reserva_nueva",
                    active_urls={"reserva_nueva"},
                ),
                _build_item(
                    namespace,
                    url_name,
                    label="Servicios",
                    icon="bi-stars",
                    view_name="citas:servicio_lista",
                    active_urls={"servicio_lista", "servicio_nuevo", "servicio_editar", "servicio_eliminar"},
                ),
            ],
        },
    }


def _build_dashboard_sections():
    dashboard_items = [
        {
            "label": "Inventario",
            "icon": "bi-box-seam",
            "url": _safe_reverse("inventario:dashboard"),
            "is_active": False,
        },
        {
            "label": "Ventas",
            "icon": "bi-receipt",
            "url": _safe_reverse("ventas:venta_lista"),
            "is_active": False,
        },
        {
            "label": "Citas",
            "icon": "bi-calendar-event",
            "url": _safe_reverse("citas:calendario"),
            "is_active": False,
        },
        {
            "label": "Devoluciones",
            "icon": "bi-arrow-return-left",
            "url": _safe_reverse("inventario:devolucion_lista"),
            "is_active": False,
        },
    ]

    dashboard_items = [item for item in dashboard_items if item["url"]]
    return [
        {
            "title": "Modulos",
            "is_active": False,
            "items": dashboard_items,
        }
    ]


def _build_sidebar_state(namespace: str, url_name: str):
    if namespace == "sesiones" and url_name == "admin_dashboard":
        return {
            "admin_sidebar_sections": _build_dashboard_sections(),
            "admin_sidebar_title": "Panel principal",
            "admin_sidebar_eyebrow": "Panel admin",
            "admin_sidebar_copy": "Ingresa a cada modulo desde un panel mas limpio y directo.",
            "admin_sidebar_back_url": "",
            "admin_sidebar_back_label": "",
            "admin_sidebar_module": "sesiones",
        }

    module_map = _module_sidebar_map(namespace, url_name)
    current_module = module_map.get(namespace)

    if not current_module:
        return {
            "admin_sidebar_sections": [],
            "admin_sidebar_title": "Panel admin",
            "admin_sidebar_eyebrow": "Panel admin",
            "admin_sidebar_copy": "Navegacion del administrador.",
            "admin_sidebar_back_url": "",
            "admin_sidebar_back_label": "",
            "admin_sidebar_module": namespace,
        }

    items = [item for item in current_module["items"] if item]
    return {
        "admin_sidebar_sections": [
            {
                "title": f"Atajos de {current_module['title']}",
                "is_active": True,
                "items": items,
            }
        ],
        "admin_sidebar_title": current_module["title"],
        "admin_sidebar_eyebrow": current_module["eyebrow"],
        "admin_sidebar_copy": current_module["copy"],
        "admin_sidebar_back_url": _safe_reverse("sesiones:admin_dashboard"),
        "admin_sidebar_back_label": "Volver al panel",
        "admin_sidebar_module": namespace,
    }


def admin_shell(request):
    resolver_match = getattr(request, "resolver_match", None)
    namespace = getattr(resolver_match, "namespace", "") or ""
    url_name = getattr(resolver_match, "url_name", "") or ""
    is_admin = request.session.get("usuario_rol") == "admin"

    allowed_views = ADMIN_VIEW_NAMES.get(namespace, set())
    show_admin_sidebar = bool(is_admin and url_name in allowed_views)

    sidebar_state = _build_sidebar_state(namespace, url_name) if show_admin_sidebar else {
        "admin_sidebar_sections": [],
        "admin_sidebar_title": "",
        "admin_sidebar_eyebrow": "",
        "admin_sidebar_copy": "",
        "admin_sidebar_back_url": "",
        "admin_sidebar_back_label": "",
        "admin_sidebar_module": "",
    }

    return {
        "show_admin_sidebar": show_admin_sidebar,
        "session_user_name": request.session.get("usuario_nombre", ""),
        "session_timeout_expires_at": getattr(request, "manual_session_expires_at", None),
        "session_timeout_redirect_url": f"{_safe_reverse('sesiones:login')}?reason=session_expired",
        **sidebar_state,
        **build_site_meta(request, show_admin_sidebar=show_admin_sidebar),
    }
