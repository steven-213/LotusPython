import json
from datetime import timedelta

from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt

from apps.citas.models import Cita, Servicio
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
        citas = Cita.objects.select_related("cliente", "servicio")
        if usuario_rol != Usuario.ROL_ADMIN:
            citas = citas.filter(cliente_id=usuario_id)

        payload = [
            {
                "id": cita.id,
                "title": f"{cita.cliente.nombre} - {cita.servicio.nombre}",
                "cliente": f"{cita.cliente.nombre} {cita.cliente.apellido}",
                "servicio": cita.servicio.nombre,
                "startDate": cita.fecha_inicio.isoformat(),
                "endDate": cita.fecha_fin.isoformat(),
                "estado": cita.estado,
            }
            for cita in citas
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

        cita = Cita.objects.create(
            cliente=cliente,
            servicio=servicio,
            fecha_inicio=inicio,
            fecha_fin=fin,
            estado=body.get("estado", "programada"),
        )
        return JsonResponse(
            {
                "id": cita.id,
                "title": f"{cita.cliente.nombre} - {cita.servicio.nombre}",
                "cliente": f"{cita.cliente.nombre} {cita.cliente.apellido}",
                "servicio": cita.servicio.nombre,
                "startDate": cita.fecha_inicio.isoformat(),
                "endDate": cita.fecha_fin.isoformat(),
                "estado": cita.estado,
            },
            status=201,
        )

    return JsonResponse({"error": "metodo no permitido"}, status=405)
