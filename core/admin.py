from django.contrib import admin
from .models import (
    CategorieProduit,
    Coach,
    Client,
    ClientInvitation,
    Exercice,
    NotificationAthlete,
    PlanNutritionnel,
    Produit,
    Programme,
    Recette,
    Recette,
    Seance,
    SeanceExercice,
    Inscription,
    Conversation,
    ConversationParticipant,
    Message,
    MessageAttachment,
    Performance,
    Commande,
    LigneCommande, Salle, ResponsableSalle
)

# Profils
admin.site.register(Coach)
admin.site.register(Client)
admin.site.register(ClientInvitation)

# Sport
admin.site.register(Exercice)
admin.site.register(Programme)
admin.site.register(Seance)
admin.site.register(SeanceExercice)
admin.site.register(Performance)

admin.site.register(Recette)
admin.site.register(PlanNutritionnel)

admin.site.register(Salle)
admin.site.register(ResponsableSalle)
@admin.register(Inscription)
class InscriptionAdmin(admin.ModelAdmin):
    list_display = ('client', 'seance', 'statut', 'date_inscription')
    list_filter = ('statut', 'seance__jour_prevu')


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'conversation_type', 'title', 'created_by', 'created_at', 'updated_at')
    list_filter = ('conversation_type',)
    search_fields = ('title', 'created_by__username', 'created_by__email')


@admin.register(ConversationParticipant)
class ConversationParticipantAdmin(admin.ModelAdmin):
    list_display = ('conversation', 'user', 'joined_at', 'last_read_at')
    search_fields = ('user__username', 'user__email', 'conversation__title')


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'conversation', 'sender', 'short_content', 'created_at', 'is_deleted')
    search_fields = ('sender__username', 'sender__email', 'content', 'conversation__title')
    list_filter = ('created_at', 'is_deleted')

    def short_content(self, obj):
        return obj.content[:50] if obj.content else "[Pièce jointe]"


@admin.register(MessageAttachment)
class MessageAttachmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'message', 'original_name', 'uploaded_at')
    search_fields = ('original_name',)


admin.site.register(NotificationAthlete)
# --- NOUVEAU : Gestion des catégories de la boutique ---
@admin.register(CategorieProduit)
class CategorieProduitAdmin(admin.ModelAdmin):
    list_display = ('nom', 'slug')
    # Ceci remplit automatiquement le champ 'slug' en tapant le nom 
    # (ex: "Programmes PDF" -> "programmes-pdf")
    prepopulated_fields = {'slug': ('nom',)} 

@admin.register(Produit)
class ProduitAdmin(admin.ModelAdmin):
    list_display = ('nom', 'coach', 'prix', 'stock', 'est_actif')
    list_filter = ('type_produit', 'categorie', 'est_actif')
    search_fields = ('nom', 'coach__user__username')
    
# --- AJOUTEZ CECI À LA TOUTE FIN DE VOTRE FICHIER admin.py ---

# core/admin.py
@admin.register(Commande)
class CommandeAdmin(admin.ModelAdmin):
    # On remplace 'statut' par 'status' et 'total' par 'montant_ttc'
    list_display = ('order_number', 'client', 'status', 'montant_ttc', 'date_commande')
    list_filter = ('status',)
    search_fields = ('order_number', 'client__user__last_name')
@admin.register(LigneCommande)
class LigneCommandeAdmin(admin.ModelAdmin):
    list_display = ('commande', 'produit', 'quantite', 'prix_unitaire')