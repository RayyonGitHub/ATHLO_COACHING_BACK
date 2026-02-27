from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from core.views import ClientViewSet, CoachMeView, AthleteMeView, ExerciceViewSet, DemoStatsView
from core.views_auth import register_view, login_view
from rest_framework_simplejwt.views import TokenRefreshView

router = DefaultRouter()

# CORRECTION ICI : Ajout de basename='client' 
router.register(r'clients', ClientViewSet, basename='client')
router.register(r'exercices', ExerciceViewSet, basename='exercice') 

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
    
    path('api/auth/register/', register_view, name='register'),
    path('api/auth/login/', login_view, name='login'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/coach/me/', CoachMeView.as_view(), name='coach-me'),
    path('api/athlete/me/', AthleteMeView.as_view(), name='athlete-me'),
    path('api/demo/stats/', DemoStatsView.as_view(), name='demo-stats'),
    path('api-auth/', include('rest_framework.urls')),
]