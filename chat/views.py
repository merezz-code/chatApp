from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .models import Room, Message, PrivateMessage, UserProfile
from .forms import RoomForm, MessageForm, PrivateMessageForm


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
        members = request.user
    ).distinct().order_by('-created_at')

    # Tous les chats privés de l'utilisateur (exemple si tu as une relation)
    # Ici, on prend les utilisateurs avec qui il a déjà discuté
    user_chats = User.objects.filter( id__in=[
        *PrivateMessage.objects.filter(sender=request.user).values_list('receiver_id', flat=True),
        *PrivateMessage.objects.filter(receiver=request.user).values_list('sender_id', flat=True) ] ).distinct().exclude(id=request.user.id)

    # Utilisateurs disponibles pour commencer un chat (pas encore dans les chats privés)
    users_not_chatted = User.objects.exclude(id=request.user.id)

    context = {
        'rooms': rooms,
        'user_rooms': user_rooms,
        'private_chats': user_chats,
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
        if name:
            if not Room.objects.filter(name__iexact=name).exists():
                room = Room.objects.create(
                    name=name,
                    description=description,
                    created_by=request.user
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
    """Discussion privée avec un autre utilisateur"""
    other_user = get_object_or_404(User, username=username)
    
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
        'messages': all_messages
    })


@login_required
@require_POST
def upload_file(request):
    """Upload de fichier ou image via AJAX"""
    if request.FILES.get('file'):
        room_name = request.POST.get('room')
        file = request.FILES['file']
        
        if room_name:
            room = Room.objects.filter(name__iexact=room_name).first()
            if file.content_type.startswith('image/'):
                message = Message.objects.create(
                    room=room,
                    user=request.user,
                    content=f'Image partagée: {file.name}',
                    image=file
                )
            else:
                message = Message.objects.create(
                    room=room,
                    user=request.user,
                    content=f'Fichier partagé: {file.name}',
                    file=file
                )
            return JsonResponse({
                'status': 'success',
                'message': 'Fichier uploadé avec succès'
            })
    
    return JsonResponse({
        'status': 'error',
        'message': 'Erreur lors de l\'upload'
    }, status=400)
