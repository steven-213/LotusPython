from django.urls import path
from . import views

urlpatterns = [

    path('', views.index, name='home'),

    path('conocenos/', views.conocenos, name='conocenos'),

    path('servicios/', views.servicios, name='servicios'),

    path('compra/', views.compra, name='compra'),

    path('login/', views.login_view, name='login'),

    path('registro/', views.registro, name='registro'),

    path('logout/', views.logout_view, name='logout'),

    path('dashboard/', views.dashboard, name='dashboard'),

]