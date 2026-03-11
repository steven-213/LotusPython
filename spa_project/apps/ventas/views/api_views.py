import json
from decimal import Decimal

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from apps.sesiones.models import Usuario
from apps.ventas.models import Venta


def _validar_admin(request):
    # Valida sesion y rol admin para endpoints del API.
    if "usuario_id" not in request.session:
        return JsonResponse({"error": "autenticacion requerida"}, status=401)
    if request.session.get("usuario_rol") != "admin":
        return JsonResponse({"error": "forbidden"}, status=403)
    return None


@csrf_exempt
def api_ventas(request):
    # Lista o crea ventas segun el metodo HTTP.
    denied = _validar_admin(request)
    if denied:
        return denied
    if request.method == "GET":
        ventas = Venta.objects.select_related("cliente").all()
        data = [
            {
                "id": venta.id,
                "cliente": venta.cliente.nombre,
                "total": float(venta.total),
                "fecha": venta.fecha.isoformat(),
            }
            for venta in ventas
        ]
        return JsonResponse(data, safe=False)

    if request.method == "POST":
        payload = json.loads(request.body or "{}")
        cliente_id = payload.get("cliente_id")
        total = Decimal(str(payload.get("total", "0")))
        cliente = Usuario.objects.filter(id=cliente_id).first()
        if not cliente:
            return JsonResponse({"error": "cliente_id inválido"}, status=400)
        venta = Venta.objects.create(cliente=cliente, total=total)
        return JsonResponse(
            {
                "id": venta.id,
                "cliente": venta.cliente.nombre,
                "total": float(venta.total),
                "fecha": venta.fecha.isoformat(),
            },
            status=201,
        )

    return JsonResponse({"error": "Método no permitido"}, status=405)


def api_resumen(request):
    # Devuelve un resumen basico de ventas.
    denied = _validar_admin(request)
    if denied:
        return denied
    if request.method != "GET":
        return JsonResponse({"error": "Método no permitido"}, status=405)
    total_ventas = Venta.objects.count()
    total_monto = sum((venta.total for venta in Venta.objects.all()), Decimal("0"))
    return JsonResponse({"total_ventas": total_ventas, "monto_total": float(total_monto)})
