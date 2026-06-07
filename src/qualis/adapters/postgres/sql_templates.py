from __future__ import annotations

# ---------------------------------------------------------------------------
# PostgreSQL SQL templates
# ---------------------------------------------------------------------------
# Column identifiers use double-quoted identifiers to handle reserved keywords
# and special characters. Parameters use %(name)s style (psycopg3 default).
# The ~ operator is the PostgreSQL POSIX regex match operator.

NOT_NULL_SQL = """
SELECT
    COUNT(*) FILTER (WHERE "{column}" IS NULL) AS null_count,
    COUNT(*) AS total_count
FROM {table}
"""

UNIQUE_SQL = """
SELECT COUNT(*) AS duplicate_count
FROM (
    SELECT "{column}"
    FROM {table}
    WHERE "{column}" IS NOT NULL
    GROUP BY "{column}"
    HAVING COUNT(*) > 1
) sub
"""

BETWEEN_SQL = """
SELECT
    COUNT(*) FILTER (
        WHERE "{column}" IS NOT NULL
        AND ("{column}"::text < %(min)s OR "{column}"::text > %(max)s)
    ) AS out_of_range_count,
    COUNT(*) AS total_count,
    COUNT(*) FILTER (WHERE "{column}" IS NOT NULL) AS checked
FROM {table}
"""

REGEX_SQL = """
SELECT
    COUNT(*) FILTER (
        WHERE "{column}" IS NOT NULL
        AND NOT ("{column}"::text ~ %(pattern)s)
    ) AS non_matching_count,
    COUNT(*) AS total_count
FROM {table}
"""

IN_SET_SQL = """
SELECT
    COUNT(*) FILTER (
        WHERE "{column}" IS NULL
        OR NOT ("{column}"::text = ANY(%(values)s))
    ) AS invalid_count,
    COUNT(*) AS total_count
FROM {table}
"""

ROW_COUNT_SQL = """
SELECT COUNT(*) AS row_count FROM {table}
"""

# cross_dataset_assertion aggregates (AgDR-0008). COALESCE keeps an
# empty/all-NULL SUM at 0; ::numeric returns Decimal so the engine's
# tolerance comparison never loses precision to a float cast.
AGGREGATE_ROW_COUNT_SQL = """
SELECT COUNT(*) AS value FROM {table}
"""

AGGREGATE_SUM_SQL = """
SELECT COALESCE(SUM("{column}"), 0)::numeric AS value FROM {table}
"""

NOT_NEGATIVE_SQL = """
SELECT
    COUNT(*) FILTER (WHERE "{column}" IS NOT NULL AND "{column}" < 0)
        AS negative_count,
    COUNT(*) AS total_count
FROM {table}
"""

REFERENCE_LOOKUP_SQL = """
SELECT
    COUNT(*) FILTER (
        WHERE "{column}" IS NOT NULL
        AND NOT ("{column}"::text = ANY(%(valid_values)s))
    ) AS invalid_count,
    COUNT(*) AS total_count
FROM {table}
"""

TABLE_EXISTS_SQL = """
SELECT COUNT(*) FROM information_schema.tables
WHERE table_schema = %(schema)s AND table_name = %(table)s
"""
