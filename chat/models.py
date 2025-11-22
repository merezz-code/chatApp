from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Room(models.Model):
    """Salon de discussion public ou privé"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_rooms')
    created_at = models.DateTimeField(auto_now_add=True)
    members = models.ManyToManyField(User, related_name='rooms', blank=True)

    # 🔥 Nouveau champ
    is_private = models.BooleanField(default=False)  # False = Public, True = Privé

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({'Privé' if self.is_private else 'Public'})"

    def get_online_count(self):
        return self.members.count()


class Message(models.Model):
    """Message dans un salon de discussion"""
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='messages')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='messages')
    content = models.TextField()
    image = models.ImageField(upload_to='chat_images/', blank=True, null=True)
    file = models.FileField(upload_to='chat_files/', blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['timestamp']
    
    def __str__(self):
        return f'{self.user.username}: {self.content[:50]}'


class PrivateMessage(models.Model):
    """Message privé entre deux utilisateurs"""
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages')
    content = models.TextField()
    image = models.ImageField(upload_to='private_images/', blank=True, null=True)
    file = models.FileField(upload_to='private_files/', blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['timestamp']
    
    def __str__(self):
        return f'{self.sender.username} to {self.receiver.username}: {self.content[:50]}'


class UserProfile(models.Model):
    """Profil utilisateur étendu"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    bio = models.TextField(blank=True, max_length=500)
    email = models.EmailField(blank=True, max_length=500)
    phone = models.CharField(blank=True, max_length=100)
    is_online = models.BooleanField(default=False)
    last_seen = models.DateTimeField(default=timezone.now)
    
    def __str__(self):
        return f'{self.user.username} Profile'

    def unread_private_count(self, other_user):
        """
        Retourne le nombre de messages non lus envoyés par other_user à self.user
        """
        return PrivateMessage.objects.filter(
            sender=other_user,
            receiver=self.user,
            is_read=False
        ).count()

    def is_blocking(self, other_user):
        """Vérifie si self.user bloque other_user"""
        from django.apps import apps
        Block = apps.get_model('chat', 'Block')
        return Block.objects.filter(blocker=self.user, blocked=other_user).exists()

    def is_blocked_by(self, other_user):
        """Vérifie si self.user est bloqué par other_user"""
        from django.apps import apps
        Block = apps.get_model('chat', 'Block')
        return Block.objects.filter(blocker=other_user, blocked=self.user).exists()

    def has_reported(self, other_user):
        """Vérifie si self.user a signalé other_user"""
        from django.apps import apps
        Report = apps.get_model('chat', 'Report')
        return Report.objects.filter(reporter=self.user, reported_user=other_user).exists()

    def should_hide_conversation(self, other_user):
        """
        Option 2: Cache la conversation si l'utilisateur a SIGNALÉ + BLOQUÉ
        """
        return self.is_blocking(other_user) and self.has_reported(other_user)


    def is_blocking(self, other_user):
        """Vérifie si self.user bloque other_user"""
        return Block.objects.filter(blocker=self.user, blocked=other_user).exists()

    def is_blocked_by(self, other_user):
        """Vérifie si self.user est bloqué par other_user"""
        return Block.objects.filter(blocker=other_user, blocked=self.user).exists()

    def has_reported(self, other_user):
        """Vérifie si self.user a signalé other_user"""
        return Report.objects.filter(reporter=self.user, reported_user=other_user).exists()

    def should_hide_conversation(self, other_user):
        """
        Option 2: Cache la conversation si l'utilisateur a SIGNALÉ + BLOQUÉ
        """
        return self.is_blocking(other_user) and self.has_reported(other_user)


class Block(models.Model):
    """
    Gestion des blocages entre utilisateurs
    Option 2: Bloquer = Conversation visible mais communication bloquée
    """
    blocker = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='blocking'
    )
    blocked = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='blocked_by'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('blocker', 'blocked')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.blocker.username} bloque {self.blocked.username}'


class Report(models.Model):
    """
    Signalement d'utilisateurs (action administrative)
    Signaler + Bloquer = Masque la conversation complètement
    """
    REASON_CHOICES = [
        ('spam', 'Spam ou publicité'),
        ('harassment', 'Harcèlement'),
        ('inappropriate', 'Contenu inapproprié'),
        ('fake', 'Faux profil'),
        ('other', 'Autre'),
    ]

    reporter = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='reports_made'
    )
    reported_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='reports_received'
    )
    reason = models.CharField(
        max_length=20,
        choices=REASON_CHOICES,
        default='other'
    )
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_resolved = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reporter.username} signale {self.reported_user.username} - {self.get_reason_display()}'