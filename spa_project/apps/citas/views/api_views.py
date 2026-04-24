import json
from datetime import date

from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from apps.citas.models import Reserva, Servicio
from apps.citas.services import (
    INTERVALO_RESERVA_MINUTOS,
    crear_reserva,
    obtener_horas_disponibles_reserva,
    reservas_para_calendario,
)
from apps.sesiones.models import Usuario


def _usuario_actual(request):
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return None
    return Usuario.objects.filter(id=usuario_id).first()


def _evento_payload(reserva):
    pago = reserva.ultimo_pago_confirmado
    return {
        "id": reserva.id,
        "title": f"{reserva.cliente_nombre_completo} - {reserva.servicio.nombre}",
        "start": reserva.fecha_inicio,
        "end": reserva.fecha_fin,
        "extendedProps": {
            "cliente": reserva.cliente_nombre_completo,
            "servicio": reserva.servicio.nombre,
            "estado": reserva.estado,
            "profesional": reserva.profesional_reserva.nombre if reserva.profesional_reserva else "",
            "pagada": reserva.esta_pagada,
            "ultimo_pago": pago.numero_comprobante if pago else "",
            "origen": reserva.origen_reserva,
        },
    }


@csrf_exempt
def api_eventos(request):
    usuario = _usuario_actual(request)
    if not usuario:
        return JsonResponse({"error": "autenticacion requerida"}, status=401)

    if request.method == "GET":
        reservas = reservas_para_calendario(usuario)
        payload = [_evento_payload(reserva) for reserva in reservas]
        return JsonResponse(payload, safe=False, encoder=DjangoJSONEncoder)

    if request.method == "POST":
        try:
            body = json.loads(request.body or "{}")
            servicio = Servicio.objects.select_related("profesional").filter(
                id=body.get("servicio_id"), activo=True
            ).first()
            if not servicio:
                return JsonResponse({"error": "servicio_id invalido"}, status=400)

            fecha_inicio = body.get("start")
            if not fecha_inicio:
                return JsonResponse({"error": "start es obligatorio"}, status=400)
            fecha_inicio = timezone.datetime.fromisoformat(fecha_inicio.replace("Z", "+00:00"))
            if timezone.is_naive(fecha_inicio):
                fecha_inicio = timezone.make_aware(fecha_inicio, timezone.get_current_timezone())

            cliente = usuario
            if usuario.rol == Usuario.ROL_ADMIN and body.get("cliente_id"):
                cliente = Usuario.objects.filter(id=body.get("cliente_id")).first() or usuario

            reserva, _ = crear_reserva(
                cliente=cliente,
                servicio=servicio,
                fecha_inicio=fecha_inicio,
                notas=body.get("notas", ""),
                origen=Reserva.ORIGEN_ADMIN if usuario.rol == Usuario.ROL_ADMIN else Reserva.ORIGEN_AUTENTICADO,
                actor=usuario,
                pago_data=None,
            )
            return JsonResponse(_evento_payload(reserva), status=201, encoder=DjangoJSONEncoder)
        except ValidationError as exc:
            return JsonResponse({"error": exc.message if hasattr(exc, "message") else exc.messages[0]}, status=400)
        except ValueError:
            return JsonResponse({"error": "Fecha invalida"}, status=400)

    return JsonResponse({"error": "metodo no permitido"}, status=405)


def api_disponibilidad(request):
    if request.method != "GET":
        return JsonResponse({"error": "metodo no permitido"}, status=405)

    servicio_id = (request.GET.get("servicio_id") or "").strip()
    fecha_raw = (request.GET.get("fecha") or "").strip()
    exclude_reserva_raw = (request.GET.get("exclude_reserva_id") or "").strip()

    servicio = Servicio.objects.select_related("profesional").filter(id=servicio_id, activo=True).first()
    if not servicio:
        return JsonResponse({"error": "servicio_id invalido"}, status=400)
    if not fecha_raw:
        return JsonResponse({"error": "fecha es obligatoria"}, status=400)

    try:
        fecha_reserva = date.fromisoformat(fecha_raw)
    except ValueError:
        return JsonResponse({"error": "fecha invalida"}, status=400)

    try:
        exclude_reserva_id = int(exclude_reserva_raw) if exclude_reserva_raw else None
    except ValueError:
        return JsonResponse({"error": "exclude_reserva_id invalido"}, status=400)

    try:
        horas_disponibles = obtener_horas_disponibles_reserva(
            servicio=servicio,
            fecha_reserva=fecha_reserva,
            exclude_reserva_id=exclude_reserva_id,
        )
    except ValidationError as exc:
        return JsonResponse({"error": exc.message if hasattr(exc, "message") else exc.messages[0]}, status=400)

    return JsonResponse(
        {
            "fecha": fecha_reserva.isoformat(),
            "horas_disponibles": horas_disponibles,
            "intervalo_minutos": INTERVALO_RESERVA_MINUTOS,
            "profesional": servicio.profesional.nombre if servicio.profesional else "",
        }
    )
