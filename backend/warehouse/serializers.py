from rest_framework import serializers

from exceptions_app.models import ExceptionKind
from warehouse.models import WarehouseTask


class TaskRequestSerializer(serializers.Serializer):
    """The request data a warehouse worker needs (TZ 3.3 task contents)."""

    id = serializers.IntegerField()
    queue_number = serializers.IntegerField()
    awb_number = serializers.CharField()
    pieces_total = serializers.IntegerField()
    weight_kg = serializers.DecimalField(max_digits=10, decimal_places=2)
    category = serializers.CharField(source="category.code")
    category_name = serializers.CharField(source="category.name")
    special_handling = serializers.BooleanField(source="category.special_handling")
    dock = serializers.CharField(source="dock.code", allow_null=True, default=None)
    status = serializers.CharField()
    priority = serializers.IntegerField()
    notes = serializers.CharField(allow_blank=True)
    pieces_remaining = serializers.SerializerMethodField()

    def get_pieces_remaining(self, obj) -> int:
        # Pieces still to hand over (differs from the total in the second cycle).
        from cargo_queue.services.closing import remaining_pieces

        return remaining_pieces(obj)


class WarehouseTaskSerializer(serializers.ModelSerializer):
    request = TaskRequestSerializer(read_only=True)
    assigned_to = serializers.CharField(
        source="assigned_to.full_name", allow_null=True, default=None, read_only=True
    )

    class Meta:
        model = WarehouseTask
        fields = [
            "id",
            "status",
            "storage_location",
            "assigned_to",
            "created_at",
            "started_at",
            "ready_at",
            "handed_over_at",
            "request",
        ]
        read_only_fields = fields


class PaginatedTasksSerializer(serializers.Serializer):
    results = WarehouseTaskSerializer(many=True)


class StartTaskSerializer(serializers.Serializer):
    storage_location = serializers.CharField(max_length=100, required=False, allow_blank=True)


class ProblemSerializer(serializers.Serializer):
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
