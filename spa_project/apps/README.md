# Apps del proyecto

Cada carpeta dentro de `apps/` representa un dominio funcional del sistema:

- `citas/`: reservas y servicios.
- `inventario/`: productos, proveedores, compras, control y devoluciones de compra.
- `sesiones/`: login, registro, perfil y flujo de usuario.
- `ventas/`: ventas, validaciones, devoluciones de clientes y Telegram.
- `common/`: utilidades compartidas.

Regla practica:

- Si el cambio pertenece a una funcionalidad del negocio, entra primero a la app de ese dominio.
- Si el recurso lo usan varias apps, revisa si debe vivir en `common/`, `templates/` globales o `static/` global.
