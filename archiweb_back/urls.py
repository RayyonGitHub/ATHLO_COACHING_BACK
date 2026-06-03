from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from core.views_shop import ProduitViewSet, CategorieProduitViewSet, CreateShopPaymentIntentView, ShopOrderConfirmView
from core import views
from core.views_nutrition import RecetteViewSet, PlanNutritionnelViewSet
from core.views import CreateOrderView
from core.views_responsable import ResponsableDashboardStatsView, ResponsablePlanningView, ResponsableCoachSupervisionView, ResponsableStatistiquesView, ResponsableMeView, ResponsableChangePasswordView, ResponsableNotificationListView, ResponsableNotificationDetailView, ResponsableCoachListView, ResponsableCoachDetailView
# core/urls.py
# Ajoutez AthleteMyPlansView (ou le nom exact de votre vue)
from core.views_nutrition import RecetteViewSet, PlanNutritionnelViewSet
from core.views_stripe import stripe_webhook, CreatePlatformSubscriptionView, CreateStripeConnectAccountView, CheckStripeConnectStatusView, stripe_connect_relay, CreateAthleteTopUpPaymentIntentView, ConfirmAthleteTopUpPaymentView
from core.views_admin import admin_salle_list_create, admin_salle_delete
from core.views_admin import admin_prospect_list, admin_delete_prospect, admin_finance_list, admin_exercice_list_create, admin_exercice_detail, admin_category_list_create, admin_category_delete, admin_me_view, admin_change_my_password, admin_responsable_list_create, admin_responsable_delete
from core.views_integrations import (
    get_external_activities,
    integrations_status,
    strava_connect,
    strava_disconnect,
     strava_sync # <-- NOUVEAU
)
from core.views import (
    ClientViewSet, CoachMeView, CoachAvailableSallesView, CoachDevisListView, CoachTraiterDevisView, AthleteMeView, ProspectMeView,
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
    password_reset_relay,
    invite_relay,
)
from core import views_admin
from core.views import export_coach_calendar, remove_participant, update_inscription_status, coach_inscrire_client
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
router.register(r'nutrition/recipes', RecetteViewSet, basename='nutrition-recipe')
router.register(r'nutrition/plans', PlanNutritionnelViewSet, basename='nutrition-plan')
urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
    path('api/admin/salles/', admin_salle_list_create, name='admin-salles'),
    path('api/admin/salles/<int:pk>/', admin_salle_delete, name='admin-salle-delete'),
    path('api/admin/prospects/', admin_prospect_list, name='admin-prospects'),
    path('api/admin/prospects/<int:pk>/', admin_delete_prospect, name='admin-delete-prospect'),
    path('api/admin/finance/', admin_finance_list, name='admin-finance'),
    path('api/admin/exercices/', admin_exercice_list_create, name='admin-exercices'),
    path('api/admin/exercices/<int:pk>/', admin_exercice_detail, name='admin-exercice-detail'),
    path('api/admin/categories/', admin_category_list_create, name='admin-categories'),
    path('api/admin/categories/<int:pk>/', admin_category_delete, name='admin-category-delete'),
    path('api/admin/me/', admin_me_view, name='admin-me'),
    path('api/admin/me/change-password/', admin_change_my_password, name='admin-change-my-password'),
    # Authentification Publique
    path('api/auth/register/', register_view, name='register'),
    path('api/auth/login/', login_view, name='login'),
    path('api/auth/forgot-password/', forgot_password_view, name='forgot-password'),
    path('api/auth/reset-password/', reset_password_view, name='reset-password'),
    path('api/auth/reset-relay/', password_reset_relay, name='password-reset-relay'),
    path('api/auth/invite-relay/', invite_relay, name='invite-relay'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/auth/change-password/', ChangePasswordView.as_view(), name='change-password'),

    # Profils utilisateur
    path('api/coach/me/', CoachMeView.as_view(), name='coach-me'),
    path('api/coach/salles-disponibles/', CoachAvailableSallesView.as_view(), name='coach-salles-disponibles'),
    path('api/coach/devis/', CoachDevisListView.as_view(), name='coach-devis-list'),
    path('api/coach/devis/<int:devis_id>/traiter/', CoachTraiterDevisView.as_view(), name='coach-devis-traiter'),
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
    path('api/athlete/topup/create-intent/', CreateAthleteTopUpPaymentIntentView.as_view(), name='athlete-topup-create-intent'),
    path('api/athlete/topup/confirm/', ConfirmAthleteTopUpPaymentView.as_view(), name='athlete-topup-confirm'),
    path('api/seances/<int:seance_id>/ratee/', MarquerSeanceRateeView.as_view(), name='seance-ratee'),

    # Tracking de Performance
    path('api/athlete/performance/record/', PerformanceCreateView.as_view(), name='record-performance'),

    # Super Admin - Étape 1
    path('api/admin/login/', views_admin.admin_login_view, name='admin-login'),
    path('api/admin/stats/', views_admin.admin_stats_view, name='admin-stats'),
    path('api/admin/notifications/', views_admin.admin_notifications_view, name='admin-notifications'),
    path('api/admin/coachs/', views_admin.admin_coach_list, name='admin-coach-list'),
    path('api/admin/athletes/', views_admin.admin_athlete_list, name='admin-athlete-list'),
    path('api/admin/athletes/<int:pk>/', views_admin.admin_delete_athlete, name='admin-athlete-delete'),
    path('api/admin/responsables/', admin_responsable_list_create, name='admin-responsables'),
    path('api/admin/responsables/<int:pk>/', admin_responsable_delete, name='admin-responsable-delete'),
    
    # Routes génériques Utilisateurs
    path('api/admin/users/<int:pk>/update/', views_admin.admin_update_user, name='admin-update-user'),
    path('api/admin/users/<int:pk>/change-password/', views_admin.admin_change_password, name='admin-change-password'),
    path('api/admin/users/<int:pk>/force-logout/', views_admin.admin_force_logout, name='admin-force-logout'),
    path('api/admin/users/<int:pk>/toggle-status/', views_admin.admin_toggle_user_status, name='admin-toggle-status'),

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
    path('api/inscriptions/coach/inscrire/<int:seance_id>/', coach_inscrire_client, name='coach-inscrire-client'),

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
    path('api/shop/orders/', CreateOrderView.as_view(), name='create-order'),

    # --- À AJOUTER DANS urlpatterns ---
    path('api/athlete/commandes/', views.AthleteCommandeHistoryView.as_view(), name='athlete-commandes'),
    path('api/shop/my-orders/', views.AthleteCommandeHistoryView.as_view(), name='shop-my-orders'),
    path('api/shop/create-intent/', CreateShopPaymentIntentView.as_view(), name='shop-create-intent'),
    path('api/shop/confirm-order/', ShopOrderConfirmView.as_view(), name='shop-confirm-order'),
    path('api/stripe/webhook/', stripe_webhook, name='stripe-webhook'),
    path('api/stripe/create-subscription/', CreatePlatformSubscriptionView.as_view(), name='create-subscription'),
    path('api/stripe/connect-onboarding/', CreateStripeConnectAccountView.as_view(), name='connect-onboarding'),
    path('api/stripe/connect-status/', CheckStripeConnectStatusView.as_view(), name='connect-status'),
    path('api/stripe/connect-relay/', stripe_connect_relay, name='stripe-connect-relay'),
    
   # Dashboard Responsable Salle
    path('api/responsable/dashboard-stats/', ResponsableDashboardStatsView.as_view(), name='responsable-dashboard-stats'),
    path('api/responsable/planning/', ResponsablePlanningView.as_view(), name='responsable-planning'),
    path('api/responsable/supervision-coachs/', ResponsableCoachSupervisionView.as_view(), name='responsable-supervision-coachs'),
    path('api/responsable/statistiques/', ResponsableStatistiquesView.as_view(), name='responsable-statistiques'),
    path('api/responsable/me/', ResponsableMeView.as_view(), name='responsable-me'),
    path('api/responsable/change-password/', ResponsableChangePasswordView.as_view(), name='responsable-change-password'),
    path('api/responsable/notifications/', ResponsableNotificationListView.as_view(), name='responsable-notifications'),
    path('api/responsable/notifications/<int:pk>/', ResponsableNotificationDetailView.as_view(), name='responsable-notification-detail'),
    path('api/responsable/coachs/', ResponsableCoachListView.as_view(), name='responsable-coach-list'),
    path('api/responsable/coachs/<int:coach_id>/', ResponsableCoachDetailView.as_view(), name='responsable-coach-detail'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
