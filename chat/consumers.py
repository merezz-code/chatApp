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
        await self.add_user_to_room()

        # envoie le message de bienvenue
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_join',
                'username': self.user.username,
                'message': f'{self.user.username} a rejoint le salon'
            }
        )

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'user_leave',
                    'username': self.user.username,
                    'message': f'{self.user.username} a quitté le salon'
                }
            )
            
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
    
    async def receive(self, text_data):
        data = json.loads(text_data)
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
    
    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message': event['message'],
            'username': event['username'],
            'timestamp': event['timestamp']
        }))
    
    async def user_join(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_join',
            'username': event['username'],
            'message': event['message']
        }))
    
    async def user_leave(self, event):
        print(f"--- LOG SERVEUR (user_leave) ---: Événement reçu: {event}")
        await self.send(text_data=json.dumps({
            'type': 'user_leave',
            'username': event['username'],
            'message': event['message']
        }))

    @database_sync_to_async
    def get_room(self):
        """
        Récupère le salon en ignorant la casse.
        """
        return Room.objects.filter(name__iexact=self.room_name).first()

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
    
    def get_current_timestamp(self):
        from datetime import datetime
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


class PrivateChatConsumer(AsyncWebsocketConsumer):
    """Consumer pour les messages privés"""
    
    async def connect(self):
        self.user = self.scope['user']
        self.other_username = self.scope['url_route']['kwargs']['username']
        
        if not self.user.is_authenticated:
            await self.close()
            return
        
        users = sorted([self.user.username, self.other_username])
        self.room_name = f'private_{users[0]}_{users[1]}'
        
        await self.channel_layer.group_add(
            self.room_name,
            self.channel_name
        )
        
        await self.accept()
    
    async def disconnect(self, close_code):
        if hasattr(self, 'room_name'):
            await self.channel_layer.group_discard(
                self.room_name,
                self.channel_name
            )
    
    async def receive(self, text_data):
        data = json.loads(text_data)
        message_content = data.get('message', '')
        
        if message_content:
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
    
    async def private_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message': event['message'],
            'sender': event['sender'],
            'timestamp': event['timestamp']
        }))
    
    @database_sync_to_async
    def save_private_message(self, message_content):
        receiver = User.objects.get(username=self.other_username)
        PrivateMessage.objects.create(
            sender=self.user,
            receiver=receiver,
            content=message_content
        )
    
    def get_current_timestamp(self):
        from datetime import datetime
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')