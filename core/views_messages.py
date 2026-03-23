from django.contrib.auth.models import User
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Client,
    Conversation,
    ConversationParticipant,
    Message,
    MessageAttachment,
)
from .serializers_messages import (
    ContactSerializer,
    ConversationSerializer,
    ConversationDetailSerializer,
    MessageSerializer,
)


def user_can_use_messaging(user):
    return bool(
        user
        and user.is_authenticated
        and (hasattr(user, 'coach_profile') or hasattr(user, 'client_profile'))
    )


def get_user_role(user):
    if hasattr(user, 'coach_profile'):
        return 'coach'
    if hasattr(user, 'client_profile'):
        return 'athlete'
    return 'unknown'


def get_allowed_contact_ids_for_user(user):
    role = get_user_role(user)

    if role == 'coach':
        return set(
            Client.objects.filter(
                coach=user.coach_profile,
                user__isnull=False
            ).values_list('user_id', flat=True)
        )

    if role == 'athlete':
        ids = set()
        if user.client_profile.coach and user.client_profile.coach.user:
            ids.add(user.client_profile.coach.user.id)
        return ids

    return set()


def get_conversation_for_user(conversation_id, user):
    conversation = get_object_or_404(
        Conversation.objects.prefetch_related(
            'participants__user',
            'messages__attachments'
        ),
        id=conversation_id
    )

    if not conversation.participants.filter(user=user).exists():
        return None

    return conversation


class MessagingAccessMixin:
    permission_classes = [IsAuthenticated]

    def check_messaging_access(self, request):
        if not user_can_use_messaging(request.user):
            return Response(
                {"detail": "La messagerie est réservée aux coachs et aux athlètes."},
                status=status.HTTP_403_FORBIDDEN
            )
        return None


class AvailableContactsView(MessagingAccessMixin, APIView):
    def get(self, request):
        denied = self.check_messaging_access(request)
        if denied:
            return denied

        allowed_ids = get_allowed_contact_ids_for_user(request.user)
        contacts = User.objects.filter(id__in=allowed_ids).order_by('first_name', 'last_name', 'username')

        serializer = ContactSerializer(contacts, many=True)
        return Response(serializer.data)


