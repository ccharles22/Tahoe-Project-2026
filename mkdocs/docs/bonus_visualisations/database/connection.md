# Database Notes

The bonus visualisation pipeline reads from the same experiment data used by
the core analysis layer. It depends on:

- experiment and generation records
- variant records
- mutation rows
- derived activity metrics when available

## Data dependencies

Some bonus plots can run with mutation data alone, while others also require
derived `activity_score` values.

- **Activity-dependent**:
  - Activity Landscape
  - Activity Surface
  - Mutation Trajectory
- **Mutation/domain-dependent**:
  - Mutation Frequency
  - Domain Enrichment
  - Mutation Fingerprinting

If a required dataset is missing, the platform keeps the bonus view visible and
shows an explanatory placeholder instead of silently removing the section.
