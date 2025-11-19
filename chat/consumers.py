import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils.text import slugify
from django.contrib.auth.models import User
from .models import Room, Message, PrivateMessage, Block
from django.utils.text import slugify


class ChatConsumer(AsyncWebsocketConsumer):
    """
    Consumer minimal pour room avec suppression persistante et broadcast.
    """

    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        safe_room_name = slugify(self.room_name)
        self.room_group_name = f'chat_{safe_room_name}'
        self.user = self.scope['user']

        if not self.user.is_authenticated:
            await self.close()
            return

        # Récupérer la room (optionnel : on suppose qu'elle existe)
        self.room = await self.get_room()
        if self.room is None:
            await self.close()
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        members_data = await self.get_members_list_data()
        # envoie le message de bienvenue
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'members_update',
                'message': f'{self.user.username} a rejoint le salon',
                'members_data': members_data
            }
        )

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            members_data = await self.get_members_list_data()
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'members_update',
                    'message': f'{self.user.username} a quitté le salon',
                    'members_data': members_data
                }
            )

            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        """
        Attendu: messages JSON avec clé 'action'.
        - {'action':'message', 'message': '...'}
        - {'action':'delete_message', 'message_id': 123}
        """
        try:
            data = json.loads(text_data)
        except Exception as e:
            # message mal formé
            await self.send(text_data=json.dumps({'type':'error','message':'invalid json'}))
            return

        action = data.get('action')

        if action == 'message':
            message_content = data.get('message', '').strip()
            if message_content:
                msg_obj = await self._create_message(message_content)
                # broadcast nouveau message
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_message',
                        'id': msg_obj.id,
                        'username': self.user.username,
                        'message': msg_obj.content,
                        'timestamp': msg_obj.timestamp.strftime("%H:%M")
                    }
                )

        elif action == 'remove_member':
            target_username = data.get('username')
            if self.user != self.room.created_by:
                # Si l'utilisateur n'est PAS l'admin
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': "Vous n'avez pas la permission de retirer un membre."
                }))
                # On arrête l'exécution de la fonction ici
                return

            if target_username:
                if target_username == self.user.username:
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': "L'administrateur ne peut pas se retirer lui-même."
                    }))
                    return
                success, removed_username = await self.remove_user_from_room_by_username(target_username)
                if success:
                    members_data = await self.get_members_list_data()
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'members_update',
                            'message': f"{removed_username} a été retiré du salon par {self.user.username}.",
                            'username_removed': removed_username,
                            'members_data': members_data
                        }
                    )

                else:
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': f"Impossible de retirer l'utilisateur {target_username}."
                    }))

        elif action == 'add_member':
            target_username = data.get('username')

            if self.user != self.room.created_by:
                # Si l'utilisateur n'est PAS l'admin
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': "Vous n'avez pas la permission d'ajouter un membre."
                }))
                # On arrête l'exécution de la fonction ici
                return

            if target_username:
                success, added_username = await self.add_user_to_room_by_username(target_username)

                if success:
                    # Envoyer la mise à jour à tout le monde
                    members_data = await self.get_members_list_data()
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'members_update',
                            'message': f"{added_username} a été ajouté au salon par {self.user.username}.",
                            'members_data': members_data
                        }
                    )
                else:
                    # Envoyer une erreur (ex: utilisateur n'existe pas, ou déjà membre)
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': f"Impossible d'ajouter l'utilisateur {target_username}."
                    }))

        elif action == 'leave_group':

            if self.user == self.room.created_by:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': "L'administrateur ne peut pas quitter le groupe. Vous devez d'abord le supprimer ou transférer la propriété."
                }))
                return

            # Retirer l'utilisateur (self.user) de la DB
            await self.remove_user_from_room()

            # Obtenir la nouvelle liste de membres
            members_data = await self.get_members_list_data()

            # Envoyer la mise à jour à tous les AUTRES membres
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'members_update',
                    'message': f"{self.user.username} a quitté le salon.",
                    'members_data': members_data
                }
            )


            # Envoyer un message juste à l'utilisateur qui part
            # pour lui dire de se rediriger
            await self.send(text_data=json.dumps({
                'type': 'group_left_you',
                'message': f"Vous avez quitté le salon '{self.room_name}'."
            }))
        elif action == 'delete_message':
            message_id = data.get('message_id')
            if not message_id:
                await self.send(text_data=json.dumps({'type': 'error', 'message': 'missing message_id'}))
                return

            # Récupérer le message et vérifier propriétaire
            msg = await self._get_message_by_id(message_id)
            if msg is None:
                await self.send(text_data=json.dumps({'type': 'error', 'message': 'message not found'}))
                return

            if msg.user_id != self.user.id:
                await self.send(text_data=json.dumps({'type': 'error', 'message': 'not allowed'}))
                return

            # Supprimer en base
            await self._delete_message_by_id(message_id)

            # Broadcast suppression à tout le groupe
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'delete_message_event',
                    'message_id': message_id
                }
            )



    # event handlers (broadcast)
    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message',
            'id': event['id'],
            'username': event['username'],
            'message': event['message'],
            'timestamp': event['timestamp']
        }))
    async def members_update(self, event):
        """
            Envoie la mise à jour de la liste des membres et le message au client.
        """
        await self.send(text_data=json.dumps({
            'type': 'members_update',
            'id': event.get('id'),
            'message': event.get('message'),
            'username_removed': event.get('username_removed'),
            'members_data': event.get('members_data')
        }))

    async def delete_message_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'delete_message',
            'message_id': event['message_id']
        }))

    # ---------- DB helpers (sync -> async wrapper) ----------
    @database_sync_to_async
    def get_room(self):
        """
        Récupère le salon en ignorant la casse.
        """
        return Room.objects.select_related('created_by').filter(name__iexact=self.room_name).first()

    @database_sync_to_async
    def get_members_list_data(self):
        """
        Récupère la liste des membres actuels et le compte.
        """
        if not self.room:
            return {'count': 0, 'members': []}

        # .all() est paresseux, il faut l'évaluer dans un contexte sync
        # En le passant dans list(), on force l'évaluation
        members = list(self.room.members.all())

        return {
            'count': len(members),
            'members': [{'username': member.username} for member in members]
        }

    @database_sync_to_async
    def save_message(self, message_content):
        """
        Utilise self.room (défini dans connect)
        """
        if self.room:
            Message.objects.create(
                room=self.room,
                user=self.user,
                content=message_content
            )

    @database_sync_to_async
    def add_user_to_room(self):
        if self.room:
            self.room.members.add(self.user)

    @database_sync_to_async
    def remove_user_from_room(self):
        if self.room:
            self.room.members.remove(self.user)

    @database_sync_to_async
    def remove_user_from_room_by_username(self, target_username):
        """
        Retire un utilisateur spécifique (par username) du salon.
        Utilisé par un admin/modérateur pour retirer quelqu'un d'autre.
        """
        if not self.room:
            return False, None
        try:
            user_to_remove = User.objects.get(username=target_username)
            if user_to_remove in self.room.members.all():
                self.room.members.remove(user_to_remove)

                print(f"SUCCÈS: {user_to_remove.username} retiré de {self.room.name}")
                return True, target_username
            else:
                print(f"ERREUR: {target_username} n'est pas dans le salon.")
                return False, None
        except User.DoesNotExist:
            print(f"ERREUR: Utilisateur {target_username} n'existe pas.")
            return False, None

    @database_sync_to_async
    def add_user_to_room_by_username(self, target_username):
        """
            Ajoute un utilisateur spécifique (par username) au salon.
        """
        if not self.room:
            return False, None
        try:
            user_to_add = User.objects.get(username=target_username)
            if user_to_add not in self.room.members.all():
                self.room.members.add(user_to_add)
                print(f"SUCCÈS: {user_to_add.username} ajouté à {self.room.name}")
                return True, target_username
            else:
                print(f"INFO: {target_username} est déjà dans le salon.")
                return False, None
        except User.DoesNotExist:
            print(f"ERREUR: Utilisateur {target_username} n'existe pas.")
            return False, None

    def get_current_timestamp(self):
        from datetime import datetime
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    @database_sync_to_async
    def _create_message(self, content):
        return Message.objects.create(room=self.room, user=self.user, content=content)

    @database_sync_to_async
    def _get_message_by_id(self, message_id):
        try:
            # s'assure que le message appartient à la même room
            return Message.objects.get(id=message_id, room=self.room)
        except Message.DoesNotExist:
            return None

    @database_sync_to_async
    def _delete_message_by_id(self, message_id):
        Message.objects.filter(id=message_id, room=self.room).delete()



