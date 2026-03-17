import json
from datetime import timedelta

from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt

from apps.citas.models import Reserva, Servicio
from apps.sesiones.models import Usuario


def _validar_login(request):
    # Valida que exista una sesion activa para el API.
    if "usuario_id" not in request.session:
        return JsonResponse({"error": "autenticacion requerida"}, status=401)
    return None


@csrf_exempt
def api_eventos(request):
    denied = _validar_login(request)
    if denied:
        return denied

    usuario_id = request.session.get("usuario_id")
    usuario_rol = request.session.get("usuario_rol")

    if request.method == "GET":
        reservas = Reserva.objects.select_related("cliente", "servicio")
        if usuario_rol != Usuario.ROL_ADMIN:
            reservas = reservas.filter(cliente_id=usuario_id)

        payload = [
            {
                "id": reserva.id,
                "title": f"{reserva.cliente.nombre} - {reserva.servicio.nombre}",
                "cliente": f"{reserva.cliente.nombre} {reserva.cliente.apellido}",
                "servicio": reserva.servicio.nombre,
                "startDate": reserva.fecha_inicio.isoformat(),
                "endDate": reserva.fecha_fin.isoformat(),
                "estado": reserva.estado,
            }
            for reserva in reservas
        ]
        return JsonResponse(payload, safe=False)

    if request.method == "POST":
        body = json.loads(request.body or "{}")
        cliente_id = body.get("cliente_id")
        servicio_id = body.get("servicio_id")
        inicio = parse_datetime(body.get("startDate")) or timezone.now()
        fin = parse_datetime(body.get("endDate")) or (inicio + timedelta(hours=1))

        if usuario_rol != Usuario.ROL_ADMIN:
            cliente_id = usuario_id

        if not servicio_id:
            return JsonResponse({"error": "servicio_id es obligatorio"}, status=400)

        cliente = Usuario.objects.filter(id=cliente_id).first()
        servicio = Servicio.objects.filter(id=servicio_id).first()
        if not cliente or not servicio:
            return JsonResponse({"error": "cliente_id o servicio_id invalido"}, status=400)

        reserva = Reserva.objects.create(
            cliente=cliente,
            servicio=servicio,
            fecha_inicio=inicio,
            fecha_fin=fin,
            estado=body.get("estado", "programada"),
        )
        return JsonResponse(
            {
                "id": reserva.id,
                "title": f"{reserva.cliente.nombre} - {reserva.servicio.nombre}",
                "cliente": f"{reserva.cliente.nombre} {reserva.cliente.apellido}",
                "servicio": reserva.servicio.nombre,
                "startDate": reserva.fecha_inicio.isoformat(),
                "endDate": reserva.fecha_fin.isoformat(),
                "estado": reserva.estado,
            },
            status=201,
        )

    return JsonResponse({"error": "metodo no permitido"}, status=405)
