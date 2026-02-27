from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

# On combine tous les imports des deux branches
from core.views import (
    ClientViewSet, CoachMeView, AthleteMeView, 
    ExerciceViewSet, ProgrammeViewSet, AthleteDashboardView
)
from core.views_auth import register_view, login_view
from core.views_admin import (
    admin_login_view, admin_coach_list, 
    admin_stats_view, admin_toggle_coach_status
)

router = DefaultRouter()
router.register(r'clients', ClientViewSet, basename='client')
router.register(r'exercices', ExerciceViewSet, basename='exercice')
router.register(r'programmes', ProgrammeViewSet, basename='programme')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
    
    # Authentification Publique
    path('api/auth/register/', register_view, name='register'),
    path('api/auth/login/', login_view, name='login'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # Profils utilisateur
    path('api/coach/me/', CoachMeView.as_view(), name='coach-me'),
    path('api/athlete/me/', AthleteMeView.as_view(), name='athlete-me'),
    
    # Dashboard Athlète (Nouveau)
    path('api/athlete/dashboard-stats/', AthleteDashboardView.as_view(), name='athlete-dashboard-stats'),

    # ROUTES SUPER-ADMIN (Isolées)
    path('api/admin/login/', admin_login_view, name='admin-login'),
    path('api/admin/stats/', admin_stats_view, name='admin-stats'),
    path('api/admin/coachs/', admin_coach_list, name='admin-coach-list'),
    path('api/admin/coachs/<int:pk>/status/', admin_toggle_coach_status, name='admin-coach-status'),
]