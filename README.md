# LotusPython

## Mapa rápido del proyecto

- `spa_project/apps/`: lógica principal separada por dominio.
- `spa_project/config/`: configuración Django, URLs globales y settings de pruebas.
- `spa_project/templates/`: plantillas globales compartidas.
- `spa_project/static/`: CSS, JS e imágenes globales.

Si quieres ubicarte más rápido dentro del proyecto, revisa [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md).

## Telegram para varios administradores

La app ahora soporta varios destinatarios de Telegram al mismo tiempo.

En `spa_project/.env` puedes usar cualquiera de estas opciones:

- `TELEGRAM_CHAT_ID=123456789` para un solo administrador.
- `TELEGRAM_CHAT_IDS=123456789,987654321` para varios administradores.

No pongas varios IDs entre comillas dentro de `TELEGRAM_CHAT_ID`.
Si son varios, sepáralos por coma en `TELEGRAM_CHAT_IDS`.

Si defines `TELEGRAM_CHAT_IDS`, el bot enviara las notificaciones de compras y devoluciones a todos los chats configurados.
