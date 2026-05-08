from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from .models import Coach, Client, Salle, Commande, Devis, Exercice, CategorieProduit
from .permissions import IsSystemAdmin
from .serializers import SalleSerializer
from django.db.models import Sum, Avg, Count
from django.utils import timezone
from datetime import timedelta
from django.utils.text import slugify
# --- LOGIN ADMIN ---
@api_view(['POST'])
@permission_classes([AllowAny])
def admin_login_view(request):
    try:
        email = request.data.get('email')
        password = request.data.get('password')
        if not email or not password:
            return Response({'message': 'Email et mot de passe requis'}, status=400)
        user = User.objects.filter(email=email).first()
        if not user or not user.check_password(password):
            return Response({'message': 'Identifiants incorrects'}, status=401)
        if not user.is_staff and not user.is_superuser:
            return Response({'message': 'Accès refusé.'}, status=403)
        refresh = RefreshToken.for_user(user)
        return Response({
            'token': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'id': user.id,
                'email': user.email,
                'name': f"{user.first_name} {user.last_name}".strip(),
                'role': 'admin'
            }
        })
    except Exception as e:
        return Response({'message': str(e)}, status=500)

# --- STATS ---
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_stats_view(request):
    now = timezone.now()
    first_day_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Stats de base
    total_coaches = User.objects.filter(coach_profile__isnull=False).count()
    total_athletes = User.objects.filter(client_profile__isnull=False).count()
    gym_partners = Salle.objects.count()

    # Revenu Total (Vrai calcul)
    total_revenue = Commande.objects.filter(status='PAID').aggregate(total=Sum('montant_ttc'))['total'] or 0.0

    # MRR (Monthly Recurring Revenue) : Somme des abonnements payés ce mois-ci
    mrr = Commande.objects.filter(
        status='PAID', 
        offre_type='abonnement',
        date_commande__gte=first_day_of_month
    ).aggregate(total=Sum('montant_ttc'))['total'] or 0.0

    # Inscriptions ce mois-ci (Athlètes)
    registrations_this_month = Client.objects.filter(date_creation__gte=first_day_of_month).count()

    return Response({
        "total_coaches": total_coaches,
        "total_athletes": total_athletes,
        "total_revenue": round(total_revenue, 2),
        "mrr": round(mrr, 2),
        "registrations_this_month": registrations_this_month,
        "gym_partners": gym_partners
    })

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_finance_list(request):
    # On récupère toutes les commandes avec les infos client et facture
    commandes = Commande.objects.select_related('client', 'facture').all().order_by('-date_commande')
    
    data = []
    for cmd in commandes:
        data.append({
            "id": cmd.id,
            "order_number": cmd.order_number,
            "client_name": f"{cmd.client.prenom} {cmd.client.nom}",
            "offre": cmd.offre_label,
            "montant": cmd.montant_ttc,
            "status": cmd.status,
            "date": cmd.date_commande.strftime("%d/%m/%Y %H:%M"),
            "has_invoice": hasattr(cmd, 'facture'),
            "invoice_url": cmd.facture.pdf_file.url if hasattr(cmd, 'facture') and cmd.facture.pdf_file else None
        })
    return Response(data)
