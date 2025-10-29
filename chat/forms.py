from django import forms
from .models import Room, Message, PrivateMessage


class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nom du salon'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Description', 'rows': 3}),
        }


class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ['content', 'image', 'file']
        widgets = {
            'content': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Votre message...', 'rows': 2}),
        }


class PrivateMessageForm(forms.ModelForm):
    class Meta:
        model = PrivateMessage
        fields = ['content', 'image', 'file']
        widgets = {
            'content': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Message privé...', 'rows': 2}),
        }
