from django.urls import reverse


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
        "sugerencia_pedido",
        "informe_inventario",
        "devolucion_lista",
        "devolucion_nueva",
        "devolucion_detalle",
        "devolucion_eliminar",
    },
    "ventas": {
        "venta_lista",
        "venta_nueva",
        "venta_detalle",
        "venta_validaciones",
    },
    "citas": {
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


def _build_sidebar_sections(namespace: str, url_name: str):
    def is_active(item_namespace: str, item_urls: set[str]) -> bool:
        return namespace == item_namespace and url_name in item_urls

    return [
        {
            "title": "General",
            "is_active": namespace == "sesiones" and url_name == "admin_dashboard",
            "items": [
                {
                    "label": "Panel principal",
                    "icon": "bi-speedometer2",
                    "url": reverse("sesiones:admin_dashboard"),
                    "is_active": namespace == "sesiones" and url_name == "admin_dashboard",
                },
            ],
        },
        {
            "title": "Inventario",
            "is_active": namespace == "inventario",
            "items": [
                {
                    "label": "Dashboard",
                    "icon": "bi-grid-1x2",
                    "url": reverse("inventario:dashboard"),
                    "is_active": namespace == "inventario" and url_name == "dashboard",
                },
                {
                    "label": "Productos",
                    "icon": "bi-box-seam",
                    "url": reverse("inventario:producto_lista"),
                    "is_active": is_active(
                        "inventario",
                        {
                            "producto_lista",
                            "producto_importar_csv",
                            "producto_nuevo",
                            "producto_editar",
                            "producto_detalle",
                            "producto_eliminar",
                        },
                    ),
                },
                {
                    "label": "Compras",
                    "icon": "bi-cart-check",
                    "url": reverse("inventario:compra_lista"),
                    "is_active": is_active(
                        "inventario",
                        {
                            "compra_lista",
                            "compra_nueva",
                            "compra_editar",
                            "compra_detalle",
                            "compra_eliminar",
                        },
                    ),
                },
                {
                    "label": "Proveedores",
                    "icon": "bi-truck",
                    "url": reverse("inventario:proveedor_lista"),
                    "is_active": is_active(
                        "inventario",
                        {
                            "proveedor_lista",
                            "proveedor_nuevo",
                            "proveedor_editar",
                            "proveedor_detalle",
                            "proveedor_eliminar",
                        },
                    ),
                },
                {
                    "label": "Devoluciones",
                    "icon": "bi-arrow-return-left",
                    "url": reverse("inventario:devolucion_lista"),
                    "is_active": is_active(
                        "inventario",
                        {
                            "devolucion_lista",
                            "devolucion_nueva",
                            "devolucion_detalle",
                            "devolucion_eliminar",
                        },
                    ),
                },
                {
                    "label": "Control",
                    "icon": "bi-clipboard2-pulse",
                    "url": reverse("inventario:sugerencia_pedido"),
                    "is_active": is_active(
                        "inventario",
                        {"sugerencia_pedido", "informe_inventario"},
                    ),
                },
            ],
        },
        {
            "title": "Ventas",
            "is_active": namespace == "ventas",
            "items": [
                {
                    "label": "Resumen de ventas",
                    "icon": "bi-receipt",
                    "url": reverse("ventas:venta_lista"),
                    "is_active": is_active(
                        "ventas",
                        {"venta_lista", "venta_detalle", "venta_validaciones"},
                    ),
                },
                {
                    "label": "Nueva venta",
                    "icon": "bi-plus-circle",
                    "url": reverse("ventas:venta_nueva"),
                    "is_active": namespace == "ventas" and url_name == "venta_nueva",
                },
            ],
        },
        {
            "title": "Citas",
            "is_active": namespace == "citas",
            "items": [
                {
                    "label": "Calendario",
                    "icon": "bi-calendar-event",
                    "url": reverse("citas:calendario"),
                    "is_active": is_active(
                        "citas",
                        {
                            "calendario",
                            "agenda",
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
                },
                {
                    "label": "Nueva reserva",
                    "icon": "bi-calendar-plus",
                    "url": reverse("citas:reserva_nueva"),
                    "is_active": namespace == "citas" and url_name == "reserva_nueva",
                },
                {
                    "label": "Servicios",
                    "icon": "bi-stars",
                    "url": reverse("citas:servicio_lista"),
                    "is_active": is_active(
                        "citas",
                        {"servicio_lista", "servicio_nuevo", "servicio_editar", "servicio_eliminar"},
                    ),
                },
            ],
        },
    ]


def admin_shell(request):
    resolver_match = getattr(request, "resolver_match", None)
    namespace = getattr(resolver_match, "namespace", "") or ""
    url_name = getattr(resolver_match, "url_name", "") or ""
    is_admin = request.session.get("usuario_rol") == "admin"

    allowed_views = ADMIN_VIEW_NAMES.get(namespace, set())
    show_admin_sidebar = bool(is_admin and url_name in allowed_views)

    return {
        "show_admin_sidebar": show_admin_sidebar,
        "admin_sidebar_sections": _build_sidebar_sections(namespace, url_name)
        if show_admin_sidebar
        else [],
        "admin_sidebar_module": namespace if show_admin_sidebar else "",
    }
