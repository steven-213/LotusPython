# Style Map

## Active CSS Architecture
- `static/css/site/base.css`: base visual system (header, nav, buttons, footer, flash messages).
- `static/css/site/home.css`: homepage sections (`templates/index.html`).
- `static/css/site/conocenos.css`: about page sections (`templates/conocenos.html`).
- `static/css/site/auth.css`: login/registro forms (`templates/login.html`, `templates/registro.html`).
- `static/css/site/admin_dashboard.css`: admin dashboard (`templates/administrador/dashboard.html`).
- `static/css/site/admin_calendar.css`: admin calendar page (`templates/administrador/calendar.html`).
- `static/css/site/admin_sales.css`: admin sales page (`templates/administrador/ventas.html`).
- `static/css/site/services_page.css`: client services page (`templates/cliente/servicios.html`).
- `static/css/site/shop_page.css`: client shop/result pages (`templates/cliente/compra.html`, `templates/cliente/resultado.html`, `templates/sesiones/perfil.html`).
- `static/css/site/perfil.css`: user profile purchases (`templates/sesiones/perfil.html`).

## Shared Base Templates
- `templates/base_public.html`: shared public layout.

## Removed Legacy CSS
- `static/css/index.css`
- `static/css/nosotros.css`
- `static/css/login.css`
- `static/css/registro.css`
- `static/css/servicios.css`
- `static/css/compra.css`
- `static/css/global_style.css`
- `static/css/dashboard/*` (entire legacy folder removed)

## Legacy Templates Status
- `templates/productosAdm/*`, `templates/serviciosAdm/*`, `templates/usuariosAdm/*` are legacy and currently not wired in active routes.
- Their CSS references were updated to avoid broken static links, but they should be treated as deprecated.

