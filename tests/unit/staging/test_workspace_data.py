"""Unit tests for staging workspace KPI query behavior."""

from __future__ import annotations

from types import SimpleNamespace


class _FakeMappings:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)

    def first(self):
        if not self._rows:
            return None
        return self._rows[0]


class _FakeResult:
    def __init__(self, *, scalar_value=None, fetchone_value=None, mappings_rows=None):
        self._scalar_value = scalar_value
        self._fetchone_value = fetchone_value
        self._mappings_rows = mappings_rows or []

    def scalar(self):
        return self._scalar_value

    def fetchone(self):
        return self._fetchone_value

    def mappings(self):
        return _FakeMappings(self._mappings_rows)


def test_load_kpis_uses_latest_successful_vsa_for_mutation_kpi(monkeypatch):
    from app.services.staging import workspace_data

    captured_sql = []

    class _FakeSession:
        def execute(self, statement, params):
            sql = str(statement)
            captured_sql.append(sql)

            if "COUNT(*)" in sql and "FROM variants v" in sql:
                return _FakeResult(scalar_value=120)
            if "MIN(generation_number)" in sql and "MAX(generation_number)" in sql:
                return _FakeResult(fetchone_value=(1, 6))
            if "AVG(la.activity_score)" in sql and "MAX(la.activity_score)" in sql:
                return _FakeResult(fetchone_value=(1.25, 2.8))
            if "percentile_cont(0.5)" in sql:
                return _FakeResult(scalar_value=1.1)
            if "analysed_variants" in sql:
                return _FakeResult(scalar_value=40)
            if "mutated_variants" in sql:
                return _FakeResult(scalar_value=10)
            if "mutation_label" in sql:
                return _FakeResult(
                    mappings_rows=[{"mutation_label": "A1V", "mutation_count": 4}]
                )
            if "syn_count" in sql and "non_syn_count" in sql:
                return _FakeResult(mappings_rows=[{"syn_count": 3, "non_syn_count": 6}])

            raise AssertionError(f"Unexpected SQL in test: {sql}")

        def rollback(self):
            return None

    fake_db = SimpleNamespace(session=_FakeSession())
    monkeypatch.setattr(workspace_data, "db", fake_db)

    kpis = workspace_data.load_kpis(999)

    assert kpis["mutated_percent"] == 25.0
    assert kpis["most_common_mutations"] == "A1V (4)"
    assert kpis["syn_non_syn_ratio"] == "3:6 (0.50)"

    joined_sql = "\n".join(captured_sql)
    assert "status = 'success'" in joined_sql
    assert "qc_flags->'mutation_counts'->>'nonsynonymous'" in joined_sql
    assert "m.is_synonymous = FALSE" in joined_sql
