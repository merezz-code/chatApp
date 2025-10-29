# Application de Chat Django avec Channels

## Overview
Application de chat en temps réel construite avec Django et Django Channels. L'application permet aux utilisateurs de créer des salons de discussion, envoyer des messages en temps réel, échanger des fichiers et des images, et communiquer en privé.

## Date de création
29 octobre 2025

## Recent Changes
- Création de la structure de base du projet Django
- Installation de Django, Django Channels, Channels-Redis et Pillow
- Configuration en cours

## Features
- **Authentification**: Inscription et connexion des utilisateurs avec Django Auth
- **Salons de discussion publics**: Création et gestion de salons multiples
- **Messages en temps réel**: Communication instantanée via WebSockets
- **Messages privés**: Communication 1-to-1 entre utilisateurs
- **Partage de fichiers**: Upload de fichiers et images dans les conversations
- **Utilisateurs en ligne**: Affichage des utilisateurs connectés dans chaque salon

## Project Architecture
```
chatapp/          # Configuration principale Django
chat/            # Application de chat
├── models.py    # Modèles: Room, Message, PrivateMessage
├── views.py     # Vues pour l'interface web
├── consumers.py # Consommateurs WebSocket pour temps réel
├── routing.py   # Configuration des routes WebSocket
└── templates/   # Templates HTML
```

## Technologies
- **Backend**: Django 5.2, Django Channels 4.3
- **WebSocket Layer**: Channels-Redis 4.3
- **Database**: SQLite (dev)
- **Frontend**: HTML, CSS, JavaScript vanilla
- **Image Processing**: Pillow 12.0

## User Preferences
- Langue: Français
- Interface responsive et moderne
