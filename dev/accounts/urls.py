from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('profile/', views.profile, name='profile'),
    path('preferences/', views.edit_preferences, name='edit_preferences'),
]
