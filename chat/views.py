from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_http_methods
from .models import Room, Message, PrivateMessage, UserProfile, Block, Report, HiddenConversation, MessageRead
from .forms import UserProfileForm
from django.db.models import Q, Max
from django.utils import timezone




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
    # -------------------------
    # Salons (Rooms)
    # -------------------------
    user_rooms = Room.objects.filter(members=request.user).distinct()

    # Ajouter le timestamp du dernier message dans chaque room
    user_rooms = user_rooms.annotate(
        last_message_time=Max('messages__timestamp')
    ).order_by('-last_message_time')  # trie par dernier message reçu/envoi

    # Préparer rooms_data pour les messages non lus
    rooms_data = []
    for room in user_rooms:
        unread_count = room.unread_count_for_user(request.user)
        rooms_data.append({
            'id': room.id,
            'name': room.name,
            'unread_count': unread_count
        })

    # -------------------------
    # Chats privés
    # -------------------------
    # Récupérer tous les utilisateurs avec qui il y a eu un échange
    user_chats = User.objects.filter(
        id__in=[
            *PrivateMessage.objects.filter(sender=request.user).values_list('receiver_id', flat=True),
            *PrivateMessage.objects.filter(receiver=request.user).values_list('sender_id', flat=True)
        ]
    ).distinct().exclude(id=request.user.id)

    private_chats = []
    for user in user_chats:
        if not request.user.profile.should_hide_conversation(user):
            unread_count = request.user.profile.unread_private_count(user)

            # Récupérer le dernier message entre les deux
            last_msg = PrivateMessage.objects.filter(
                Q(sender=request.user, receiver=user) | Q(sender=user, receiver=request.user)
            ).order_by('-timestamp').first()

            private_chats.append({
                'user': user,
                'unread_count': unread_count,
                'last_message_time': last_msg.timestamp if last_msg else None
            })

    # Trier les chats privés par dernier message
    private_chats.sort(key=lambda x: x['last_message_time'] or 0, reverse=True)

    # -------------------------
    # Tous les salons disponibles (pour modal)
    # -------------------------
    rooms = Room.objects.all().order_by('-created_at')
    users_not_chatted = User.objects.exclude(id=request.user.id)

    context = {
        'rooms': rooms,
        'user_rooms': user_rooms,
        'rooms_data': rooms_data,
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
    hidden = HiddenConversation.objects.filter(user=request.user, room=room).first()

    # Récupération des messages
    if hidden:
        messages_list = list(
            Message.objects.filter(room=room, timestamp__gt=hidden.hidden_at)
            .order_by('timestamp')  # ordre normal
        )
    else:
        messages_list = list(Message.objects.filter(room=room).order_by('timestamp'))

    # Marquer comme lus
    for msg in messages_list:
        MessageRead.objects.get_or_create(message=msg, user=request.user)

    # -----------------------------
    # Liste des membres actuels
    # -----------------------------
    members_list = room.members.all()

    # -----------------------------
    # Liste des utilisateurs non membres (disponibles à ajouter)
    # -----------------------------
    # Exclut les membres existants + l'utilisateur actuel
    membre_contact = User.objects.exclude(id__in=members_list.values_list('id', flat=True))\
                                 .exclude(id=request.user.id)

    context = {
        'room': room,
        'messages': messages_list,
        'members_list': members_list,
        'membre_contact': membre_contact,  # pour modal "Ajouter membre"
    }

    return render(request, 'chat/room.html', context)



@login_required
def create_room(request):
    """Créer un nouveau salon de discussion"""
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        is_private = request.POST.get('is_private') == "1"

        if name:
            # Vérification de l'unicité du nom
            if not Room.objects.filter(name__iexact=name).exists():

                room = Room.objects.create(
                    name=name,
                    description=description,
                    created_by=request.user,
                    is_private=is_private
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
    profile = request.user.profile
    is_blocking = profile.is_blocking(other_user)
    is_blocked_by = profile.is_blocked_by(other_user)
    has_reported = profile.has_reported(other_user)
    should_hide = profile.should_hide_conversation(other_user)

    if should_hide:
        messages.warning(request, f'Cette conversation avec {username} a été masquée.')
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

    context = {
        'other_user': other_user,
        'messages': all_messages,
        'is_blocking': is_blocking,
        'is_blocked_by': is_blocked_by,
        'has_reported': has_reported,
        'should_hide': should_hide
    }

    print(f"  Context: {context}")  # Debug du contexte

    return render(request, 'chat/private_chat.html', context)

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

    # Si c'est un chat privé
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


@login_required
@require_POST
def block_user(request, username):
    """
    Bloque un utilisateur
    """
    try:
        user_to_block = get_object_or_404(User, username=username)

        # Vérification: impossible de se bloquer soi-même
        if user_to_block == request.user:
            return JsonResponse({
                'success': False,
                'error': 'Vous ne pouvez pas vous bloquer vous-même'
            }, status=400)

        block, created = Block.objects.get_or_create(
            blocker=request.user,
            blocked=user_to_block
        )

        if created:
            return JsonResponse({
                'success': True,
                'message': f'{username} a été bloqué',
                'blocked_user': username
            })
        else:
            return JsonResponse({
                'success': False,
                'error': f'{username} est déjà bloqué'
            }, status=400)

    except User.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Utilisateur introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_POST
def unblock_user(request, username):
    """
    Débloque un utilisateur
    """
    try:
        user_to_unblock = get_object_or_404(User, username=username)

        # Supprimer le blocage
        deleted_count, _ = Block.objects.filter(
            blocker=request.user,
            blocked=user_to_unblock
        ).delete()

        if deleted_count > 0:
            return JsonResponse({
                'success': True,
                'message': f'{username} a été débloqué',
                'unblocked_user': username
            })
        else:
            return JsonResponse({
                'success': False,
                'error': f'{username} n\'était pas bloqué'
            }, status=400)

    except User.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Utilisateur introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_POST
def report_user(request, username):
    """
    Signale un utilisateur
    """
    try:
        user_to_report = get_object_or_404(User, username=username)

        # Vérification: impossible de se signaler soi-même
        if user_to_report == request.user:
            return JsonResponse({
                'success': False,
                'error': 'Vous ne pouvez pas vous signaler vous-même'
            }, status=400)

        # Récupérer les données du formulaire
        reason = request.POST.get('reason', 'other')
        description = request.POST.get('description', '').strip()

        # Vérifier si déjà signalé
        existing_report = Report.objects.filter(
            reporter=request.user,
            reported_user=user_to_report
        ).first()

        if existing_report:
            return JsonResponse({
                'success': False,
                'error': f'{username} a déjà été signalé'
            }, status=400)

        # Créer le signalement
        report = Report.objects.create(
            reporter=request.user,
            reported_user=user_to_report,
            reason=reason,
            description=description
        )

        return JsonResponse({
            'success': True,
            'message': f'{username} a été signalé aux administrateurs',
            'report_id': report.id
        })

    except User.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Utilisateur introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
@require_POST
def report_and_block_user(request, username):
    """
    Signale ET bloque un utilisateur
    """
    try:
        user_to_report_and_block = get_object_or_404(User, username=username)

        if user_to_report_and_block == request.user:
            return JsonResponse({
                'success': False,
                'error': 'Action impossible'
            }, status=400)

        reason = request.POST.get('reason', 'other')
        description = request.POST.get('description', '').strip()

        report, report_created = Report.objects.get_or_create(
            reporter=request.user,
            reported_user=user_to_report_and_block,
            defaults={
                'reason': reason,
                'description': description
            }
        )

        block, block_created = Block.objects.get_or_create(
            blocker=request.user,
            blocked=user_to_report_and_block
        )

        return JsonResponse({
            'success': True,
            'message': f'{username} a été signalé et bloqué. La conversation est maintenant masquée.',
            'action': 'report_and_block',
            'hidden': True  # Indique que la conversation doit disparaître
        })

    except User.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Utilisateur introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# VÉRIFIER LE STATUT DE BLOCAGE (API)
@login_required
def check_block_status(request, username):
    """
    API pour vérifier le statut de blocage avec un utilisateur
    Retourne JSON avec toutes les informations nécessaires
    """
    try:
        other_user = get_object_or_404(User, username=username)
        profile = request.user.profile

        # Récupérer les statuts
        is_blocking = profile.is_blocking(other_user)
        is_blocked_by = profile.is_blocked_by(other_user)
        has_reported = profile.has_reported(other_user)
        should_hide = profile.should_hide_conversation(other_user)

        return JsonResponse({
            'success': True,
            'username': username,
            'is_blocking': is_blocking,
            'is_blocked_by': is_blocked_by,
            'has_reported': has_reported,
            'should_hide_conversation': should_hide,
            'can_send_messages': not (is_blocking or is_blocked_by)
        })

    except User.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Utilisateur introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
def update_profile(request):
    profile = request.user.profile

    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            return redirect('/home')
    else:
        form = UserProfileForm(instance=profile)
    return render(request, 'base.html', {'form': form, 'user': request.user})

@require_POST
@login_required
def hide_conversation(request, room_id):
    room = get_object_or_404(Room, id=room_id)
    hidden, created = HiddenConversation.objects.update_or_create(
        user=request.user,
        room=room,
        defaults={"hidden_at": timezone.now()}
    )
    return JsonResponse({"success": True})



@login_required
def private_unread_count(request):
    user = request.user
    chats = []

    user_chats = User.objects.filter(
        id__in=[
            *PrivateMessage.objects.filter(sender=user).values_list('receiver_id', flat=True),
            *PrivateMessage.objects.filter(receiver=user).values_list('sender_id', flat=True)
        ]
    ).distinct().exclude(id=user.id)

    for u in user_chats:
        unread_count = PrivateMessage.objects.filter(
            sender=u,
            receiver=user,
            is_read=False
        ).count()
        chats.append({
            'id': u.id,
            'username': u.username,
            'unread_count': unread_count
        })

    return JsonResponse({'private_chats': chats})


from django.http import JsonResponse
from .models import Room, Message


def rooms_unread_count(request):
    user = request.user
    rooms_data = []

    # Récupérer tous les salons que l'utilisateur peut voir
    rooms = Room.objects.all()  # ou selon ton filtre (par ex: user.rooms.all())
    for room in rooms:
        # Compter uniquement les messages non lus pour cet utilisateur
        rooms_data.append({
            "id": room.id,
            "name": room.name,
            "unread_count": room.unread_count_for_user(user)
        })

    return JsonResponse({"rooms": rooms_data})


@login_required
@require_http_methods(["DELETE"])
def delete_private_chat(request, user_id):
    try:
        other_user = User.objects.get(id=user_id)

        # Supprimer tous les messages dans les deux sens
        PrivateMessage.objects.filter(
            sender=request.user,
            receiver=other_user
        ).delete()

        PrivateMessage.objects.filter(
            sender=other_user,
            receiver=request.user
        ).delete()

        return JsonResponse({"status": "success"})

    except User.DoesNotExist:
        return JsonResponse({"status": "error", "message": "Utilisateur introuvable"}, status=404)

@login_required
def private_unread_count(request):
    user = request.user
    data = []
    private_chats = PrivateMessage.objects.filter(receiver=user).select_related("sender")

    unread_map = {}
    for msg in private_chats.filter(is_read=False):
        unread_map[msg.sender.id] = unread_map.get(msg.sender.id, 0) + 1

    for user_id, count in unread_map.items():
        data.append({"user_id": user_id, "count": count})

    return JsonResponse({"private_unread": data})

