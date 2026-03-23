from django.contrib.auth.models import User
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Client, Coach, Conversation, ConversationParticipant, Message
from .serializers_messages import (
    ContactSerializer,
    ConversationSerializer,
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


def get_conversation_for_user(conversation_id, user):
    conversation = get_object_or_404(
        Conversation.objects.prefetch_related('participants__user', 'messages'),
        id=conversation_id
    )

    is_participant = conversation.participants.filter(user=user).exists()
    if not is_participant:
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

        user = request.user
        role = get_user_role(user)

        contacts = User.objects.none()

        if role == 'coach':
            coach_profile = user.coach_profile
            client_user_ids = Client.objects.filter(
                coach=coach_profile,
                user__isnull=False
            ).values_list('user_id', flat=True)
            contacts = User.objects.filter(id__in=client_user_ids).order_by('first_name', 'last_name', 'username')

        elif role == 'athlete':
            client_profile = user.client_profile
            if client_profile.coach and client_profile.coach.user:
                contacts = User.objects.filter(id=client_profile.coach.user.id)

        serializer = ContactSerializer(contacts, many=True)
        return Response(serializer.data)


class ConversationListCreateView(MessagingAccessMixin, APIView):
    def get(self, request):
        denied = self.check_messaging_access(request)
        if denied:
            return denied

        conversations = (
            Conversation.objects
            .filter(participants__user=request.user)
            .distinct()
            .prefetch_related('participants__user', 'messages')
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
            return Response(
                {"detail": "participant_ids doit être une liste."},
                status=status.HTTP_400_BAD_REQUEST
            )

        participant_ids = list(set(int(pid) for pid in participant_ids if str(pid).isdigit()))
        participant_ids = [pid for pid in participant_ids if pid != user.id]

        if not participant_ids:
            return Response(
                {"detail": "Aucun participant valide sélectionné."},
                status=status.HTTP_400_BAD_REQUEST
            )

        selected_users = list(User.objects.filter(id__in=participant_ids))
        if len(selected_users) != len(participant_ids):
            return Response(
                {"detail": "Un ou plusieurs participants sont introuvables."},
                status=status.HTTP_400_BAD_REQUEST
            )

        for selected_user in selected_users:
            if not user_can_use_messaging(selected_user):
                return Response(
                    {"detail": "Tous les participants doivent être coachs ou athlètes."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        current_role = get_user_role(user)

        if current_role == 'coach':
            allowed_user_ids = set(
                Client.objects.filter(
                    coach=user.coach_profile,
                    user__isnull=False
                ).values_list('user_id', flat=True)
            )
        elif current_role == 'athlete':
            allowed_user_ids = set()
            if user.client_profile.coach and user.client_profile.coach.user:
                allowed_user_ids.add(user.client_profile.coach.user.id)
        else:
            allowed_user_ids = set()

        if not set(participant_ids).issubset(allowed_user_ids):
            return Response(
                {"detail": "Certains participants ne sont pas autorisés pour cette conversation."},
                status=status.HTTP_403_FORBIDDEN
            )

        if conversation_type == 'direct':
            if len(participant_ids) != 1:
                return Response(
                    {"detail": "Une conversation directe doit contenir un seul autre participant."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            other_user_id = participant_ids[0]

            existing_conversations = (
                Conversation.objects
                .filter(conversation_type='direct', participants__user=user)
                .distinct()
                .prefetch_related('participants__user', 'messages')
            )

            for conversation in existing_conversations:
                current_ids = set(conversation.participants.values_list('user_id', flat=True))
                if current_ids == {user.id, other_user_id}:
                    serializer = ConversationSerializer(conversation, context={'request': request})
                    return Response(serializer.data, status=status.HTTP_200_OK)

            conversation = Conversation.objects.create(conversation_type='direct', created_by=user)
            ConversationParticipant.objects.create(conversation=conversation, user=user)
            ConversationParticipant.objects.create(conversation=conversation, user_id=other_user_id)

        elif conversation_type == 'group':
            if not title:
                return Response(
                    {"detail": "Le titre du groupe est obligatoire."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            conversation = Conversation.objects.create(
                conversation_type='group',
                title=title,
                created_by=user
            )
            ConversationParticipant.objects.create(conversation=conversation, user=user)

            for participant_id in participant_ids:
                ConversationParticipant.objects.create(
                    conversation=conversation,
                    user_id=participant_id
                )
        else:
            return Response(
                {"detail": "Type de conversation invalide."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = ConversationSerializer(conversation, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ConversationMessagesView(MessagingAccessMixin, APIView):
    def get(self, request, conversation_id):
        denied = self.check_messaging_access(request)
        if denied:
            return denied

        conversation = get_conversation_for_user(conversation_id, request.user)
        if not conversation:
            return Response({"detail": "Conversation introuvable."}, status=status.HTTP_404_NOT_FOUND)

        messages = conversation.messages.select_related('sender').order_by('created_at')
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
        if not content:
            return Response(
                {"detail": "Le contenu du message est obligatoire."},
                status=status.HTTP_400_BAD_REQUEST
            )

        message = Message.objects.create(
            conversation=conversation,
            sender=request.user,
            content=content
        )

        conversation.updated_at = timezone.now()
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