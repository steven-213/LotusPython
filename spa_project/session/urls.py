
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
    path('productosAdm/lista/', views.productos, name='lista'),
    path('productosAdm/buscar/', views.buscar_producto, name='buscar_producto'),
    path('productosAdm/nuevo/', views.nuevo_producto, name='nuevo'),
    path('productosAdm/actualizar/<int:id>/', views.actualizar_producto, name='actualizar'),
    path('servicios/', views.servicios_lista, name='servicios_lista'),
    path('servicios/nuevo/', views.servicio_nuevo, name='servicio_nuevo'),
    path('servicios/detalle/<int:id>/', views.detalle_servicio, name='servicio_detalle'),
    path('servicios/actualizar/<int:id>/', views.servicio_actualizar, name='servicio_actualizar'),

]