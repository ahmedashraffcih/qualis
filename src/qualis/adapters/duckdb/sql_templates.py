from __future__ import annotations

# ---------------------------------------------------------------------------
# DuckDB SQL templates
# ---------------------------------------------------------------------------
# All column references use double-quoted identifiers to handle names that
# are reserved keywords or contain special characters.

NOT_NULL_SQL = (
    'SELECT COUNT(*) FILTER (WHERE "{column}" IS NULL) AS null_count, '
    "COUNT(*) AS total_count "
    "FROM {table}"
)

UNIQUE_SQL = (
    "SELECT COUNT(*) AS duplicate_count, COUNT(*) + "
    "(SELECT COUNT(*) FROM {table}) - COUNT(*) AS total_count "
    "FROM ("
    '  SELECT "{column}" FROM {table} '
    '  GROUP BY "{column}" HAVING COUNT(*) > 1'
    ") dup"
)

BETWEEN_SQL = (
    "SELECT "
    "  COUNT(*) FILTER ("
    '    WHERE CAST("{column}" AS VARCHAR) < \'{min_val}\' '
    '    OR CAST("{column}" AS VARCHAR) > \'{max_val}\''
    "  ) AS out_of_range_count, "
    "  COUNT(*) AS total_count "
    "FROM {table}"
)

REGEX_SQL = (
    "SELECT "
    "  COUNT(*) FILTER ("
    '    WHERE "{column}" IS NULL '
    '    OR NOT regexp_matches(CAST("{column}" AS VARCHAR), \'{pattern}\')'
    "  ) AS non_matching_count, "
    "  COUNT(*) AS total_count "
    "FROM {table}"
)

TABLE_EXISTS_SQL = (
    "SELECT COUNT(*) AS cnt FROM information_schema.tables "
    "WHERE table_name = '{table}'"
)
