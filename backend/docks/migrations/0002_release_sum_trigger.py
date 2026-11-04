from django.db import migrations

from config.pg import run_pg

# Domain rule 5: sum(pieces_released) <= pieces_total. The request row is locked first so that
# two docks releasing the same request concurrently are serialised.
SQL = """
CREATE OR REPLACE FUNCTION release_operations_check_sum() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    total integer;
    released bigint;
BEGIN
    SELECT pieces_total INTO total FROM queue_requests WHERE id = NEW.request_id FOR UPDATE;
    SELECT COALESCE(SUM(pieces_released), 0) INTO released
        FROM release_operations WHERE request_id = NEW.request_id;
    IF released > total THEN
        RAISE EXCEPTION 'RELEASE_EXCEEDS_TOTAL' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER release_operations_sum_limit
    AFTER INSERT OR UPDATE OF pieces_released, request_id ON release_operations
    FOR EACH ROW EXECUTE FUNCTION release_operations_check_sum();
"""

REVERSE = """
DROP TRIGGER IF EXISTS release_operations_sum_limit ON release_operations;
DROP FUNCTION IF EXISTS release_operations_check_sum();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("docks", "0001_initial"),
        ("cargo_queue", "0002_initial"),
    ]
    operations = [run_pg(SQL, REVERSE)]
