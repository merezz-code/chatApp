from django.urls import path
from . import views

urlpatterns = [
path('', views.welcome, name='welcome'),
    path('home', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    path('room/create/', views.create_room, name='create_room'),
    path('room/<str:room_name>/', views.room_detail, name='room_detail'),
    path("room/<str:room_name>/join/", views.join_room, name="join_room"),
    path('private/<str:username>/', views.private_chat, name='private_chat'),
    path('upload/', views.upload_file, name='upload_file'),
    path('chat/new/', views.choose_user_chat, name='choose_user_chat'),
    path('delete_private_message/<int:message_id>/', views.delete_private_message, name='delete_private_message'),
    path('delete_message/<int:message_id>/', views.delete_message, name='delete_message'),
]
