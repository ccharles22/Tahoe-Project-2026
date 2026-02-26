# Git workflow

This page describes the standard branch flow for this repository.

Replace placeholder values such as `<YOUR_REPO_URL>`, `<TEAM_REPO_URL>`, and branch names with your actual values.

## One-time setup

```bash
git init
git add .
git commit -m "Initial commit"
```

Connect remotes:

```bash
git remote add origin <YOUR_REPO_URL>
git remote add group <TEAM_REPO_URL>
git remote -v
```

## Daily workflow

### 1. Sync branch

```bash
git checkout PostgreSQL-repository-and-data-visualization-MPL
git fetch group
git rebase group/PostgreSQL-repository-and-data-visualization-MPL
```

### 2. Commit local work

```bash
git add -A
git commit -m "Describe change"
git push origin PostgreSQL-repository-and-data-visualization-MPL
```

### 3. Share to team remote

```bash
git push group PostgreSQL-repository-and-data-visualization-MPL
```

## Merge workflow

When branch work is ready:

```bash
git checkout main
git merge PostgreSQL-repository-and-data-visualization-MPL
git push origin main
```

## Recommended ignore rules

```gitignore
# Python
__pycache__/
*.pyc
.venv/
venv/
.env

# Flask
instance/
*.log

# VS Code / OS
.vscode/
.DS_Store

# Local data exports
*.db
*.sqlite
```

## Quick recovery commands

### Undo staged changes (keep working tree)

```bash
git restore --staged .
```

### Inspect differences

```bash
git status
git diff
git log --oneline --decorate --graph -20
```

### Save work before risky operations

```bash
git add -A
git commit -m "WIP backup"
```

## Collaboration rules

- Commit small, focused changes.
- Rebase frequently onto team branch.
- Avoid force push on shared branches.
- Never commit secrets (`.env`, passwords, private URLs).
