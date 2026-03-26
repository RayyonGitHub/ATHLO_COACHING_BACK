from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from core import views

from core.views import (
    ClientViewSet, CoachMeView, AthleteMeView, ProspectMeView,
    ExerciceViewSet, ProgrammeViewSet, SeanceViewSet,
    AthleteDashboardView, AthleteStatsView,
    DemoStatsView, CoachAnalyticsView,
    PerformanceCreateView, CoachCalendarView, IndisponibiliteViewSet, 
    NotificationViewSet, # Celui de ton collègue (Coach)
    AthleteNotificationViewSet, # <-- TA NOUVELLE VUE (Athlète)
    ChangePasswordView
)
from core.views_auth import register_view, login_view
from core.views_admin import (
    admin_login_view, admin_coach_list,
    admin_stats_view, admin_toggle_coach_status
)
from core.views import export_coach_calendar, remove_participant, update_inscription_status
from core.views_messages import (
    AvailableContactsView,
    ConversationListCreateView,
    ConversationDetailView,
    ConversationMembersView,
    ConversationMemberDeleteView,
    ConversationMessagesView,
    ConversationReadView,
)

# --- CONFIGURATION DU ROUTEUR ---
router = DefaultRouter()
router.register(r'clients', ClientViewSet, basename='client')
router.register(r'exercices', ExerciceViewSet, basename='exercice')
router.register(r'programmes', ProgrammeViewSet, basename='programme')
router.register(r'seances', SeanceViewSet, basename='seance')
router.register(r'indisponibilites', IndisponibiliteViewSet, basename='indisponibilite')

# Notifications du Coach (L'existant)
router.register(r'notifications', NotificationViewSet, basename='notification')

# 🔔 TES NOTIFICATIONS (Athlète)
# Cela créera l'URL : /api/notifications-athlete/
router.register(r'notifications-athlete', AthleteNotificationViewSet, basename='notification-athlete')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),

    # Authentification Publique
    path('api/auth/register/', register_view, name='register'),
    path('api/auth/login/', login_view, name='login'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/auth/change-password/', ChangePasswordView.as_view(), name='change-password'),

    # Profils utilisateur
    path('api/coach/me/', CoachMeView.as_view(), name='coach-me'),
    path('api/athlete/me/', AthleteMeView.as_view(), name='athlete-me'),
    path('api/prospect/me/', ProspectMeView.as_view(), name='prospect-me'),

    # Démo & Analytics
    path('api/demo/stats/', DemoStatsView.as_view(), name='demo-stats'),
    path('api/coach/analytics/', CoachAnalyticsView.as_view(), name='coach-analytics'),

    # Dashboard Athlète
    path('api/athlete/dashboard-stats/', AthleteDashboardView.as_view(), name='athlete-dashboard-stats'),
    path('api/athlete/stats/', AthleteStatsView.as_view(), name='athlete-stats'),

    # Tracking de Performance
    path('api/athlete/performance/record/', PerformanceCreateView.as_view(), name='record-performance'),

    # Super Admin
    path('api/admin/login/', admin_login_view, name='admin-login'),
    path('api/admin/stats/', admin_stats_view, name='admin-stats'),
    path('api/admin/coachs/', admin_coach_list, name='admin-coach-list'),
    path('api/admin/coachs/<int:pk>/status/', admin_toggle_coach_status, name='admin-coach-status'),

    # Calendrier coach et athlete
    path('api/calendar/coach/<int:coach_id>/', CoachCalendarView.as_view(), name='coach-calendar'),
    path('api/calendar/export/<int:coach_id>/', export_coach_calendar, name='export-calendar'),
    path('api-auth/', include('rest_framework.urls')),
    path('api/calendar/export/athlete/<int:athlete_id>/', views.export_athlete_calendar, name='export-athlete-calendar'),


    # Inscriptions
    path('api/inscriptions/<int:inscription_id>/', remove_participant, name='remove-participant'),
    path('api/inscriptions/<int:inscription_id>/status/', update_inscription_status, name='update-inscription-status'),
    path('api/inscriptions/reserver/<int:seance_id>/', views.athlete_reserver_seance, name='athlete-reserver-seance'),
    path('api/inscriptions/annuler/<int:inscription_id>/', views.athlete_annuler_reservation, name='athlete-annuler-reservation'),

    # Messagerie V2
    path('api/messages/contacts/', AvailableContactsView.as_view(), name='message-contacts'),
    path('api/messages/conversations/', ConversationListCreateView.as_view(), name='message-conversations'),
    path('api/messages/conversations/<int:conversation_id>/', ConversationDetailView.as_view(), name='message-conversation-detail'),
    path('api/messages/conversations/<int:conversation_id>/members/', ConversationMembersView.as_view(), name='message-conversation-members'),
    path('api/messages/conversations/<int:conversation_id>/members/<int:user_id>/', ConversationMemberDeleteView.as_view(), name='message-conversation-member-delete'),
    path('api/messages/conversations/<int:conversation_id>/messages/', ConversationMessagesView.as_view(), name='message-conversation-messages'),
    path('api/messages/conversations/<int:conversation_id>/read/', ConversationReadView.as_view(), name='message-conversation-read'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)