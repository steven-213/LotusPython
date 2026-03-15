from django.shortcuts import render

from apps.sesiones.decorators import login_required_session
from apps.sesiones.models import Usuario
from apps.ventas.models import ValidacionVenta


@login_required_session
def perfil(request):
    usuario = Usuario.objects.filter(id=request.session.get("usuario_id")).first()
    validaciones = (
        ValidacionVenta.objects.select_related("venta")
        .prefetch_related("venta__detalles__producto")
        .filter(cliente_id=request.session.get("usuario_id"))
        .order_by("-fecha_validacion")
    )
    # Filtrar SOLO los estados que realmente importan, ignorar valores incorrectos
    compras_pendientes = validaciones.filter(estado__iexact="pendiente")
    compras_compradas = validaciones.filter(estado__iexact="comprado")
    compras_rechazadas = validaciones.filter(estado__iexact="rechazado")
    
    return render(
        request,
        "sesiones/perfil.html",
        {
            "usuario": usuario,
            "compras_pendientes": compras_pendientes,
            "compras_compradas": compras_compradas,
            "compras_rechazadas": compras_rechazadas,
        },
    )
