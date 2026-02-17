# Initialising visual studio code:
git init
git add .
git commit -m "Initial commit: schema + Flask skeleton"

# Add a proper Python + Flask .gitignore
Creating a .gitignore file
git add .gitignore
git commit -m "Add .gitignore"

# Connect to github and push
git branch -M main
git remote add origin https://github.com/mpluciani/PostgreSQL-database-schema-and-data-visualization-MPL.git
git push -u origin main

# Create the README file with added checklist
touch README.md
git add README.md
git commit -m "Add project README and workplan"
git push


# IMPORTANT FROM NOW ON: 
git add .
git commit -m "Describe change"
git push


# Clone the team repo, then create a branch, then add your files
cd "/Users/mariapaolaluciani/Documents/GitHub/PostgreSQL-repository-and-data-visualization-MPL"
git status
git add .
git commit -m "Save work before sharing" #only if  status shows changes
git push #push to my own github (origin)


# add the team repository as the second remote (group)
git remote add group https://github.com/ccharles22/Tahoe-Project-2026.git
git remote -v


# create branch to contribute 
git checkout PostgreSQL-repository-and-data-visualization-MPL #branch already exists
git branch #* next to my branch

# push branch onto the team repository
git push -u group PostgreSQL-repository-and-data-visualization-MPL


# ignore macOS files
echo .DS_Store >> .gitignore
git add .gitignore
git commit -m "chore: ignore macOS system files"
git push origin PostgreSQL-repository-and-data-visualization-MPL

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

# Database / data
*.db
*.sqlite
*.tsv
*.csv
*.json


# What happens when I need to add or push something, example:
# 1) Make sure I am on the  branch
git checkout PostgreSQL-repository-and-data-visualization-MPL

git add -A
git commit -m "Your message"
git push origin PostgreSQL-repository-and-data-visualization-MPL #sending to my rep


git push group PostgreSQL-repository-and-data-visualization-MPL #sending to group rep

git checkout PostgreSQL-repository-and-data-visualization-MPL
git fetch group
git rebase group/PostgreSQL-repository-and-data-visualization-MPL
git push origin PostgreSQL-repository-and-data-visualization-MPL


# ***day to day work
# work on branch
git add
git commit
git push origin PostgreSQL-repository-and-data-visualization-MPL


### when work is ready:
git checkout main
git merge PostgreSQL-repository-and-data-visualization-MPL
git push origin main


# push the branch to the team work
git push group PostgreSQL-repository-and-data-visualization-MPL




# Complete workflow for the creation of the github repository with all the documentation needed
# Make sure I am in my working branch
cd "/Users/mariapaolaluciani/Documents/GitHub/PostgreSQL-repository-and-data-visualization-MPL"
git status
git branch
git checkout PostgreSQL-repository-and-data-visualization-MPL

# Create the folder structure
mkdir -p src/analysis_MPL app/templates app/static/generated schema docs scripts tests
touch src/analysis_MPL/__init__.py
touch scripts/__init__.py
touch schema/schema.sql

# src
touch src/analysis_MPL/database.py \
      src/analysis_MPL/queries.py \
      src/analysis_MPL/activity_score.py \
      src/analysis_MPL/mutations.py \
      src/analysis_MPL/sequence.py \
      src/analysis_MPL/plots.py \
      src/analysis_MPL/report.py
      src/analysis_MPL/metrics.py

touch scripts/run_report.py scripts/test_connection.py
touch tests/test_activity_score.py tests/test_mutations.py

# Create all the docs files
touch docs/git_workflow.md \
      docs/database_setup_tailscale.md \
      docs/schema_design_notes.md \
      docs/methodology.md


#  OFFICIAL WORKFLOW 
1) docs/git_workflow.md
# Paste all origin/group/branch commands +  daily workflow.
2) docs/database_setup_tailscale.md
# Paste Homebrew Postgres + Tailscale + pg_hba.conf + role setup steps.
Replace:
any IP like 100.xx.xx.xx → <TAILSCALE_IP>
any password → <PASSWORD>
3) docs/schema_design_notes.md
Paste your schema explanation, triggers, cascade deletes rationale, constraints.
4) docs/stage4_method.md
Write (briefly):
activity score definition
what top-10 means
what the generation plot shows
what mutation counts represent

# Create a .env file (local only, not committed)
cat > .env <<'EOF'
DATABASE_URL= postgresql://mariapaolaluciani:<PASSWORD>@100.80.183.102:5432/bio727p_group_project 
EOF


# Allowing to set DATABASE_URL before testing
export DATABASE_URL="postgresql://mariapaolaluciani:<PASSWORD>@100.80.183.102:5432/bio727p_group_project"
PYTHONPATH=. python scripts/test_connection.py

python -m scripts.test_connection #testing the connection


# Add minime runnable schema
# src/analysis_MPL database.py
import os
import psycopg2

def get_conn():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set. Use .env or export it.")
    return psycopg2.connect(url)

# scripts/test_connection.py
from src.analysis_MPL.database import get_conn

# also add to allow get_conn() to work without exporting it directly to .env
from dotenv import load_dotenv
load_dotenv()

if __name__ == "__main__":
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
            print("DB connection OK:", cur.fetchone())

# scripts/run_report.py
print("Placeholder: this will generate top-10 table + generation plot.")
print("Next: implement queries + plots in src/stage4/")

# Create and activate the virtual environment
python3 -m venv venv
source venv/bin/activate


# installing the right packages
pip install Flask psycopg2-binary pandas matplotlib python-dotenv #installing what is needed for the project, considering PostgreSQL is used rather than mysql


# save dependencies to let my teammates recreate the environment
pip freeze > requirements.txt
python -m scripts.test_connection


# Commit everything
cd "/Users/mariapaolaluciani/Documents/GitHub/PostgreSQL-repository-and-data-visualization-MPL"

git status

git add .gitignore
git commit -m "Update .gitignore" #gitignore needs to be up to date and committed

git add .
git status #should see everything

git commit -m "Initial project setup: folder structure, database connection, scripts, docs, requirements"

git branch

git push origin PostgreSQL-repository-and-data-visualization-MPL
git push group PostgreSQL-repository-and-data-visualization-MPL
