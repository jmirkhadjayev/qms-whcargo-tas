from rest_framework import serializers

from exceptions_app.models import ExceptionKind, ExceptionRecord


class ExceptionSerializer(serializers.ModelSerializer):
    queue_number = serializers.IntegerField(source="request.queue_number", read_only=True)
    request_status = serializers.CharField(source="request.status", read_only=True)
    reported_by = serializers.CharField(
        source="reported_by.full_name", allow_null=True, default=None, read_only=True
    )
    resolved_by = serializers.CharField(
        source="resolved_by.full_name", allow_null=True, default=None, read_only=True
    )

    class Meta:
        model = ExceptionRecord
        fields = [
            "id",
            "request",
            "queue_number",
            "request_status",
            "kind",
            "pieces_affected",
            "description",
            "reported_by",
            "reported_at",
            "resolved_by",
            "resolved_at",
            "resolution",
        ]
        read_only_fields = fields


class ResolveSerializer(serializers.Serializer):
    resolution = serializers.CharField(max_length=2000)


class ReportSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(
        choices=[
            ExceptionKind.MISSING,
            ExceptionKind.DAMAGE,
            ExceptionKind.SHORTAGE,
            ExceptionKind.MISMATCH,
        ]
    )
    description = serializers.CharField(max_length=2000)
    pieces_affected = serializers.IntegerField(min_value=0, required=False, default=0)
