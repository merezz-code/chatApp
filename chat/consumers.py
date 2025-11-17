import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from .models import Room, Message, PrivateMessage
from django.utils.text import slugify


class ChatConsumer(AsyncWebsocketConsumer):
    """Consumer pour les salons de discussion publics"""
    
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        safe_room_name = slugify(self.room_name)
        self.room_group_name = f'chat_{safe_room_name}'
        self.user = self.scope['user']
        
        if not self.user.is_authenticated:
            await self.close()
            return

        self.room = await self.get_room()

        if self.room is None:
            print(f"ERREUR: Salon '{self.room_name}' non trouvé. Connexion refusée.")
            await self.close()
            return

        await self.accept()

        #On ajoute le canal au groupe
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

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
        data = json.loads(text_data)
        action = data.get('action')

        if action == 'message':
            message_content = data.get('message', '')
            if message_content:
                await self.save_message(message_content)
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_message',
                        'message': message_content,
                        'username': self.user.username,
                        'timestamp': self.get_current_timestamp()
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

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message': event['message'],
            'username': event['username'],
            'timestamp': event['timestamp']
        }))

    async def members_update(self, event):
        """
            Envoie la mise à jour de la liste des membres et le message au client.
        """
        await self.send(text_data=json.dumps({
            'type': 'members_update',
            'message': event.get('message'),
            'username_removed': event.get('username_removed'),
            'members_data': event.get('members_data')
        }))

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


class PrivateChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.user = self.scope['user']
        self.other_username = self.scope['url_route']['kwargs']['username']

        if not self.user.is_authenticated:
            await self.close()
            return

        # Room unique, neutre
        users = sorted([self.user.username, self.other_username])
        self.room_name = f'private_{users[0]}_{users[1]}'

        await self.channel_layer.group_add(self.room_name, self.channel_name)
        await self.accept()

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

    async def private_message(self, event):
        """
        Envoi d'un message à TOUS les clients connectés.
        Ici on renvoie exactement ce que ton JS attend.
        """
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