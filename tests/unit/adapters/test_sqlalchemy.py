from __future__ import annotations

import importlib.util

import pytest

_SA_INSTALLED = importlib.util.find_spec("sqlalchemy") is not None

pytestmark = pytest.mark.skipif(not _SA_INSTALLED, reason="sqlalchemy not installed")

"""SQLAlchemy meta-adapter tests, run against in-memory SQLite — an engine
qualis has NO native adapter for, which is exactly the point: if the checks
count correctly here, the Core-expression layer is doing the work."""


@pytest.fixture()
def adapter():
    from qualis.adapters.sqlalchemy.adapter import SQLAlchemyAdapter

    a = SQLAlchemyAdapter("sqlite://")
    a.execute(
        "CREATE TABLE accidents ("
        "id INTEGER, accident_date TEXT, severity_code TEXT, location_id INTEGER)"
    )
    rows = [
        (1, "2024-01-15", "FATAL", 101),
        (2, None, "SERIOUS", 102),
        (3, "2024-03-20", "INVALID", 103),
        (4, "2024-05-10", "MINOR", None),
        (5, "2024-05-10", "FATAL", -5),
        (1, "2024-06-01", "PROPERTY", 106),
    ]
    for r in rows:
        a.execute(
            "INSERT INTO accidents VALUES (:id, :d, :s, :loc)",
            {"id": r[0], "d": r[1], "s": r[2], "loc": r[3]},
        )
    return a


class TestChecks:
    def test_not_null(self, adapter) -> None:
        result = adapter.check_not_null("", "accidents", "accident_date")
        assert result == {"null_count": 1, "total_count": 6}

    def test_unique_counts_extra_copies(self, adapter) -> None:
        result = adapter.check_unique("", "accidents", "id")
        assert result["duplicate_count"] == 1  # id=1 twice -> one extra copy
        assert result["total_count"] == 6

    def test_between(self, adapter) -> None:
        result = adapter.check_between(
            "", "accidents", "accident_date", "2024-01-01", "2024-05-31"
        )
        assert result["out_of_range_count"] == 1  # 2024-06-01
        assert result["total_count"] == 6
        assert result["checked"] == 5  # null excluded

    def test_regex(self, adapter) -> None:
        result = adapter.check_regex("", "accidents", "severity_code", "^[A-Z]+$")
        assert result["non_matching_count"] == 0
        result = adapter.check_regex("", "accidents", "severity_code", "^(FATAL|SERIOUS)$")
        assert result["non_matching_count"] == 3  # INVALID, MINOR, PROPERTY

    def test_in_set(self, adapter) -> None:
        result = adapter.check_in_set(
            "", "accidents", "severity_code",
            ["FATAL", "SERIOUS", "MINOR", "PROPERTY"],
        )
        assert result == {"invalid_count": 1, "total_count": 6}

    def test_row_count(self, adapter) -> None:
        assert adapter.check_row_count("", "accidents") == {"row_count": 6}

    def test_not_negative(self, adapter) -> None:
        result = adapter.check_not_negative("", "accidents", "location_id")
        assert result == {"negative_count": 1, "total_count": 6}

    def test_reference_lookup(self, adapter) -> None:
        result = adapter.check_reference_lookup(
            "", "accidents", "severity_code",
            ["FATAL", "SERIOUS", "MINOR", "PROPERTY"],
        )
        assert result == {"invalid_count": 1, "total_count": 6}

    def test_table_exists(self, adapter) -> None:
        assert adapter.table_exists("", "accidents") is True
        assert adapter.table_exists("", "nope") is False


class TestSamples:
    def test_in_set_sample_carries_value_and_rid(self, adapter) -> None:
        samples = adapter.fetch_violation_samples(
            "", "accidents", "severity_code", "in_set",
            {"values": ["FATAL", "SERIOUS", "MINOR", "PROPERTY"]}, 10,
        )
        assert len(samples) == 1
        assert samples[0]["actual_value"] == "INVALID"
        assert samples[0]["record_id"] is not None

    def test_limit_respected(self, adapter) -> None:
        samples = adapter.fetch_violation_samples(
            "", "accidents", "id", "unique", {}, 1,
        )
        assert len(samples) == 1
        assert samples[0]["actual_value"] == 1

    def test_unsupported_kind_raises(self, adapter) -> None:
        with pytest.raises(ValueError, match="unsupported sample kind"):
            adapter.fetch_violation_samples("", "accidents", "id", "row_count", {}, 5)


