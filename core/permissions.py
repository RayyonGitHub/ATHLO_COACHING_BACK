from rest_framework import permissions

class IsSystemAdmin(permissions.BasePermission):
    """
    Vérifie que l'utilisateur est authentifié ET possède le flag staff/admin.
    Indispensable pour protéger l'endpoint /stats/.
    """
    def has_permission(self, request, view):
        return bool(
            request.user and 
            request.user.is_authenticated and 
            (request.user.is_staff or request.user.is_superuser)
        )