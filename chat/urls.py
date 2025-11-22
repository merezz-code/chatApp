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

    # Bloquer un utilisateur
    path('block/<str:username>/', views.block_user, name='block_user'),
    path('unblock/<str:username>/', views.unblock_user, name='unblock_user'),
    # Signaler un utilisateur
    path('report/<str:username>/', views.report_user, name='report_user'),
    # Signaler + Bloquer (masque la conversation)
    path('report-and-block/<str:username>/', views.report_and_block_user, name='report_and_block_user'),
    # Vérifier le statut de blocage (API)
    path('check-block-status/<str:username>/', views.check_block_status, name='check_block_status'),
    path('profile/update/', views.update_profile, name='update_profile'),

]