# --- NOUVELLE GESTION DES SALLES (CRUD ADMIN) ---
@api_view(['GET', 'POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_salle_list_create(request):
    if request.method == 'GET':
        salles = Salle.objects.all().order_by('-id')
        data = []
        for s in salles:
            data.append({
                "id": s.id,
                "nom": s.nom,
                "adresse": s.adresse,
                "ville": s.ville,
                "latitude": s.latitude,
                "longitude": s.longitude,
                "nb_coachs": s.coachs_affilies.count() # Utilise le related_name défini dans models.py
            })
        return Response(data)

    elif request.method == 'POST':
        serializer = SalleSerializer(data=request.data)
        if serializer.is_valid():
            s = serializer.save()
            return Response({
                "id": s.id, 
                "nom": s.nom, 
                "adresse": s.adresse, 
                "ville": s.ville, 
                "nb_coachs": 0
            }, status=201)
        return Response(serializer.errors, status=400)

@api_view(['DELETE'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_salle_delete(request, pk):
    try:
        salle = Salle.objects.get(pk=pk)
        salle.delete()
        return Response({"message": "Salle supprimée"}, status=204)
    except Salle.DoesNotExist:
        return Response({"error": "Salle introuvable"}, status=404)
# --- CATALOGUE : EXERCICES ---
@api_view(['GET', 'POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_exercice_list_create(request):
    if request.method == 'GET':
        exercices = Exercice.objects.all().order_by('-id')
        data = [{
            "id": e.id,
            "nom": e.nom,
            "description": e.description,
            "categorie": e.categorie,
            "muscle_principal": e.muscle_principal,
            "video_url": e.video_url
        } for e in exercices]
        return Response(data)
    
    elif request.method == 'POST':
        data = request.data
        ex = Exercice.objects.create(
            nom=data.get('nom'),
            description=data.get('description', ''),
            categorie=data.get('categorie', 'FORCE'),
            muscle_principal=data.get('muscle_principal', ''),
            video_url=data.get('video_url', '')
        )
        return Response({"id": ex.id, "nom": ex.nom}, status=201)

@api_view(['PUT', 'DELETE'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_exercice_detail(request, pk):
    try:
        ex = Exercice.objects.get(pk=pk)
    except Exercice.DoesNotExist:
        return Response({"error": "Introuvable"}, status=404)
        
    if request.method == 'PUT':
        data = request.data
        ex.nom = data.get('nom', ex.nom)
        ex.description = data.get('description', ex.description)
        ex.categorie = data.get('categorie', ex.categorie)
        ex.muscle_principal = data.get('muscle_principal', ex.muscle_principal)
        ex.video_url = data.get('video_url', ex.video_url)
        ex.save()
        return Response({"message": "Mis à jour"})
        
    elif request.method == 'DELETE':
        ex.delete()
        return Response({"message": "Supprimé"}, status=204)

# --- CATALOGUE : CATEGORIES BOUTIQUE ---
@api_view(['GET', 'POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_category_list_create(request):
    if request.method == 'GET':
        cats = CategorieProduit.objects.all().order_by('-id')
        data = [{"id": c.id, "nom": c.nom, "slug": c.slug} for c in cats]
        return Response(data)
        
    elif request.method == 'POST':
        nom = request.data.get('nom')
        if not nom: return Response({"error": "Nom requis"}, status=400)
        slug = slugify(nom)
        if CategorieProduit.objects.filter(slug=slug).exists():
            slug = f"{slug}-{CategorieProduit.objects.count() + 1}"
        cat = CategorieProduit.objects.create(nom=nom, slug=slug)
        return Response({"id": cat.id, "nom": cat.nom, "slug": cat.slug}, status=201)

@api_view(['DELETE'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_category_delete(request, pk):
    try:
        cat = CategorieProduit.objects.get(pk=pk)
        cat.delete()
        return Response(status=204)
    except CategorieProduit.DoesNotExist:
        return Response(status=404)    
# --- GESTION UTILISATEURS ---
@api_view(['PATCH'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_update_user(request, pk):
    try:
        user = User.objects.get(pk=pk)
        data = request.data
        user.first_name = data.get('first_name', user.first_name)
        user.last_name = data.get('last_name', user.last_name)
        user.email = data.get('email', user.email)
        user.save()
        return Response({"message": "Utilisateur mis à jour"})
    except User.DoesNotExist:
        return Response({"error": "Introuvable"}, status=404)

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_change_password(request, pk):
    try:
        user = User.objects.get(pk=pk)
        pwd = request.data.get('password')
        if not pwd: return Response({"error": "Manquant"}, status=400)
        user.password = make_password(pwd)
        user.save()
        return Response({"message": "Mot de passe changé"})
    except User.DoesNotExist:
        return Response({"error": "Introuvable"}, status=404)

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_toggle_user_status(request, pk):
    try:
        user = User.objects.get(id=pk)
        action = request.data.get('action')
        user.is_active = (action in ['activate', 'validate'])
        user.save()
        return Response({"status": "Validated" if user.is_active else "Suspended"})
    except User.DoesNotExist:
        return Response({"error": "Introuvable"}, status=404)

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_coach_list(request):
    coaches = User.objects.filter(coach_profile__isnull=False).select_related('coach_profile')
    data = []
    
    for u in coaches:
        coach_profile = u.coach_profile
        
        # 1. Nombre d'athlètes affiliés à ce coach
        nb_clients = coach_profile.clients.count()
        
        # 2. Revenus générés (Somme des commandes 'PAID' pour ce coach)
        revenus = Commande.objects.filter(
            coach=coach_profile, 
            status='PAID'
        ).aggregate(total=Sum('montant_ttc'))['total'] or 0.0
        
        # 3. Note moyenne
        note_moyenne = coach_profile.avis.aggregate(avg=Avg('note'))['avg'] or 0.0

        # Détermination du statut
        # Si le user n'est pas actif, on le considère comme 'Pending' (En attente KYC)
        status = "Validated" if u.is_active else "Pending"

        data.append({
            "id": u.id, 
            "first_name": u.first_name, 
            "last_name": u.last_name,
            "name": f"{u.first_name} {u.last_name}".strip() or u.email, 
            "email": u.email,
            "status": status,
            "nb_clients": nb_clients,
            "revenus": round(revenus, 2),
            "note": round(note_moyenne, 1)
        })
        
    # On trie par revenus décroissants par défaut
    data.sort(key=lambda x: x['revenus'], reverse=True)
    return Response(data)

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_athlete_list(request):
    # On récupère les clients avec leurs infos user et coach pour optimiser la requête
    clients = Client.objects.select_related('user', 'coach__user').all().order_by('-date_creation')
    data = []
    for c in clients:
        coach_name = "Aucun"
        if c.coach and c.coach.user:
            coach_name = f"{c.coach.user.first_name} {c.coach.user.last_name}".strip() or c.coach.user.username
            
        data.append({
            "id": c.user.id,
            "client_id": c.id,
            "name": f"{c.prenom} {c.nom}",
            "email": c.email,
            "coach_name": coach_name,
            "status": "Active" if c.user.is_active else "Inactive",
            "date_creation": c.date_creation.strftime("%d/%m/%Y")
        })
    return Response(data)

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_prospect_list(request):
    devis = Devis.objects.select_related('coach__user').all().order_by('-date_creation')
    data = []
    for d in devis:
        coach_name = "Inconnu"
        if d.coach and d.coach.user:
            coach_name = f"{d.coach.user.first_name} {d.coach.user.last_name}".strip() or d.coach.user.username
            
        data.append({
            "id": d.id,
            "name": f"{d.prenom} {d.nom}",
            "email": d.email,
            "coach_name": coach_name,
            "statut": d.statut, # ex: 'en_attente'
            "date_creation": d.date_creation.strftime("%d/%m/%Y")
        })
    return Response(data)

@api_view(['DELETE'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_delete_prospect(request, pk):
    Devis.objects.filter(id=pk).delete()
    return Response({"message": "Prospect supprimé"}, status=204)
@api_view(['DELETE'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_delete_athlete(request, pk):
    User.objects.filter(id=pk, client_profile__isnull=False).delete()
    return Response({"message": "Supprimé"})

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_force_logout(request, pk):
    # Pour l'instant, on retourne un succès simple. 
    # (L'invalidation réelle nécessite la table de blacklistage JWT)
    return Response({"message": "Déconnecté"})

@api_view(['GET', 'PATCH'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_me_view(request):
    user = request.user
    if request.method == 'GET':
        return Response({
            "id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
        })
    
    elif request.method == 'PATCH':
        data = request.data
        user.first_name = data.get('first_name', user.first_name)
        user.last_name = data.get('last_name', user.last_name)
        user.email = data.get('email', user.email)
        user.save()
        return Response({
            "message": "Profil mis à jour",
            "user": {
                "name": f"{user.first_name} {user.last_name}".strip(),
                "email": user.email
            }
        })

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsSystemAdmin])
def admin_change_my_password(request):
    user = request.user
    old_password = request.data.get('old_password')
    new_password = request.data.get('new_password')
    
    if not user.check_password(old_password):
        return Response({"error": "Ancien mot de passe incorrect"}, status=400)
    
    user.set_password(new_password)
    user.save()
    return Response({"message": "Mot de passe modifié avec succès"})