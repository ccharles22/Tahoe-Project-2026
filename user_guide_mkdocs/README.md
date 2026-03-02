# User Guide Documentation

This directory contains the MkDocs-based user guide for the Direct Evolution Monitoring Portal.

## Overview

The user guide provides step-by-step instructions for using the portal's 5-step workflow:

1. **Step 1: Fetch Wild-Type** - Retrieve protein from UniProt
2. **Step 2: Validate Plasmid** - Validate plasmid FASTA against wild-type
3. **Step 3: Upload Data** - Upload variant data (TSV/CSV/JSON)
4. **Step 4: Process Sequences** - Translate and call mutations
5. **Step 5: Run Analysis** - Generate visualizations

## Structure

```
user_guide_mkdocs/
├── mkdocs.yml              # MkDocs configuration
├── staging_docs/           # Documentation source files
│   ├── index.md           # Home page
│   ├── workflow/          # Workflow step guides
│   │   ├── overview.md
│   │   ├── step1-fetch-wildtype.md
│   │   ├── step2-validate-plasmid.md
│   │   ├── step3-upload-data.md
│   │   ├── step4-process-sequences.md
│   │   └── step5-run-analysis.md
│   ├── troubleshooting/   # Troubleshooting guides
│   │   ├── common-issues.md
│   │   └── faqs.md
│   └── stylesheets/       # Custom CSS
│       └── extra.css
└── site/                   # Generated static site (auto-generated)
```

## Building the Documentation

### Prerequisites

Install MkDocs and required extensions:

```bash
pip install mkdocs
pip install mkdocs-material
pip install pymdown-extensions
```

### Build Commands

**Serve locally (with live reload):**

```bash
cd user_guide_mkdocs
mkdocs serve
```

Then open http://127.0.0.1:8000/ in your browser.

**Build static site:**

```bash
cd user_guide_mkdocs
mkdocs build
```

This generates the static HTML site in the `site/` directory.

**Deploy to GitHub Pages:**

```bash
cd user_guide_mkdocs
mkdocs gh-deploy
```

## Integration with Portal

The user guide is accessible from the portal via the **User Guide** link in the navigation bar.

To integrate:

1. Build the static site: `mkdocs build`
2. The `site/` folder contains the generated HTML
3. Configure your web server to serve `/guide/` from the `site/` directory
4. Or copy the `site/` contents to your web server's public directory

### Flask Integration

In your Flask app, you can serve the guide using:

```python
from flask import send_from_directory

@app.route('/guide/')
@app.route('/guide/<path:path>')
def user_guide(path='index.html'):
    return send_from_directory('user_guide_mkdocs/site', path)
```

## Customization

### Theme

The guide uses the Material for MkDocs theme with:

- Primary color: Indigo
- Dark/light mode toggle
- Navigation features (tabs, sections, search)

Customize in `mkdocs.yml` under the `theme:` section.

### Styling

Custom CSS is in `staging_docs/stylesheets/extra.css`. This includes:

- Badge styling
- Table enhancements
- Mermaid diagram styling
- Responsive images

### Content

Edit the Markdown files in `staging_docs/` to update content. MkDocs uses standard Markdown with extensions:

- Admonitions: `!!! note`, `!!! tip`, `!!! warning`
- Code highlighting: ` ```python `
- Mermaid diagrams: ` ```mermaid `
- Tables, task lists, and more

See the [MkDocs documentation](https://www.mkdocs.org/) and [Material theme docs](https://squidfunk.github.io/mkdocs-material/) for details.

## Contributing

To add new pages:

1. Create a new `.md` file in the appropriate `staging_docs/` subdirectory
2. Add the page to the `nav:` section in `mkdocs.yml`
3. Build and test locally with `mkdocs serve`
4. Commit the source files (not the `site/` directory)

## License

This documentation is part of the BIO727P Group Project.

---

**Navigation:**

- [Home](staging_docs/index.md)
- [Workflow Overview](staging_docs/workflow/overview.md)
- [Step 1: Fetch Wild-Type](staging_docs/workflow/step1-fetch-wildtype.md)
- [Step 2: Validate Plasmid](staging_docs/workflow/step2-validate-plasmid.md)