class ConversationListCreateView(MessagingAccessMixin, APIView):
    parser_classes = [JSONParser]

    def get(self, request):
        denied = self.check_messaging_access(request)
        if denied:
            return denied

        conversations = (
            Conversation.objects
            .filter(participants__user=request.user)
            .distinct()
            .prefetch_related('participants__user', 'messages__attachments')
            .order_by('-updated_at', '-created_at')
        )

        serializer = ConversationSerializer(conversations, many=True, context={'request': request})
        return Response(serializer.data)

    @transaction.atomic
    def post(self, request):
        denied = self.check_messaging_access(request)
        if denied:
            return denied

        user = request.user
        conversation_type = request.data.get('type', 'direct')
        title = (request.data.get('title') or '').strip()
        participant_ids = request.data.get('participant_ids', [])

        if not isinstance(participant_ids, list):
            return Response({"detail": "participant_ids doit être une liste."}, status=status.HTTP_400_BAD_REQUEST)

        cleaned_ids = []
        for pid in participant_ids:
            try:
                pid_int = int(pid)
                if pid_int != user.id:
                    cleaned_ids.append(pid_int)
            except (ValueError, TypeError):
                continue

        participant_ids = list(set(cleaned_ids))

        if not participant_ids:
            return Response({"detail": "Aucun participant valide sélectionné."}, status=status.HTTP_400_BAD_REQUEST)

        selected_users = list(User.objects.filter(id__in=participant_ids))
        if len(selected_users) != len(participant_ids):
            return Response({"detail": "Un ou plusieurs participants sont introuvables."}, status=status.HTTP_400_BAD_REQUEST)

        allowed_ids = get_allowed_contact_ids_for_user(user)
        if not set(participant_ids).issubset(allowed_ids):
            return Response({"detail": "Certains participants ne sont pas autorisés."}, status=status.HTTP_403_FORBIDDEN)

        if conversation_type == 'direct':
            if len(participant_ids) != 1:
                return Response({"detail": "Une conversation directe doit contenir un seul participant."}, status=status.HTTP_400_BAD_REQUEST)

            other_user_id = participant_ids[0]

            existing_conversations = (
                Conversation.objects
                .filter(conversation_type='direct', participants__user=user)
                .distinct()
                .prefetch_related('participants__user', 'messages__attachments')
            )

            for conversation in existing_conversations:
                current_ids = set(conversation.participants.values_list('user_id', flat=True))
                if current_ids == {user.id, other_user_id}:
                    serializer = ConversationSerializer(conversation, context={'request': request})
                    return Response(serializer.data, status=status.HTTP_200_OK)

            conversation = Conversation.objects.create(
                conversation_type='direct',
                created_by=user
            )
            ConversationParticipant.objects.create(conversation=conversation, user=user)
            ConversationParticipant.objects.create(conversation=conversation, user_id=other_user_id)

        elif conversation_type == 'group':
            # IMPORTANT : seuls les coachs peuvent créer un groupe
            if not hasattr(user, 'coach_profile'):
                return Response(
                    {"detail": "Seul un coach peut créer une conversation de groupe."},
                    status=status.HTTP_403_FORBIDDEN
                )

            if not title:
                return Response({"detail": "Le titre du groupe est obligatoire."}, status=status.HTTP_400_BAD_REQUEST)

            conversation = Conversation.objects.create(
                conversation_type='group',
                title=title,
                created_by=user
            )
            ConversationParticipant.objects.create(conversation=conversation, user=user)

            for participant_id in participant_ids:
                ConversationParticipant.objects.create(conversation=conversation, user_id=participant_id)
        else:
            return Response({"detail": "Type de conversation invalide."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = ConversationSerializer(conversation, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ConversationDetailView(MessagingAccessMixin, APIView):
    parser_classes = [JSONParser]

    def get(self, request, conversation_id):
        denied = self.check_messaging_access(request)
        if denied:
            return denied

        conversation = get_conversation_for_user(conversation_id, request.user)
        if not conversation:
            return Response({"detail": "Conversation introuvable."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ConversationDetailSerializer(conversation, context={'request': request})
        return Response(serializer.data)

    def patch(self, request, conversation_id):
        denied = self.check_messaging_access(request)
        if denied:
            return denied

        conversation = get_conversation_for_user(conversation_id, request.user)
        if not conversation:
            return Response({"detail": "Conversation introuvable."}, status=status.HTTP_404_NOT_FOUND)

        if conversation.conversation_type != 'group':
            return Response({"detail": "Seuls les groupes peuvent être renommés."}, status=status.HTTP_400_BAD_REQUEST)

        if conversation.created_by != request.user:
            return Response({"detail": "Seul le créateur du groupe peut le renommer."}, status=status.HTTP_403_FORBIDDEN)

        title = (request.data.get('title') or '').strip()
        if not title:
            return Response({"detail": "Le titre est obligatoire."}, status=status.HTTP_400_BAD_REQUEST)

        conversation.title = title
        conversation.save(update_fields=['title', 'updated_at'])

        serializer = ConversationDetailSerializer(conversation, context={'request': request})
        return Response(serializer.data)

    def delete(self, request, conversation_id):
        denied = self.check_messaging_access(request)
        if denied:
            return denied

        conversation = get_conversation_for_user(conversation_id, request.user)
        if not conversation:
            return Response({"detail": "Conversation introuvable."}, status=status.HTTP_404_NOT_FOUND)

        if conversation.conversation_type == 'group':
            if conversation.created_by != request.user:
                return Response({"detail": "Seul le créateur du groupe peut le supprimer."}, status=status.HTTP_403_FORBIDDEN)
            conversation.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        conversation.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ConversationMembersView(MessagingAccessMixin, APIView):
    parser_classes = [JSONParser]

    @transaction.atomic
    def post(self, request, conversation_id):
        denied = self.check_messaging_access(request)
        if denied:
            return denied

        conversation = get_conversation_for_user(conversation_id, request.user)
        if not conversation:
            return Response({"detail": "Conversation introuvable."}, status=status.HTTP_404_NOT_FOUND)

        if conversation.conversation_type != 'group':
            return Response({"detail": "Action réservée aux groupes."}, status=status.HTTP_400_BAD_REQUEST)

        if conversation.created_by != request.user:
            return Response({"detail": "Seul le créateur du groupe peut ajouter des membres."}, status=status.HTTP_403_FORBIDDEN)

        participant_ids = request.data.get('participant_ids', [])
        if not isinstance(participant_ids, list):
            return Response({"detail": "participant_ids doit être une liste."}, status=status.HTTP_400_BAD_REQUEST)

        cleaned_ids = []
        for pid in participant_ids:
            try:
                pid_int = int(pid)
                if pid_int != request.user.id:
                    cleaned_ids.append(pid_int)
            except (TypeError, ValueError):
                continue

        participant_ids = list(set(cleaned_ids))
        if not participant_ids:
            return Response({"detail": "Aucun participant valide."}, status=status.HTTP_400_BAD_REQUEST)

        allowed_ids = get_allowed_contact_ids_for_user(request.user)
        if not set(participant_ids).issubset(allowed_ids):
            return Response({"detail": "Certains participants ne sont pas autorisés."}, status=status.HTTP_403_FORBIDDEN)

        existing_ids = set(conversation.participants.values_list('user_id', flat=True))

        for participant_id in participant_ids:
            if participant_id not in existing_ids:
                ConversationParticipant.objects.create(
                    conversation=conversation,
                    user_id=participant_id
                )

        conversation.save(update_fields=['updated_at'])

        serializer = ConversationDetailSerializer(conversation, context={'request': request})
        return Response(serializer.data)


class ConversationMemberDeleteView(MessagingAccessMixin, APIView):
    def delete(self, request, conversation_id, user_id):
        denied = self.check_messaging_access(request)
        if denied:
            return denied

        conversation = get_conversation_for_user(conversation_id, request.user)
        if not conversation:
            return Response({"detail": "Conversation introuvable."}, status=status.HTTP_404_NOT_FOUND)

        if conversation.conversation_type != 'group':
            return Response({"detail": "Action réservée aux groupes."}, status=status.HTTP_400_BAD_REQUEST)

        if conversation.created_by != request.user:
            return Response({"detail": "Seul le créateur du groupe peut retirer un membre."}, status=status.HTTP_403_FORBIDDEN)

        if int(user_id) == request.user.id:
            return Response({"detail": "Le créateur ne peut pas être retiré du groupe."}, status=status.HTTP_400_BAD_REQUEST)

        participant = conversation.participants.filter(user_id=user_id).first()
        if not participant:
            return Response({"detail": "Membre introuvable dans ce groupe."}, status=status.HTTP_404_NOT_FOUND)

        participant.delete()
        conversation.save(update_fields=['updated_at'])

        serializer = ConversationDetailSerializer(conversation, context={'request': request})
        return Response(serializer.data)


class ConversationMessagesView(MessagingAccessMixin, APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request, conversation_id):
        denied = self.check_messaging_access(request)
        if denied:
            return denied

        conversation = get_conversation_for_user(conversation_id, request.user)
        if not conversation:
            return Response({"detail": "Conversation introuvable."}, status=status.HTTP_404_NOT_FOUND)

        messages = (
            conversation.messages
            .filter(is_deleted=False)
            .select_related('sender')
            .prefetch_related('attachments')
            .order_by('created_at')
        )
        serializer = MessageSerializer(messages, many=True, context={'request': request})
        return Response(serializer.data)

    @transaction.atomic
    def post(self, request, conversation_id):
        denied = self.check_messaging_access(request)
        if denied:
            return denied

        conversation = get_conversation_for_user(conversation_id, request.user)
        if not conversation:
            return Response({"detail": "Conversation introuvable."}, status=status.HTTP_404_NOT_FOUND)

        content = (request.data.get('content') or '').strip()
        files = request.FILES.getlist('files')

        if not content and not files:
            return Response(
                {"detail": "Le message doit contenir un texte ou au moins un fichier."},
                status=status.HTTP_400_BAD_REQUEST
            )

        message = Message.objects.create(
            conversation=conversation,
            sender=request.user,
            content=content
        )

        for uploaded_file in files:
            MessageAttachment.objects.create(
                message=message,
                file=uploaded_file,
                original_name=uploaded_file.name
            )

        conversation.save(update_fields=['updated_at'])

        serializer = MessageSerializer(message, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ConversationReadView(MessagingAccessMixin, APIView):
    def post(self, request, conversation_id):
        denied = self.check_messaging_access(request)
        if denied:
            return denied

        conversation = get_conversation_for_user(conversation_id, request.user)
        if not conversation:
            return Response({"detail": "Conversation introuvable."}, status=status.HTTP_404_NOT_FOUND)

        participant = conversation.participants.filter(user=request.user).first()
        if not participant:
            return Response({"detail": "Participant introuvable."}, status=status.HTTP_404_NOT_FOUND)

        participant.last_read_at = timezone.now()
        participant.save(update_fields=['last_read_at'])

        return Response({"status": "ok"})