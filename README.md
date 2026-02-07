Workflow:

0 Github creation
1 Designed full relational schema (users → experiments → generations → variants)
2 Added mutation tracking (DNA + protein, synonymous vs non-synonymous)
3 Designed metrics table (raw / normalised / derived)
4 Added JSONB metadata for flexible TSV/JSON ingestion
5 Added cascade delete rules to prevent orphan data
6 Set up shared PostgreSQL using Tailscale
7 Created per-user database roles for teammates
8 Defined metric strategy (what counts as yield, activity score, normalisation)
9 Implement yield calculations (DNA yield, protein yield, etc.)
10 Implement activity score calculation per variant
11 Implement WT baseline normalisation
12 Store raw, normalised, and derived metrics in DB
13 Export final schema to schema.sql
14 Create Flask app skeleton
15 Connect Flask to PostgreSQL
16 Implement user registration
17 Implement user login (Flask-Login)
18 Restrict users to their own experiments
19 Create TSV/JSON upload route (metrics-related fields)
20 Validate and parse metric-relevant data
21 Insert calculated metrics into database
22 Query top-10 variants by activity score
23 Plot per-generation activity distribution
24 Compare WT vs variants across generations