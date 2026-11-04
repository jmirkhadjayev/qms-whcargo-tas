from django.db import migrations

from config.pg import run_pg

# Domain rules 1 and 3 enforced inside PostgreSQL (the service layer checks them as well).
SQL = """
-- Rule 3: the status history only ever grows.
CREATE TRIGGER request_status_history_append_only
    BEFORE UPDATE OR DELETE ON request_status_history
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

-- Rule 3: requests are never deleted (they go to CANCELLED).
CREATE TRIGGER queue_requests_no_delete
    BEFORE DELETE ON queue_requests
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

-- Rule 1: no request without a verified, valid permit for the same AWB.
CREATE OR REPLACE FUNCTION queue_requests_check_permit() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    p release_permits%ROWTYPE;
BEGIN
    SELECT * INTO p FROM release_permits WHERE id = NEW.permit_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'PERMIT_MISSING' USING ERRCODE = 'check_violation';
    END IF;
    IF p.status <> 'VERIFIED' THEN
        RAISE EXCEPTION 'PERMIT_NOT_VERIFIED' USING ERRCODE = 'check_violation';
    END IF;
    IF p.valid_until IS NOT NULL AND p.valid_until < now() THEN
        RAISE EXCEPTION 'PERMIT_EXPIRED' USING ERRCODE = 'check_violation';
    END IF;
    IF p.awb_number <> NEW.awb_number THEN
        RAISE EXCEPTION 'PERMIT_AWB_MISMATCH' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER queue_requests_permit_required
    BEFORE INSERT ON queue_requests
    FOR EACH ROW EXECUTE FUNCTION queue_requests_check_permit();
"""

REVERSE = """
DROP TRIGGER IF EXISTS queue_requests_permit_required ON queue_requests;
DROP FUNCTION IF EXISTS queue_requests_check_permit();
DROP TRIGGER IF EXISTS queue_requests_no_delete ON queue_requests;
DROP TRIGGER IF EXISTS request_status_history_append_only ON request_status_history;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("cargo_queue", "0002_initial"),
        ("audit", "0002_append_only_trigger"),
    ]
    operations = [run_pg(SQL, REVERSE)]
