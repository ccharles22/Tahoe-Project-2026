# Connection & Materialized Views

## Database connection

All database access goes through `analysis.database.postgres`, which reads
connection parameters from a `.env` file or environment variables:

| Variable | Description |
|---|---|
| `DB_HOST` | PostgreSQL host |
| `DB_PORT` | Port (default `5432`) |
| `DB_NAME` | Database name |
| `DB_USER` | Username |
| `DB_PASSWORD` | Password |

Two helpers are used throughout the codebase:

```python
from analysis.database.postgres import get_connection, get_cursor

# Read-only queries (returns psycopg2 connection)
with get_connection() as conn:
    df = pd.read_sql_query("SELECT ...", conn)

# Write operations (auto-commits on success)
with get_cursor(commit=True) as cur:
    cur.execute("INSERT INTO ...")
```

## Materialized views

The pipeline creates and queries two materialized views.  DDL lives in
`sql/views/`.

### `mv_activity_landscape`

Combines embeddings from the `metrics` table with activity scores and protein
mutation summaries.

Key columns: `generation_id`, `plasmid_variant_index`, `activity_score`,
`x`, `y`, `method`, `protein_mutations`.

### `mv_domain_mutation_enrichment`

Aggregates non-synonymous mutation counts per protein domain per generation.

Key columns: `generation_id`, `domain_label`, `nonsyn_count`, `syn_count`,
`domain_length`, `nonsyn_per_residue`.

!!! warning
    If the schema of these views changes (e.g. columns are added upstream),
    the pipeline detects the mismatch and raises an error with instructions
    to drop and recreate the views.
