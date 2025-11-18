import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from .models import Room, Message, PrivateMessage
from django.utils.text import slugify


# chat/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils.text import slugify
from django.contrib.auth.models import User
from .models import Room, Message

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
        self.room = await self._get_room()
        if self.room is None:
            await self.close()
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

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

        elif action == 'delete_message':
            message_id = data.get('message_id')
            if not message_id:
                await self.send(text_data=json.dumps({'type':'error','message':'missing message_id'}))
                return

            # Récupérer le message et vérifier propriétaire
            msg = await self._get_message_by_id(message_id)
            if msg is None:
                await self.send(text_data=json.dumps({'type':'error','message':'message not found'}))
                return

            if msg.user_id != self.user.id:
                await self.send(text_data=json.dumps({'type':'error','message':'not allowed'}))
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

        # else: autres actions gérées ailleurs (members, etc.)

    # event handlers (broadcast)
    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message',
            'id': event['id'],
            'username': event['username'],
            'message': event['message'],
            'timestamp': event['timestamp']
        }))

    async def delete_message_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'delete_message',
            'message_id': event['message_id']
        }))

    # ---------- DB helpers (sync -> async wrapper) ----------
    @database_sync_to_async
    def _get_room(self):
        try:
            return Room.objects.get(name__iexact=self.room_name)
        except Room.DoesNotExist:
            return None

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