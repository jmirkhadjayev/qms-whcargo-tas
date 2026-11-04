"""Helper for PostgreSQL-only migration steps (triggers). Skipped on other databases."""

from django.db import migrations


def run_pg(sql: str, reverse_sql: str) -> migrations.RunPython:
    def forward(apps, schema_editor):
        if schema_editor.connection.vendor == "postgresql":
            schema_editor.execute(sql, params=None)

    def backward(apps, schema_editor):
        if schema_editor.connection.vendor == "postgresql":
            schema_editor.execute(reverse_sql, params=None)

    return migrations.RunPython(forward, backward)
