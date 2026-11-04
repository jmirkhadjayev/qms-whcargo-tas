from django.db import migrations

from config.pg import run_pg

# Domain rule 3: audit_log accepts INSERT only. The function is shared with other append-only tables.
SQL = """
CREATE OR REPLACE FUNCTION prevent_modification() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'APPEND_ONLY: % on table % is not allowed', TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'restrict_violation';
END;
$$;

CREATE TRIGGER audit_log_append_only
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();
"""

REVERSE = """
DROP TRIGGER IF EXISTS audit_log_append_only ON audit_log;
DROP FUNCTION IF EXISTS prevent_modification();
"""


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]
    operations = [run_pg(SQL, REVERSE)]
