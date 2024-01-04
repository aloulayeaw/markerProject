from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('upload/', views.overlay_photos, name='overlay_photos'),
    path('contact/', views.contact, name='contact'),
]
