from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from core.views_shop import ProduitViewSet, CategorieProduitViewSet
from core import views


from core.views_integrations import (
    get_external_activities,
    integrations_status,
    strava_connect,
    strava_disconnect,
     strava_sync # <-- NOUVEAU
)
from core.views import (
    ClientViewSet, CoachMeView, AthleteMeView, ProspectMeView,
    ExerciceViewSet, ProgrammeViewSet, SeanceViewSet,
    AthleteDashboardView, AthleteStatsView,
    DemoStatsView, CoachAnalyticsView,
    PerformanceCreateView, CoachCalendarView, IndisponibiliteViewSet,
    NotificationViewSet, AthleteNotificationViewSet,
    ChangePasswordView, MarquerSeanceRateeView
)
from core.views_auth import (
    register_view,
    login_view,
    forgot_password_view,
    reset_password_view,
)
from core.views_admin import (
    admin_login_view,
    admin_coach_list,
    admin_athlete_list,
    admin_stats_view,
    admin_toggle_coach_status,
    admin_delete_athlete
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
from core.views_google import (
    google_calendar_status,
    google_calendar_connect,
    google_calendar_disconnect,
)
from core.views_prospect import (
    PublicCoachListView,
    ProspectCheckoutPayView,
    ProspectCheckoutPreviewView,
    ProspectActivateAthleteView,
    InvitationCheckoutPreviewView,
    InvitationCheckoutPayView,
    InvitationSetPasswordView,
    PublicSalleListView,
    ProspectDemandeDevisView,
)


router = DefaultRouter()
router.register(r'clients', ClientViewSet, basename='client')
router.register(r'exercices', ExerciceViewSet, basename='exercice')
router.register(r'programmes', ProgrammeViewSet, basename='programme')
router.register(r'seances', SeanceViewSet, basename='seance')
router.register(r'indisponibilites', IndisponibiliteViewSet, basename='indisponibilite')
router.register(r'notifications', NotificationViewSet, basename='notification')
router.register(r'notifications-athlete', AthleteNotificationViewSet, basename='notification-athlete')
router.register(r'shop/products', ProduitViewSet, basename='shop-product')
router.register(r'shop/categories', CategorieProduitViewSet, basename='shop-category')
urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),

    # Authentification Publique
    path('api/auth/register/', register_view, name='register'),
    path('api/auth/login/', login_view, name='login'),
    path('api/auth/forgot-password/', forgot_password_view, name='forgot-password'),
    path('api/auth/reset-password/', reset_password_view, name='reset-password'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/auth/change-password/', ChangePasswordView.as_view(), name='change-password'),

    # Profils utilisateur
    path('api/coach/me/', CoachMeView.as_view(), name='coach-me'),
    path('api/athlete/me/', AthleteMeView.as_view(), name='athlete-me'),
    path('api/prospect/me/', ProspectMeView.as_view(), name='prospect-me'),

    # Prospect / Marketplace / Paiement
    path('api/prospects/coachs/', PublicCoachListView.as_view(), name='prospect-public-coachs'),
    path('api/prospects/checkout/pay/', ProspectCheckoutPayView.as_view(), name='prospect-checkout-pay'),
    path('api/prospects/checkout/preview/', ProspectCheckoutPreviewView.as_view(), name='prospect-checkout-preview'),
    path('api/prospects/checkout/activate-athlete/', ProspectActivateAthleteView.as_view(), name='prospect-activate-athlete'),

    # Flow invitation coach -> client
    path('api/prospects/invitations/checkout/preview/', InvitationCheckoutPreviewView.as_view(), name='invitation-checkout-preview'),
    path('api/prospects/invitations/checkout/pay/', InvitationCheckoutPayView.as_view(), name='invitation-checkout-pay'),
    path('api/prospects/invitations/set-password/', InvitationSetPasswordView.as_view(), name='invitation-set-password'),

    # Prospect / Salles / Devis
    path('api/prospects/salles/', PublicSalleListView.as_view(), name='prospect-salles'),
    path('api/prospects/devis/', ProspectDemandeDevisView.as_view(), name='prospect-devis'),

    # Démo & Analytics
    path('api/demo/stats/', DemoStatsView.as_view(), name='demo-stats'),
    path('api/coach/analytics/', CoachAnalyticsView.as_view(), name='coach-analytics'),

    # Dashboard Athlète
    path('api/athlete/dashboard-stats/', AthleteDashboardView.as_view(), name='athlete-dashboard-stats'),
    path('api/athlete/stats/', AthleteStatsView.as_view(), name='athlete-stats'),
    path('api/seances/<int:seance_id>/ratee/', MarquerSeanceRateeView.as_view(), name='seance-ratee'),

    # Tracking de Performance
    path('api/athlete/performance/record/', PerformanceCreateView.as_view(), name='record-performance'),

    # Super Admin
    path('api/admin/login/', admin_login_view, name='admin-login'),
    path('api/admin/stats/', admin_stats_view, name='admin-stats'),
    path('api/admin/coachs/', admin_coach_list, name='admin-coach-list'),
    path('api/admin/athletes/', admin_athlete_list, name='admin-athlete-list'),
    path('api/admin/athletes/<int:pk>/delete/', admin_delete_athlete, name='admin-athlete-delete'),
    path('api/admin/coachs/<int:pk>/status/', admin_toggle_coach_status, name='admin-coach-status'),

    # Calendrier coach et athlète
    path('api/calendar/coach/<int:coach_id>/', CoachCalendarView.as_view(), name='coach-calendar'),
    path('api/calendar/export/<int:coach_id>/', export_coach_calendar, name='export-calendar'),
    path('api-auth/', include('rest_framework.urls')),
    path('api/calendar/export/athlete/<int:athlete_id>/', views.export_athlete_calendar, name='export-athlete-calendar'),

    # Google Calendar
    path('api/google-calendar/status/', google_calendar_status, name='google-calendar-status'),
    path('api/google-calendar/connect/', google_calendar_connect, name='google-calendar-connect'),
    path('api/google-calendar/disconnect/', google_calendar_disconnect, name='google-calendar-disconnect'),

    # Inscriptions
    path('api/inscriptions/<int:inscription_id>/', remove_participant, name='remove-participant'),
    path('api/inscriptions/<int:inscription_id>/status/', update_inscription_status, name='update-inscription-status'),
    path('api/inscriptions/reserver/<int:seance_id>/', views.athlete_reserver_seance, name='athlete-reserver-seance'),
    path('api/inscriptions/annuler/<int:inscription_id>/', views.athlete_annuler_reservation, name='athlete-annuler-reservation'),

    # Messagerie
    path('api/messages/contacts/', AvailableContactsView.as_view(), name='message-contacts'),
    path('api/messages/conversations/', ConversationListCreateView.as_view(), name='message-conversations'),
    path('api/messages/conversations/<int:conversation_id>/', ConversationDetailView.as_view(), name='message-conversation-detail'),
    path('api/messages/conversations/<int:conversation_id>/members/', ConversationMembersView.as_view(), name='message-conversation-members'),
    path('api/messages/conversations/<int:conversation_id>/members/<int:user_id>/', ConversationMemberDeleteView.as_view(), name='message-conversation-member-delete'),
    path('api/messages/conversations/<int:conversation_id>/messages/', ConversationMessagesView.as_view(), name='message-conversation-messages'),
    path('api/messages/conversations/<int:conversation_id>/read/', ConversationReadView.as_view(), name='message-conversation-read'),

# Intégrations Sportives (Strava / Garmin) pour l'Athlète
    path('api/athlete/integrations/status/', integrations_status, name='integrations-status'),
    path('api/athlete/integrations/strava/connect/', strava_connect, name='strava-connect'),
    path('api/athlete/integrations/strava/disconnect/', strava_disconnect, name='strava-disconnect'),
    path('api/athlete/integrations/strava/sync/', strava_sync, name='strava-sync'),
    path('api/athlete/integrations/activities/', get_external_activities, name='get-external-activities'),


    # --- À AJOUTER DANS urlpatterns ---
    path('api/athlete/commandes/', views.AthleteCommandeHistoryView.as_view(), name='athlete-commandes'),

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)