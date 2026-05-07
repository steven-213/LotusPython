from apps.sesiones.session_utils import asegurar_vencimiento_sesion


class ManualSessionTimeoutMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        asegurar_vencimiento_sesion(request)
        return self.get_response(request)
