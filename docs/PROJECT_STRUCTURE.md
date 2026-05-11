# Estructura del proyecto

Este proyecto esta organizado para que cada app de Django tenga su propia responsabilidad y sea facil de ubicar desde VS Code.

## Raiz

- `README.md`: resumen general del proyecto y notas operativas.
- `.vscode/`: configuracion del workspace para depurar y navegar mejor.
- `spa_project/`: codigo fuente real del sistema Django.

## Dentro de `spa_project/`

- `manage.py`: punto de entrada para comandos Django.
- `config/`: configuracion global del proyecto.
- `apps/`: modulos funcionales separados por dominio.
- `templates/`: vistas globales compartidas entre apps.
- `static/`: recursos globales compartidos entre apps.

## Apps principales

### `apps/citas/`

- Maneja reservas y servicios del spa.
- `views/`: vistas separadas en `cita_views.py`, `servicio_views.py` y `api_views.py`.
- `templates/citas/`: interfaces publicas y de dashboard.
- `static/citas/`: estilos propios de citas.

### `apps/inventario/`

- Maneja productos, proveedores, compras, control y devoluciones de compra.
- `views/`: una vista por subdominio (`producto`, `proveedor`, `compra`, `control`, `dashboard`).
- `templates/inventario/dashboard/`: UI administrativa por modulo.
- `static/inventario/`: estilos por seccion del inventario.
- `templatetags/`: filtros y utilidades para templates del inventario.

### `apps/sesiones/`

- Maneja autenticacion, perfil, decoradores y comandos de carga inicial.
- `views/auth_views.py`: login, registro y flujo de acceso.
- `views/profile_views.py`: perfil del cliente y datos asociados.
- `management/commands/`: comandos utiles para sembrar datos.

### `apps/ventas/`

- Maneja ventas, validaciones de pago, devoluciones de clientes y Telegram.
- `views/venta_views.py`: flujo administrativo de ventas.
- `views/devolucion_views.py`: solicitudes de devolucion del cliente y acciones desde Telegram.
- `telegram_notifier.py`: envio de notificaciones.
- `devoluciones.py`: logica de soporte para devoluciones de venta.

### `apps/common/`

- Utilidades compartidas entre apps.
- `currency.py` y `templatetags/money_tags.py`: formato y parseo de dinero.

## Templates globales

Usa `spa_project/templates/` para pantallas que no pertenecen claramente a una sola app, por ejemplo:

- `index.html`
- `conocenos.html`
- `login.html`
- `registro.html`
- `templates/cliente/`
- `templates/administrador/`

## Static global

Usa `spa_project/static/` para recursos reutilizables entre varias apps:

- `css/site/`: estilos globales del sitio.
- `css/dashboard/`: estilos globales de dashboard.
- `js/site/`: scripts compartidos.
- `img/`: imagenes del sitio.

Cuando un estilo o script es solo de una app, la ubicacion preferida es `apps/<app>/static/<app>/`.

## Como ubicarse rapido en VS Code

### Si quieres cambiar autenticacion o perfil

- Ve a `spa_project/apps/sesiones/`.

### Si quieres cambiar reservas o servicios

- Ve a `spa_project/apps/citas/`.

### Si quieres cambiar inventario o compras

- Ve a `spa_project/apps/inventario/`.

### Si quieres cambiar ventas, validaciones o devoluciones de clientes

- Ve a `spa_project/apps/ventas/`.

### Si quieres cambiar paginas publicas generales

- Ve a `spa_project/templates/` y `spa_project/static/css/site/`.

## Criterio recomendado para nuevos archivos

- Coloca codigo de negocio por dominio dentro de la app correspondiente.
- Deja `config/` solo para configuracion global.
- Usa `templates/` y `static/` globales solo cuando el recurso sea compartido.
- Mantén las vistas separadas por tema dentro de `views/` cuando una app crezca.
