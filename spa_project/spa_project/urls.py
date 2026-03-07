
from django.contrib import admin
from django.urls import path
from session import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.index, name='home'),
    path('conocenos/', views.conocenos, name='conocenos'),
    path('servicios/', views.servicios, name='servicios'),
    path('compra/', views.compra, name='compra'),
    path('login/', views.login_view, name='login'),
    path('registro/', views.registro, name='registro'),
    path('logout/', views.logout, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('resultado/', views.resultado, name='resultado'),
    path("lista/", views.productos, name="lista"),
    path("productosAdm/nuevo/", views.nuevo_producto, name="nuevo"),
    path("productosAdm/actualizar/<int:id>/", views.actualizar_producto, name="actualizar"),
    path("imagenes/", views.imagenes, name="imagenes"),
]