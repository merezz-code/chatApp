from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods
from .models import Room, Message, PrivateMessage, UserProfile
from .forms import RoomForm, MessageForm, PrivateMessageForm
from django.db.models import Q

from .models import Block, Report


def register(request):
    """Inscription d'un nouvel utilisateur"""
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            UserProfile.objects.create(user=user)
            login(request, user)
            messages.success(request, 'Inscription réussie! Bienvenue sur ChatApp!')
            return redirect('home')
    else:
        form = UserCreationForm()
    return render(request, 'chat/register.html', {'form': form})

def welcome(request):
    return render(request, 'chat/welcome.html')


def user_login(request):
    """Connexion utilisateur"""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            if hasattr(user, 'profile'):
                user.profile.is_online = True
                user.profile.save()
            return redirect('home')
        else:
            messages.error(request, 'Nom d\'utilisateur ou mot de passe incorrect')
    return render(request, 'chat/login.html')


@login_required
def user_logout(request):
    """Déconnexion utilisateur"""
    if hasattr(request.user, 'profile'):
        request.user.profile.is_online = False
        request.user.profile.save()
    logout(request)
    return redirect('login')

@login_required
def home(request):
    # Tous les salons existants
    rooms = Room.objects.all().order_by('-created_at')
    user_rooms = Room.objects.filter(
        Q(members = request.user )
    ).distinct().order_by('-created_at')

    # Tous les chats privés de l'utilisateur
    user_chats = User.objects.filter(id__in=[
        *PrivateMessage.objects.filter(sender=request.user).values_list('receiver_id', flat=True),
        *PrivateMessage.objects.filter(receiver=request.user).values_list('sender_id', flat=True)
    ]).distinct().exclude(id=request.user.id)

    # Utilisateurs disponibles pour commencer un chat
    users_not_chatted = User.objects.exclude(id=request.user.id)

    private_chats = []
    for user in user_chats:
        # NOUVEAU : Filtrer les conversations signalées + bloquées
        if request.user.profile.should_hide_conversation(user):
            continue  # Masquer complètement cette conversation

        unread_count = request.user.profile.unread_private_count(user)
        is_blocked = request.user.profile.is_blocking(user)

        private_chats.append({
            'user': user,
            'unread_count': unread_count,
            'is_blocked': is_blocked  # Afficher le badge "🚫 Bloqué"
        })

    context = {
        'rooms': rooms,
        'user_rooms': user_rooms,
        'private_chats': private_chats,
        'users_not_chatted': users_not_chatted,
    }
    return render(request, 'chat/home.html', context)



@login_required
def choose_user_chat(request):
    """Page pour choisir un utilisateur avec qui démarrer un chat privé"""
    # Récupérer les utilisateurs jamais contactés

    users_not_chatted = User.objects.exclude(id=request.user.id)
    return render(request, 'chat/choose_user_chat.html', {'users': users_not_chatted})

@login_required
def room_detail(request, room_name):
    room = Room.objects.filter(name__iexact=room_name).first()

    if request.user not in room.members.all():
        messages.error(request, "Vous n'êtes pas membre de ce salon.")
        return redirect('home')

    messages_list = room.messages.all().select_related('user')[:50]
    membre_contact = User.objects.exclude(id__in=room.members.all())
    members_list = room.members.all()

    return render(request, 'chat/room.html', {
        'room': room,
        'messages': messages_list,
        'membre_contact': membre_contact,
        'members_list': members_list,
    })


@login_required
def create_room(request):
    """Créer un nouveau salon de discussion"""
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        is_private = request.POST.get('is_private') == "1"  # 🔥 Nouveau champ

        if name:
            # Vérification de l'unicité du nom
            if not Room.objects.filter(name__iexact=name).exists():

                room = Room.objects.create(
                    name=name,
                    description=description,
                    created_by=request.user,
                    is_private=is_private  # 🔥 Enregistrer public/privé
                )

                # Ajouter le créateur dans les membres immédiatement
                room.members.add(request.user)

                messages.success(request, f'Salon "{name}" créé avec succès!')
                return redirect('room_detail', room_name=name)

            else:
                messages.error(request, 'Un salon avec ce nom existe déjà')

    return render(request, 'chat/create_room.html')


