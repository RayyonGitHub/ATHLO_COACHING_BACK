from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from core.views import ClientViewSet
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

# Configuration du Router pour les clients (Issue #5)
router = DefaultRouter()
router.register(r'clients', ClientViewSet) # URL accessible via /api/clients/

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # --- Routes API Métier ---
    path('api/', include(router.urls)),
    
    # --- Routes API Authentification (Issue #3) ---
    # Route pour se connecter et recevoir le Token (Login)
    path('api/login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    
    # Route pour rafraîchir le Token quand il expire
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]