class PrivateChatConsumer(AsyncWebsocketConsumer):
    """Consumer pour les messages privés avec gestion du blocage"""

    async def connect(self):
        self.user = self.scope['user']
        self.other_username = self.scope['url_route']['kwargs']['username']
        
        if not self.user.is_authenticated:
            await self.close()
            return

        # Vérifier si l'autre utilisateur existe
        self.other_user = await self.get_other_user()
        if not self.other_user:
            await self.close()
            return

        users = sorted([self.user.username, self.other_username])
        self.room_name = f'private_{users[0]}_{users[1]}'

        await self.channel_layer.group_add(self.room_name, self.channel_name)
        await self.accept()


        # Envoyer le statut de blocage au client
        block_status = await self.check_block_status()
        await self.send(text_data=json.dumps({
            'type': 'block_status',
            'is_blocking': block_status['is_blocking'],
            'is_blocked_by': block_status['is_blocked_by']
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_name, self.channel_name)

    async def receive(self, text_data):
        """
        Gère :
        - Envoi message (texte, image, fichier)
        - Suppression message
        """
        data = json.loads(text_data)
        msg_type = data.get('type', 'message')

        # ---------------------
        # 🔹 ENVOI MESSAGE
        # ---------------------
        if msg_type == 'message':
            content = data.get('message', '')
            file_url = data.get('file_url')
            image_url = data.get('image_url')

            if content or file_url or image_url:
                message = await self.save_message(content)

                await self.channel_layer.group_send(
                    self.room_name,
                    {
                        'type': 'private_message',
                        'id': message.id,
                        'sender': self.user.username,
                        'message': message.content,
                        'timestamp': message.timestamp.strftime("%d/%m %H:%M"),
                        'file_url': file_url,
                        'image_url': image_url,
                        'is_read': message.is_read,
                    }
                )

        # ---------------------
        # 🔹 SUPPRESSION MESSAGE
        # ---------------------
        elif msg_type == 'delete_message':
            msg_id = data.get('message_id')
            deleted = await self.delete_message(msg_id)

            if deleted:
                await self.channel_layer.group_send(
                    self.room_name,
                    {
                        'type': 'delete_message_event',
                        'message_id': msg_id
                    }
                )

    # ====================================================
    # 🔥 FONCTIONS BROADCAST
    # ====================================================

        action = data.get('action', 'message')

        # Action: Envoyer un message
        if action == 'message':
            message_content = data.get('message', '')

            if message_content:
                # Vérifier si l'utilisateur est bloqué
                is_blocked = await self.is_blocked_by_other()
                is_blocking = await self.is_blocking_other()

                if is_blocking:
                    # L'utilisateur a bloqué l'autre → impossible d'envoyer
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': 'Vous avez bloqué cet utilisateur. Débloquez-le pour envoyer des messages.'
                    }))
                    return

                if is_blocked:
                    # L'utilisateur est bloqué par l'autre → impossible d'envoyer
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': 'Impossible d\'envoyer le message.'
                    }))
                    return

                # Sauvegarder et envoyer le message
                await self.save_private_message(message_content)

                await self.channel_layer.group_send(
                    self.room_name,
                    {
                        'type': 'private_message',
                        'message': message_content,
                        'sender': self.user.username,
                        'timestamp': self.get_current_timestamp()
                    }
                )

        # Action: Notification de blocage (envoyée depuis le frontend)
        elif action == 'user_blocked':
            # Notifier l'autre utilisateur qu'il a été bloqué
            await self.channel_layer.group_send(
                self.room_name,
                {
                    'type': 'block_notification',
                    'blocker': self.user.username,
                    'message': 'Vous avez été bloqué par cet utilisateur.'
                }
            )

        # Action: Notification de déblocage
        elif action == 'user_unblocked':
            # Notifier l'autre utilisateur qu'il a été débloqué
            await self.channel_layer.group_send(
                self.room_name,
                {
                    'type': 'unblock_notification',
                    'unblocker': self.user.username,
                    'message': 'Vous pouvez à nouveau communiquer avec cet utilisateur.'
                }
            )

    async def private_message(self, event):
        """
        Envoi d'un message à TOUS les clients connectés.
        Ici on renvoie exactement ce que ton JS attend.
        """
        """Reçoit et envoie les messages privés"""
        await self.send(text_data=json.dumps({
            'type': 'message',  # obligatoire pour ton JS
            'id': event['id'],
            'sender': event['sender'],
            'message': event['message'],
            'timestamp': event['timestamp'],
            'file_url': event.get('file_url'),
            'image_url': event.get('image_url'),
            'is_read': event.get('is_read'),
        }))

    async def delete_message_event(self, event):
        """
        Broadcast de suppression de message.
        """
        await self.send(text_data=json.dumps({
            'type': 'delete_message',
            'message_id': event['message_id']
        }))

    # ====================================================
    # 🔥 BASE DE DONNÉES
    # ====================================================


    async def block_notification(self, event):
        """Notification envoyée à l'utilisateur bloqué"""
        # Ne pas notifier le bloqueur lui-même
        if event['blocker'] != self.user.username:
            await self.send(text_data=json.dumps({
                'type': 'blocked',
                'message': event['message']
            }))

    async def unblock_notification(self, event):
        """Notification envoyée à l'utilisateur débloqué"""
        # Ne pas notifier le débloqueur lui-même
        if event['unblocker'] != self.user.username:
            await self.send(text_data=json.dumps({
                'type': 'unblocked',
                'message': event['message']
            }))

    @database_sync_to_async
    def get_other_user(self):
        """Récupère l'autre utilisateur"""
        from django.contrib.auth.models import User
        try:
            return User.objects.get(username=self.other_username)
        except User.DoesNotExist:
            return None

    @database_sync_to_async
    def is_blocking_other(self):
        """Vérifie si self.user bloque other_user"""
        return Block.objects.filter(
            blocker=self.user,
            blocked=self.other_user
        ).exists()

    @database_sync_to_async
    def is_blocked_by_other(self):
        """Vérifie si self.user est bloqué par other_user"""
        return Block.objects.filter(
            blocker=self.other_user,
            blocked=self.user
        ).exists()

    @database_sync_to_async
    def check_block_status(self):
        """Vérifie le statut de blocage complet"""
        is_blocking = Block.objects.filter(
            blocker=self.user,
            blocked=self.other_user
        ).exists()

        is_blocked_by = Block.objects.filter(
            blocker=self.other_user,
            blocked=self.user
        ).exists()

        return {
            'is_blocking': is_blocking,
            'is_blocked_by': is_blocked_by
        }

    @database_sync_to_async
    def save_message(self, content):
        receiver = User.objects.get(username=self.other_username)
        return PrivateMessage.objects.create(
            sender=self.user,
            receiver=receiver,
            content=content
        )

    @database_sync_to_async
    def delete_message(self, message_id):
        try:
            msg = PrivateMessage.objects.get(id=message_id, sender=self.user)
            msg.delete()
            return True
        except PrivateMessage.DoesNotExist:
            return False