# Static global

Esta carpeta contiene recursos globales reutilizables por varias partes del proyecto.

## Subcarpetas principales

- `css/site/`: estilos del sitio publico y pantallas compartidas.
- `css/dashboard/`: estilos compartidos de paneles administrativos.
- `js/site/`: scripts globales.
- `img/`: imagenes reutilizables del sitio.
- `cliente/` y `administrador/`: estilos heredados de vistas globales.

## Criterio de uso

- Si el recurso es global o lo usan varias apps, puede vivir aqui.
- Si el recurso es exclusivo de una app, la ubicacion preferida es `apps/<app>/static/<app>/`.
