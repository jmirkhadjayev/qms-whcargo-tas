import datetime as dt

from django.db import connection, transaction


def next_queue_number(queue_date: dt.date) -> int:
    """Race-free daily counter (domain rule 4, decision K7).

    One atomic upsert takes a row lock on the day's counter and holds it until the surrounding
    transaction ends, so concurrent registrations queue up instead of getting the same number.
    A rolled-back registration also rolls back its increment, so numbers have no gaps.
    """
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO queue_counters (queue_date, last_number) VALUES (%s, 1)
            ON CONFLICT (queue_date) DO UPDATE SET last_number = queue_counters.last_number + 1
            RETURNING last_number
            """,
            [queue_date],
        )
        return cursor.fetchone()[0]
