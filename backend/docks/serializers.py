from rest_framework import serializers

from docks.models import DockState


class DockRequestSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    queue_number = serializers.IntegerField()
    status = serializers.CharField()
    vehicle_plate = serializers.CharField(allow_blank=True)
    category = serializers.CharField()


class DockCardSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    name = serializers.CharField()
    state = serializers.ChoiceField(choices=DockState.choices)
    is_active = serializers.BooleanField()
    categories = serializers.ListField(child=serializers.CharField())
    agent = serializers.CharField(allow_null=True)
    agent_ready = serializers.BooleanField()
    request = DockRequestSerializer(allow_null=True)


class KpiSerializer(serializers.Serializer):
    registered_today = serializers.IntegerField()
    in_preparation = serializers.IntegerField()
    waiting_dock = serializers.IntegerField()
    at_dock = serializers.IntegerField()
    completed_today = serializers.IntegerField()
    open_exceptions = serializers.IntegerField()
    avg_wait_minutes = serializers.IntegerField(allow_null=True)


class OverviewSerializer(serializers.Serializer):
    kpi = KpiSerializer()
    docks = DockCardSerializer(many=True)


class QueueRowSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    queue_number = serializers.IntegerField()
    awb_number = serializers.CharField()
    consignee_name = serializers.CharField()
    category = serializers.CharField()
    special_handling = serializers.BooleanField()
    status = serializers.CharField()
    priority = serializers.IntegerField()
    dock = serializers.CharField(allow_null=True)
    pieces_total = serializers.IntegerField()
    vehicle_plate = serializers.CharField(allow_blank=True)
    wait_minutes = serializers.IntegerField()
    task_status = serializers.CharField(allow_null=True)
    free_docks = serializers.ListField(child=serializers.CharField())
    attempts = serializers.IntegerField()
    recalls_left = serializers.IntegerField()
    call_blockers = serializers.ListField(child=serializers.CharField())
    remaining_pieces = serializers.IntegerField()
    suspended_from = serializers.CharField(allow_null=True)


class DockStateSerializer(serializers.Serializer):
    maintenance = serializers.BooleanField()


class CheckInSerializer(serializers.Serializer):
    dock = serializers.CharField(max_length=10)


class AgentDockSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    state = serializers.CharField()
    ready_since = serializers.DateTimeField(allow_null=True)


class AgentHistorySerializer(serializers.Serializer):
    from_status = serializers.CharField(allow_null=True)
    to_status = serializers.CharField()
    changed_at = serializers.DateTimeField()


class AgentCurrentSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    queue_number = serializers.IntegerField()
    awb_number = serializers.CharField()
    consignee_name = serializers.CharField()
    representative_name = serializers.CharField(allow_blank=True)
    category = serializers.CharField()
    special_handling = serializers.BooleanField()
    pieces_total = serializers.IntegerField()
    weight_kg = serializers.DecimalField(max_digits=10, decimal_places=2)
    vehicle_plate = serializers.CharField(allow_blank=True)
    notes = serializers.CharField(allow_blank=True)
    status = serializers.CharField()
    attempt_no = serializers.IntegerField()
    recalls_left = serializers.IntegerField()
    timeout_at = serializers.DateTimeField(allow_null=True)
    blockers = serializers.ListField(child=serializers.CharField())
    pieces_released = serializers.IntegerField()
    pieces_remaining = serializers.IntegerField()
    operation_pieces = serializers.IntegerField()
    history = AgentHistorySerializer(many=True)


class AgentNextSerializer(serializers.Serializer):
    queue_number = serializers.IntegerField()
    category = serializers.CharField()
    vehicle_plate = serializers.CharField(allow_blank=True)
    wait_minutes = serializers.IntegerField()


class AvailableDockSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    categories = serializers.ListField(child=serializers.CharField())


class AgentScreenSerializer(serializers.Serializer):
    dock = AgentDockSerializer(allow_null=True)
    current = AgentCurrentSerializer(allow_null=True)
    next = AgentNextSerializer(many=True)
    available_docks = AvailableDockSerializer(many=True)


class ScanResultSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    queue_number = serializers.IntegerField()
    status = serializers.CharField()


# Public screens: only these fields ever leave the server (domain rule 7).
class HallCalledSerializer(serializers.Serializer):
    queue_number = serializers.IntegerField()
    dock = serializers.CharField()
    vehicle_plate = serializers.CharField(allow_blank=True)
    recall = serializers.BooleanField()


class HallPreparingSerializer(serializers.Serializer):
    queue_number = serializers.IntegerField()


class HallSerializer(serializers.Serializer):
    called = HallCalledSerializer(many=True)
    preparing = HallPreparingSerializer(many=True)


class LedCurrentSerializer(serializers.Serializer):
    queue_number = serializers.IntegerField()
    vehicle_plate = serializers.CharField(allow_blank=True)
    phase = serializers.ChoiceField(choices=["CALLING", "SERVING"])
    recall = serializers.BooleanField()


class LedSerializer(serializers.Serializer):
    dock = serializers.CharField()
    state = serializers.CharField()
    current = LedCurrentSerializer(allow_null=True)
