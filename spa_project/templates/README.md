# Templates globales

Esta carpeta contiene plantillas que no pertenecen de forma exclusiva a una sola app.

## Que vive aqui

- `base_public.html`: base visual compartida del sitio.
- `index.html`, `conocenos.html`, `login.html`, `registro.html`: paginas publicas generales.
- `cliente/`: vistas globales del flujo del cliente.
- `administrador/`: vistas globales del panel administrativo.

## Cuando usar esta carpeta

- Cuando la plantilla es compartida entre varias apps.
- Cuando representa una pagina global del sitio.

## Cuando NO usar esta carpeta

- Si la vista pertenece claramente a una sola app, dejala dentro de `apps/<app>/templates/<app>/`.