class TestEngineIntegration:
    def test_rule_engine_runs_through_sqlalchemy(self, adapter) -> None:
        from qualis.domain.enums import DQDimension, RuleType, Severity
        from qualis.domain.models import Rule
        from qualis.domain.params import NotNullParams
        from qualis.domain.rule_engine import RuleEngine

        rule = Rule(
            id="r1", name="x", dimension=DQDimension.COMPLETENESS,
            rule_type=RuleType.ROW_LEVEL, severity=Severity.CRITICAL,
            dataset="accidents", column="accident_date", check="not_null",
            params=NotNullParams(),
        )
        engine = RuleEngine(adapter, schema="", sample_rows=3)
        result = engine.evaluate_rule(rule)
        assert result.violation_count == 1
        assert result.violations[0].actual_value is None
        assert result.violations[0].record_id is not None  # real sampled row


class TestResolutionPath:
    def test_settings_resolve_sqlalchemy_via_entry_point(self) -> None:
        from qualis.bootstrap import resolve_adapter
        from qualis.config.settings import QualisSettings

        settings = QualisSettings(adapter="sqlalchemy", database_url="sqlite://")
        adapter = resolve_adapter(settings)
        assert type(adapter).__name__ == "SQLAlchemyAdapter"

    def test_missing_extra_raises_install_hint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import qualis.adapters.sqlalchemy.adapter as mod

        monkeypatch.setattr(mod, "_SA_AVAILABLE", False)
        with pytest.raises(ImportError, match=r"qualis\[sqlalchemy\]"):
            mod.SQLAlchemyAdapter("sqlite://")


class TestConditions:
    """Condition pushdown (AgDR-0005) through Core expressions."""

    def _rule_engine(self, adapter, sample_rows=None):
        from qualis.domain.rule_engine import RuleEngine

        return RuleEngine(adapter, schema="", sample_rows=sample_rows)

    def test_supports_conditions_flag(self, adapter) -> None:
        assert adapter.supports_conditions is True

    def test_condition_filters_count_population(self, adapter) -> None:
        from qualis.domain.condition import parse_condition

        cond = parse_condition("severity_code = 'FATAL'")
        result = adapter.check_not_null("", "accidents", "accident_date", condition=cond)
        assert result == {"null_count": 0, "total_count": 2}  # two FATAL rows

    def test_conditioned_samples_respect_population(self, adapter) -> None:
        from qualis.domain.condition import parse_condition

        # Without condition: 1 null date (row id=2, SERIOUS). With a
        # condition excluding SERIOUS rows the sample must be empty.
        cond = parse_condition("severity_code != 'SERIOUS'")
        samples = adapter.fetch_violation_samples(
            "", "accidents", "accident_date", "not_null", {}, 10, condition=cond,
        )
        assert samples == []

    def test_in_with_numbers_and_reserved_word_column(self, adapter) -> None:
        from qualis.domain.condition import parse_condition

        adapter.execute('CREATE TABLE t2 ("order" INTEGER, v TEXT)')
        adapter.execute('INSERT INTO t2 VALUES (1, NULL)')
        adapter.execute('INSERT INTO t2 VALUES (2, NULL)')
        cond = parse_condition("order IN (1, 3)")  # reserved-word column (C4)
        result = adapter.check_not_null("", "t2", "v", condition=cond)
        assert result == {"null_count": 1, "total_count": 1}

    def test_unique_condition_applies_to_inner_scan(self, adapter) -> None:
        from qualis.domain.condition import parse_condition

        # id=1 duplicates across FATAL + PROPERTY rows; restricting the
        # population to FATAL rows leaves one id=1 -> no duplicates (the
        # review's HAVING-subquery trap, B2).
        cond = parse_condition("severity_code = 'FATAL'")
        result = adapter.check_unique("", "accidents", "id", condition=cond)
        assert result["duplicate_count"] == 0
        assert result["total_count"] == 2


