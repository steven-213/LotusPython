from django.contrib import admin
from django.urls import path
from django.shortcuts import redirect
from . import views


def home(request):
    return redirect('login')

urlpatterns = [
    path('', home),
    path('admin/', admin.site.urls),
    path('login/', views.login, name='login'),
]