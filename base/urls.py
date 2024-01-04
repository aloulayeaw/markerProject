from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', views.home, name='home'),
    path('upload/', views.overlay_photos, name='overlay_photos'),
    path('contact/', views.contact, name='contact'),
]+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)