class TestReferenceJoin:
    """AgDR-0006 JOIN-mode lookup: NULL-safe NOT EXISTS (C1), namespace (C2)."""

    @pytest.fixture()
    def ref_adapter(self):
        from qualis.adapters.sqlalchemy.adapter import SQLAlchemyAdapter

        a = SQLAlchemyAdapter("sqlite://")
        a.execute("CREATE TABLE orders (id INTEGER, country TEXT, region TEXT)")
        for row in [(1, "US", "amer"), (2, "GB", "emea"), (3, "XX", "emea"), (4, None, "apac")]:
            a.execute(
                "INSERT INTO orders VALUES (:i, :c, :r)",
                {"i": row[0], "c": row[1], "r": row[2]},
            )
        # Reference table WITH a NULL key (the C1 trap) and a colliding
        # column name `region` (the C2 trap).
        a.execute("CREATE TABLE countries (code TEXT, region TEXT)")
        for row in [("US", "amer"), ("GB", "emea"), (None, "x")]:
            a.execute(
                "INSERT INTO countries VALUES (:c, :r)", {"c": row[0], "r": row[1]}
            )
        return a

    def test_null_ref_key_does_not_zero_invalid_count(self, ref_adapter) -> None:
        # C1: with NOT IN this would return 0; NOT EXISTS must find XX.
        result = ref_adapter.check_reference_join(
            "", "orders", "country", "", "countries", "code"
        )
        assert result == {"invalid_count": 1, "total_count": 4}

    def test_condition_with_colliding_column_name(self, ref_adapter) -> None:
        # C2: `region` exists in BOTH tables; the condition must bind to the
        # target. emea rows: GB (valid), XX (invalid) -> 1 invalid of 2.
        from qualis.domain.condition import parse_condition

        result = ref_adapter.check_reference_join(
            "", "orders", "country", "", "countries", "code",
            condition=parse_condition("region = 'emea'"),
        )
        assert result == {"invalid_count": 1, "total_count": 2}

    def test_join_samples_respect_population_and_predicate(self, ref_adapter) -> None:
        samples = ref_adapter.fetch_violation_samples(
            "", "orders", "country", "reference_join",
            {"reference_schema": "", "reference": "countries", "key_column": "code"},
            10,
        )
        assert [s["actual_value"] for s in samples] == ["XX"]


def test_reference_join_same_column_name_no_tautology(ref_adapter=None) -> None:
    """Regression: key_column == column must not render 'code' = 'code'."""
    from qualis.adapters.sqlalchemy.adapter import SQLAlchemyAdapter

    a = SQLAlchemyAdapter("sqlite://")
    a.execute("CREATE TABLE t (code TEXT)")
    a.execute("INSERT INTO t VALUES ('XX')")
    a.execute("CREATE TABLE ref (code TEXT)")
    a.execute("INSERT INTO ref VALUES ('US')")
    result = a.check_reference_join("", "t", "code", "", "ref", "code")
    assert result == {"invalid_count": 1, "total_count": 1}


class TestCheckAggregate:
    """cross_dataset_assertion capability (AgDR-0008) via Core expressions."""

    def test_row_count(self, adapter) -> None:  # type: ignore[no-untyped-def]
        assert adapter.check_aggregate("", "accidents", "row_count")["value"] == 6

    def test_sum_excludes_nulls(self, adapter) -> None:  # type: ignore[no-untyped-def]
        # location_id: 101+102+103+(-5)+106 = 407, one NULL excluded
        value = adapter.check_aggregate("", "accidents", "sum", "location_id")["value"]
        assert float(value) == 407.0

    def test_sum_of_all_null_is_zero(self, adapter) -> None:  # type: ignore[no-untyped-def]
        adapter.execute("CREATE TABLE nulls_only (x INTEGER)")
        adapter.execute("INSERT INTO nulls_only VALUES (NULL)")
        value = adapter.check_aggregate("", "nulls_only", "sum", "x")["value"]
        assert value is not None
        assert float(value) == 0.0

    def test_unknown_metric_rejected(self, adapter) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(ValueError, match="unsupported metric"):
            adapter.check_aggregate("", "accidents", "count_distinct", "id")
