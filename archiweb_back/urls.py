from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

# On importe toutes les vues combinées (les tiennes + celles de l'issue)
# N'oublie pas d'ajouter PerformanceCreateView à la fin de cette liste !
from core.views import (
    ClientViewSet, CoachMeView, AthleteMeView, 
    ExerciceViewSet, ProgrammeViewSet, SeanceViewSet, 
    AthleteDashboardView, DemoStatsView, CoachAnalyticsView,
    PerformanceCreateView, CoachCalendarView, IndisponibiliteViewSet,NotificationViewSet,
)
from core.views_auth import register_view, login_view
from core.views_admin import (
    admin_login_view, admin_coach_list, 
    admin_stats_view, admin_toggle_coach_status
)
from core.views import export_coach_calendar,remove_participant,update_inscription_status

# Configuration du Router
router = DefaultRouter()
router.register(r'clients', ClientViewSet, basename='client')
router.register(r'exercices', ExerciceViewSet, basename='exercice')
router.register(r'programmes', ProgrammeViewSet, basename='programme')
router.register(r'seances', SeanceViewSet, basename='seance')
router.register(r'indisponibilites', IndisponibiliteViewSet, basename='indisponibilite')
router.register(r'notifications', NotificationViewSet, basename='notification')

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
    
    # --- Tes vues (Démo & Analytics) ---
    path('api/demo/stats/', DemoStatsView.as_view(), name='demo-stats'),
    path('api/coach/analytics/', CoachAnalyticsView.as_view(), name='coach-analytics'),

    # --- Dashboard Athlète ---
    path('api/athlete/dashboard-stats/', AthleteDashboardView.as_view(), name='athlete-dashboard-stats'),
    
    # --- NOUVEAU : Tracking de Performance ---
    path('api/athlete/performance/record/', PerformanceCreateView.as_view(), name='record-performance'),

    # ROUTES SUPER-ADMIN (Isolées)
    path('api/admin/login/', admin_login_view, name='admin-login'),
    path('api/admin/stats/', admin_stats_view, name='admin-stats'),
    path('api/admin/coachs/', admin_coach_list, name='admin-coach-list'),
    path('api/admin/coachs/<int:pk>/status/', admin_toggle_coach_status, name='admin-coach-status'),

    #ROUTE pour calendrier coach
    path('api/calendar/coach/<int:coach_id>/', CoachCalendarView.as_view(), name='coach-calendar'),
    path('api/calendar/export/<int:coach_id>/', export_coach_calendar, name='export-calendar'),
    path('api-auth/', include('rest_framework.urls')),

    #ROUTE pour supprimer un partcipant d'une séance
    path('api/inscriptions/<int:inscription_id>/', remove_participant, name='remove-participant'),
    #ROUTE pour valider d'une séance
    path('api/inscriptions/<int:inscription_id>/status/', update_inscription_status, name='update-inscription-status'),
]