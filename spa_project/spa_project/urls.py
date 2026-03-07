
from django.contrib import admin
from django.urls import path
from session import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.index, name='home'),
    path('conocenos/', views.conocenos, name='conocenos'),
    path('servicios/', views.servicios, name='servicios'),
    path('compra/', views.compra, name='compra'),#productos
    path('login/', views.login_view, name='login'),
    path('registro/', views.registro, name='registro'),
    path('logout/', views.logout, name='logout'),
    path('administrador/dashboard/', views.dashboard, name='dashboard'),
    path('administrador/calendario/', views.calendario_view, name='calendario'),
    path('administrador/api/', views.api_calendar, name='api_calendar'),
    path('administrador/ventas/', views.ventas_view, name='ventas'),
    path('cliente/resultado/', views.resultado, name='resultado'),
    path('productosAdm/buscar/', views.buscar_producto, name='buscar_producto'),
    path('productosAdm/lista/', views.lista_productos, name='lista_productos'),
    path('productosAdm/nuevo/', views.crear_productos, name='crear_productos'),
    path('productosAdm/actualizar/<int:id>/', views.editar_producto, name='editar_producto'),
    path('productosElim/<int:id>/', views.eliminar_producto, name='eliminar_producto'),
    path('servicios/', views.servicios_lista, name='servicios_lista'),
    path('servicios/nuevo/', views.servicio_nuevo, name='servicio_nuevo'),
    path('servicios/detalle/<int:id>/', views.detalle_servicio, name='servicio_detalle'),
    path('servicios/actualizar/<int:id>/', views.servicio_actualizar, name='servicio_actualizar'),

]