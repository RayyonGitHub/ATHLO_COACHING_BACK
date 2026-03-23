from django.contrib.auth.models import User
from rest_framework import serializers

from .models import (
    Conversation,
    Message,
    MessageAttachment,
)


def get_user_role_label(user):
    if hasattr(user, 'coach_profile'):
        return "Coach"
    if hasattr(user, 'client_profile'):
        return "Athlète"
    return "Utilisateur"


def get_user_display_name(user):
    full_name = f"{user.first_name} {user.last_name}".strip()
    return full_name or user.username or user.email


class ContactSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    role_label = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'name', 'email', 'role_label']

    def get_name(self, obj):
        return get_user_display_name(obj)

    def get_role_label(self, obj):
        return get_user_role_label(obj)


class ConversationMemberSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    role_label = serializers.SerializerMethodField()
    is_current_user = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'name', 'email', 'role_label', 'is_current_user']

    def get_name(self, obj):
        return get_user_display_name(obj)

    def get_role_label(self, obj):
        return get_user_role_label(obj)

    def get_is_current_user(self, obj):
        request = self.context.get('request')
        return bool(request and request.user.id == obj.id)


class MessageAttachmentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    file_name = serializers.SerializerMethodField()
    is_image = serializers.ReadOnlyField()

    class Meta:
        model = MessageAttachment
        fields = ['id', 'file_url', 'file_name', 'is_image']

    def get_file_url(self, obj):
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url

    def get_file_name(self, obj):
        return obj.original_name


class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()
    is_own_message = serializers.SerializerMethodField()
    is_read = serializers.SerializerMethodField()
    attachments = MessageAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = Message
        fields = [
            'id',
            'sender',
            'sender_name',
            'content',
            'created_at',
            'is_own_message',
            'is_read',
            'attachments',
        ]
        read_only_fields = [
            'id',
            'sender',
            'sender_name',
            'created_at',
            'is_own_message',
            'is_read',
            'attachments',
        ]

    def get_sender_name(self, obj):
        return get_user_display_name(obj.sender)

    def get_is_own_message(self, obj):
        request = self.context.get('request')
        return bool(request and request.user == obj.sender)

    def get_is_read(self, obj):
        request = self.context.get('request')
        if not request:
            return False

        participant = obj.conversation.participants.filter(user=request.user).first()
        if not participant or not participant.last_read_at:
            return False

        return obj.created_at <= participant.last_read_at


class ConversationSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    subtitle = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    last_message_time = serializers.SerializerMethodField()
    is_group = serializers.SerializerMethodField()
    is_online = serializers.SerializerMethodField()
    members = serializers.SerializerMethodField()
    can_manage_group = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            'id',
            'title',
            'conversation_type',
            'is_group',
            'display_name',
            'subtitle',
            'unread_count',
            'last_message',
            'last_message_time',
            'updated_at',
            'is_online',
            'members',
            'can_manage_group',
        ]

    def _get_other_participant(self, obj):
        request = self.context.get('request')
        if not request:
            return None
        return obj.participants.exclude(user=request.user).select_related('user').first()

    def get_display_name(self, obj):
        if obj.conversation_type == 'group':
            return obj.title or "Groupe"

        other = self._get_other_participant(obj)
        if not other:
            return "Conversation"
        return get_user_display_name(other.user)

    def get_subtitle(self, obj):
        if obj.conversation_type == 'group':
            count = obj.participants.count()
            return f"{count} participants"

        other = self._get_other_participant(obj)
        if not other:
            return "Conversation directe"
        return get_user_role_label(other.user)

    def get_unread_count(self, obj):
        request = self.context.get('request')
        if not request:
            return 0

        participant = obj.participants.filter(user=request.user).first()
        if not participant:
            return 0

        queryset = obj.messages.filter(is_deleted=False).exclude(sender=request.user)

        if participant.last_read_at:
            queryset = queryset.filter(created_at__gt=participant.last_read_at)

        return queryset.count()

    def get_last_message(self, obj):
        last_message = obj.messages.filter(is_deleted=False).order_by('-created_at').first()
        if not last_message:
            return ""

        if last_message.content:
            return last_message.content

        if last_message.attachments.exists():
            return "Pièce jointe"

        return ""

    def get_last_message_time(self, obj):
        last_message = obj.messages.filter(is_deleted=False).order_by('-created_at').first()
        return last_message.created_at if last_message else None

    def get_is_group(self, obj):
        return obj.conversation_type == 'group'

    def get_is_online(self, obj):
        return False

    def get_members(self, obj):
        users = User.objects.filter(message_conversations__conversation=obj).distinct()
        serializer = ConversationMemberSerializer(users, many=True, context=self.context)
        return serializer.data

    def get_can_manage_group(self, obj):
        request = self.context.get('request')
        if not request:
            return False
        return obj.conversation_type == 'group' and obj.created_by_id == request.user.id


class ConversationDetailSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    subtitle = serializers.SerializerMethodField()
    is_group = serializers.SerializerMethodField()
    members = serializers.SerializerMethodField()
    can_manage_group = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            'id',
            'title',
            'conversation_type',
            'display_name',
            'subtitle',
            'is_group',
            'members',
            'created_at',
            'updated_at',
            'can_manage_group',
        ]

    def _get_other_participant(self, obj):
        request = self.context.get('request')
        if not request:
            return None
        return obj.participants.exclude(user=request.user).select_related('user').first()

    def get_display_name(self, obj):
        if obj.conversation_type == 'group':
            return obj.title or "Groupe"

        other = self._get_other_participant(obj)
        if not other:
            return "Conversation"
        return get_user_display_name(other.user)

    def get_subtitle(self, obj):
        if obj.conversation_type == 'group':
            return f"{obj.participants.count()} participants"

        other = self._get_other_participant(obj)
        if not other:
            return "Conversation directe"
        return get_user_role_label(other.user)

    def get_is_group(self, obj):
        return obj.conversation_type == 'group'

    def get_members(self, obj):
        users = User.objects.filter(message_conversations__conversation=obj).distinct()
        serializer = ConversationMemberSerializer(users, many=True, context=self.context)
        return serializer.data

    def get_can_manage_group(self, obj):
        request = self.context.get('request')
        if not request:
            return False
        return obj.conversation_type == 'group' and obj.created_by_id == request.user.id