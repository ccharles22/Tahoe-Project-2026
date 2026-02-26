## MkDocs Layout

Single MkDocs project with namespaced ownership:

- `mkdocs/mkdocs.yml`: unified config
- `mkdocs/docs/parsing_qc/`: Parsing/QC documentation scope
- `mkdocs/docs/postgresql_visualization/`: PostgreSQL visualization documentation scope

### Preview locally

```bash
cd mkdocs
mkdocs serve -a 127.0.0.1:8000
```

### Build static site for Flask `/docs/*`

```bash
cd mkdocs
mkdocs build
```

This writes output to `mkdocs/site/`, which is served by the Flask app at `/docs/`.