@login_required
def private_chat(request, username):
    other_user = get_object_or_404(User, username=username)

    # NOUVEAU : Vérifier le statut de blocage
    is_blocking = request.user.profile.is_blocking(other_user)
    is_blocked_by = request.user.profile.is_blocked_by(other_user)
    should_hide = request.user.profile.should_hide_conversation(other_user)

    # Si la conversation doit être masquée, rediriger
    if should_hide:
        messages.error(request, 'Cette conversation n\'est plus accessible.')
        return redirect('home')

    messages_sent = PrivateMessage.objects.filter(
        sender=request.user,
        receiver=other_user
    )
    messages_received = PrivateMessage.objects.filter(
        sender=other_user,
        receiver=request.user
    )

    all_messages = sorted(
        list(messages_sent) + list(messages_received),
        key=lambda x: x.timestamp
    )

    messages_received.filter(is_read=False).update(is_read=True)

    return render(request, 'chat/private_chat.html', {
        'other_user': other_user,
        'messages': all_messages,
        'is_blocking': is_blocking,
        'is_blocked_by': is_blocked_by
    })

@login_required
@require_POST
def upload_file(request):
    file = request.FILES.get('file')
    if not file:
        return JsonResponse({'status': 'error', 'message': 'Aucun fichier'}, status=400)

    # === Si c'est un groupe ===
    room_name = request.POST.get('room')
    if room_name:
        room = Room.objects.filter(name__iexact=room_name).first()
        if not room:
            return JsonResponse({'status': 'error', 'message': 'Salon introuvable'}, status=404)
        # Crée le message pour le groupe
        if file.content_type.startswith('image/'):
            message = Message.objects.create(room=room, user=request.user,
                                             content=f'Image partagée: {file.name}', image=file)
        else:
            message = Message.objects.create(room=room, user=request.user,
                                             content=f'Fichier partagé: {file.name}', file=file)
        return JsonResponse({'status': 'success', 'message': 'Fichier uploadé',
                             'file_url': message.file.url if message.file else '',
                             'image_url': message.image.url if message.image else ''})

    # === Si c'est un chat privé ===
    receiver_username = request.POST.get('receiver_username')
    if receiver_username:
        try:
            receiver = User.objects.get(username=receiver_username)
        except User.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Utilisateur introuvable'}, status=404)

        # Crée le message pour le chat privé
        if file.content_type.startswith('image/'):
            message = PrivateMessage.objects.create(sender=request.user, receiver=receiver,
                                                    content=f'Image partagée: {file.name}', image=file)
        else:
            message = PrivateMessage.objects.create(sender=request.user, receiver=receiver,
                                                    content=f'Fichier partagé: {file.name}', file=file)
        return JsonResponse({'status': 'success', 'message': 'Fichier uploadé',
                             'file_url': message.file.url if message.file else '',
                             'image_url': message.image.url if message.image else ''})

    return JsonResponse({'status': 'error', 'message': 'Paramètre manquant'}, status=400)


@login_required
def delete_private_message(request, message_id):
    """
    Supprime un message privé si l'utilisateur est le propriétaire (sender).
    Reste sur la page du chat après suppression.
    """
    message_obj = get_object_or_404(PrivateMessage, id=message_id)

    # Vérifier que l'utilisateur est le propriétaire
    if message_obj.sender == request.user:
        message_obj.delete()

    # Reste sur la page du chat avec l'autre utilisateur
    return redirect('private_chat', username=message_obj.receiver.username)

@login_required
def delete_message(request, message_id):

    message_obj = get_object_or_404(Message, id=message_id)
    if message_obj.user == request.user:
        message_obj.delete()

    return redirect('room_detail', room_name=message_obj.room.name)
@login_required
def join_room(request, room_name):
    room = get_object_or_404(Room, name=room_name)

    if room.is_private:
        messages.error(request, "Ce salon est privé.")
    else:
        room.members.add(request.user)
        messages.success(request, f"Vous avez rejoint le salon {room_name} !")


    return redirect('room_detail', room_name=room_name)



# Ajoutez ces vues À LA FIN de views.py


