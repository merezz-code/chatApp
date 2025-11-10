from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    path('room/create/', views.create_room, name='create_room'),
    path('room/<str:room_name>/', views.room_detail, name='room_detail'),
    path('private/<str:username>/', views.private_chat, name='private_chat'),
    path('upload/', views.upload_file, name='upload_file'),
    path('chat/new/', views.choose_user_chat, name='choose_user_chat')
]
