from .forms import UserProfileForm
from .models import UserProfile

def user_profile_form(request):
    """Ajoute le formulaire de profil au contexte si l'utilisateur est connecté."""
    if request.user.is_authenticated:
        try:
            # Tente de récupérer le profil (request.user.profile fonctionne grâce à related_name='profile')
            profile = request.user.profile
            # Initialise le formulaire avec l'instance existante
            form = UserProfileForm(instance=profile)
            return {'form': form}
        except UserProfile.DoesNotExist:
            # Si un utilisateur n'a pas encore de profil (vous devriez utiliser des signaux pour éviter cela)
            return {'form': None}
    return {}