@login_required
@require_POST
def block_user(request, username):
    """
    Bloque un utilisateur (Option 2)
    - Conversation reste visible avec badge "🚫 Bloqué"
    - Empêche l'envoi de messages
    - Notifie l'utilisateur bloqué
    """
    try:
        user_to_block = User.objects.get(username=username)

        # Empêcher de se bloquer soi-même
        if user_to_block == request.user:
            return JsonResponse({
                'status': 'error',
                'message': 'Vous ne pouvez pas vous bloquer vous-même'
            }, status=400)

        # Créer ou récupérer le blocage
        block, created = Block.objects.get_or_create(
            blocker=request.user,
            blocked=user_to_block
        )

        if created:
            return JsonResponse({
                'status': 'success',
                'message': f'{username} a été bloqué',
                'blocked': True
            })
        else:
            return JsonResponse({
                'status': 'info',
                'message': f'{username} est déjà bloqué',
                'blocked': True
            })

    except User.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Utilisateur introuvable'
        }, status=404)


@login_required
@require_POST
def unblock_user(request, username):
    """
    Débloque un utilisateur
    - Restaure la communication normale
    """
    try:
        user_to_unblock = User.objects.get(username=username)

        # Supprimer le blocage
        deleted_count = Block.objects.filter(
            blocker=request.user,
            blocked=user_to_unblock
        ).delete()[0]

        if deleted_count > 0:
            return JsonResponse({
                'status': 'success',
                'message': f'{username} a été débloqué',
                'blocked': False
            })
        else:
            return JsonResponse({
                'status': 'info',
                'message': f'{username} n\'était pas bloqué',
                'blocked': False
            })

    except User.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Utilisateur introuvable'
        }, status=404)


@login_required
@require_POST
def report_user(request, username):
    """
    Signale un utilisateur (action administrative)
    Si combiné avec blocage → masque la conversation complètement
    """
    try:
        user_to_report = User.objects.get(username=username)

        # Empêcher de se signaler soi-même
        if user_to_report == request.user:
            return JsonResponse({
                'status': 'error',
                'message': 'Vous ne pouvez pas vous signaler vous-même'
            }, status=400)

        # Récupérer la raison et description
        reason = request.POST.get('reason', 'other')
        description = request.POST.get('description', '')

        # Créer le signalement
        report, created = Report.objects.get_or_create(
            reporter=request.user,
            reported_user=user_to_report,
            defaults={
                'reason': reason,
                'description': description
            }
        )

        if created:
            return JsonResponse({
                'status': 'success',
                'message': f'{username} a été signalé',
                'reported': True
            })
        else:
            return JsonResponse({
                'status': 'info',
                'message': f'{username} a déjà été signalé',
                'reported': True
            })

    except User.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Utilisateur introuvable'
        }, status=404)


@login_required
@require_POST
def report_and_block_user(request, username):
    """
    Signale ET bloque un utilisateur en une seule action
    → Masque complètement la conversation (Option 2)
    """
    try:
        user_to_report = User.objects.get(username=username)

        if user_to_report == request.user:
            return JsonResponse({
                'status': 'error',
                'message': 'Action impossible'
            }, status=400)

        # Récupérer la raison
        reason = request.POST.get('reason', 'other')
        description = request.POST.get('description', '')

        # Créer le signalement
        Report.objects.get_or_create(
            reporter=request.user,
            reported_user=user_to_report,
            defaults={
                'reason': reason,
                'description': description
            }
        )

        # Créer le blocage
        Block.objects.get_or_create(
            blocker=request.user,
            blocked=user_to_report
        )

        return JsonResponse({
            'status': 'success',
            'message': f'{username} a été signalé et bloqué. La conversation est masquée.',
            'blocked': True,
            'reported': True,
            'hidden': True
        })

    except User.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Utilisateur introuvable'
        }, status=404)


@login_required
def check_block_status(request, username):
    """
    Vérifie le statut de blocage avec un utilisateur
    Utilisé pour l'UI dynamique
    """
    try:
        other_user = User.objects.get(username=username)

        is_blocking = request.user.profile.is_blocking(other_user)
        is_blocked_by = request.user.profile.is_blocked_by(other_user)
        has_reported = request.user.profile.has_reported(other_user)
        should_hide = request.user.profile.should_hide_conversation(other_user)

        return JsonResponse({
            'status': 'success',
            'is_blocking': is_blocking,
            'is_blocked_by': is_blocked_by,
            'has_reported': has_reported,
            'should_hide': should_hide
        })

    except User.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Utilisateur introuvable'
        }, status=404)
