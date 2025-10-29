# Application de Chat Django avec Channels

## Overview
Application de chat en temps réel construite avec Django et Django Channels. L'application permet aux utilisateurs de créer des salons de discussion, envoyer des messages en temps réel, échanger des fichiers et des images, et communiquer en privé.

## Date de création
29 octobre 2025

## Recent Changes
29 octobre 2025:
- ✅ Création complète de la structure du projet Django avec Channels
- ✅ Installation de Django 5.2, Channels 4.3, Daphne 4.2 et Pillow 12.0
- ✅ Configuration de Django Channels avec ASGI et WebSockets
- ✅ Création des modèles: Room, Message, PrivateMessage, UserProfile
- ✅ Implémentation des WebSocket consumers pour chat temps réel
- ✅ Système d'authentification complet (inscription/connexion/déconnexion)
- ✅ Interface utilisateur moderne avec Bootstrap 5
- ✅ Support upload de fichiers et images
- ✅ Workflow Daphne configuré et fonctionnel sur port 5000
- ✅ Application testée et validée par l'architecte

## Features
- **Authentification**: Inscription et connexion des utilisateurs avec Django Auth
- **Salons de discussion publics**: Création et gestion de salons multiples
- **Messages en temps réel**: Communication instantanée via WebSockets
- **Messages privés**: Communication 1-to-1 entre utilisateurs
- **Partage de fichiers**: Upload de fichiers et images dans les conversations
- **Utilisateurs en ligne**: Affichage des utilisateurs connectés dans chaque salon

## Project Architecture
```
chatapp/              # Configuration principale Django
├── settings.py       # Configuration Django + Channels
├── asgi.py          # Configuration ASGI pour WebSockets
├── urls.py          # URLs principales
└── wsgi.py

chat/                # Application de chat
├── models.py        # Room, Message, PrivateMessage, UserProfile
├── views.py         # Vues: login, register, rooms, private chat
├── consumers.py     # ChatConsumer, PrivateChatConsumer (WebSocket)
├── routing.py       # Routes WebSocket
├── urls.py          # URLs de l'application chat
├── forms.py         # Formulaires Django
├── admin.py         # Interface d'administration
├── templates/       # Templates HTML
│   └── chat/
│       ├── base.html
│       ├── login.html
│       ├── register.html
│       ├── home.html
│       ├── room.html
│       ├── private_chat.html
│       └── create_room.html
└── migrations/      # Migrations de base de données

manage.py            # Outil de gestion Django
db.sqlite3           # Base de données SQLite
```

## Fonctionnalités Implémentées
✅ **Authentification utilisateur** (Django Auth)
✅ **Création et gestion de salons publics**
✅ **Chat en temps réel via WebSockets**
✅ **Messages privés 1-to-1**
✅ **Upload de fichiers et images**
✅ **Affichage des utilisateurs en ligne**
✅ **Interface responsive moderne**
✅ **Historique des messages**

## Comment Utiliser
1. **Inscription**: Cliquez sur "Inscription" et créez un compte
2. **Connexion**: Connectez-vous avec vos identifiants
3. **Créer un salon**: Cliquez sur "Nouveau Salon" et donnez-lui un nom
4. **Rejoindre un salon**: Cliquez sur un salon dans la liste
5. **Envoyer des messages**: Tapez dans le champ de texte et appuyez sur Entrée
6. **Messages privés**: Cliquez sur un utilisateur dans la liste pour discuter en privé

## Améliorations Futures Suggérées
- Ajouter Redis comme channel layer pour la production
- Implémenter des tests automatisés pour les WebSockets
- Ajouter des limites de taille/type pour les uploads
- Intégrer un système d'emojis et de réactions
- Ajouter les notifications en temps réel
- Implémenter l'édition et la suppression de messages

## Technologies
- **Backend**: Django 5.2, Django Channels 4.3
- **WebSocket Layer**: Channels-Redis 4.3
- **Database**: SQLite (dev)
- **Frontend**: HTML, CSS, JavaScript vanilla
- **Image Processing**: Pillow 12.0

## User Preferences
- Langue: Français
- Interface responsive et moderne
