from rest_framework import serializers


class OpenProblemSerializer(serializers.Serializer):
    kind = serializers.CharField()
    description = serializers.CharField(allow_blank=True)


class CheckSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    queue_number = serializers.IntegerField()
    awb_number = serializers.CharField()
    consignee_name = serializers.CharField()
    category = serializers.CharField()
    special_handling = serializers.BooleanField()
    vehicle_plate = serializers.CharField(allow_blank=True)
    pieces_total = serializers.IntegerField()
    pieces_released = serializers.IntegerField()
    pieces_remaining = serializers.IntegerField()
    weight_kg = serializers.DecimalField(max_digits=10, decimal_places=2)
    status = serializers.CharField()
    dock = serializers.CharField(allow_null=True)
    can_confirm = serializers.BooleanField()
    blocked_reason = serializers.CharField(allow_blank=True)
    open_problems = OpenProblemSerializer(many=True)


class ConfirmSerializer(serializers.Serializer):
    plate_observed = serializers.CharField(max_length=20, required=False, allow_blank=True)


class HoldSerializer(serializers.Serializer):
    description = serializers.CharField(max_length=2000)
    plate_observed = serializers.CharField(max_length=20, required=False, allow_blank=True)


class WaitingSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    queue_number = serializers.IntegerField()
    vehicle_plate = serializers.CharField(allow_blank=True)
    pieces_released = serializers.IntegerField()
    pieces_total = serializers.IntegerField()
    is_partial = serializers.BooleanField()


class RecentPassSerializer(serializers.Serializer):
    queue_number = serializers.IntegerField()
    result = serializers.ChoiceField(choices=["APPROVED", "HELD"])
    scanned_at = serializers.DateTimeField()
    officer = serializers.CharField()


class CheckpointOverviewSerializer(serializers.Serializer):
    waiting = WaitingSerializer(many=True)
    recent = RecentPassSerializer(many=True)
