# Direct Evolution Monitoring Portal  
### Team Tahoe | MSc Bioinformatics | 2025–2026
---

## Overview

The **Direct Evolution Monitoring (DEM) Portal** is a web-based platform developed by **Team Tahoe** for the MSc Bioinformatics BIO727P Software Development Group Project (2025–2026).

The portal enables users to **track, analyse, and visualise** data generated from automated directed evolution experiments. It supports the **Design–Build–Test–Learn (DBTL)** cycle by providing an integrated environment for managing experimental data and monitoring evolutionary progress. 
This portal is designed to make core experimental signals easier to read, compare, and explain. From DNA and protein yield to activity-normalised enzyme efficiency, each run turns raw measurements into interpretable evidence for selection decisions.

The system focuses on analysing directed evolution experiments aimed at improving **DNA polymerase performance**.

---

## Project Objectives

The DEM Portal allows users to:

- Register and securely log in  
- Stage new directed evolution experiments  
- Retrieve protein information from UniProt  
- Upload and validate plasmid DNA sequences  
- Parse experimental data (TSV or JSON)  
- Perform automated sequence analysis  
- Calculate a unified **Activity Score**  
- Visualise performance across generations  

---

## Key Features

### User Management
- Secure registration and authentication  
- User-specific experiment data  

### Experiment Staging
- UniProt API integration  
- Protein sequence retrieval  
- Feature annotation extraction  
- Plasmid FASTA upload and validation  

### Data Processing
- Supports TSV and JSON formats  
- Dynamic schema handling  
- Quality control and validation  
- Circular plasmid sequence support  

### Sequence Analysis
- DNA → protein translation  
- Mutation identification relative to wild type  
- Classification of synonymous and non-synonymous mutations  

### Activity Analysis
- Calculation of a unified **Activity Score**  
- Normalisation using control baseline values  

### Visualisation
- Top-performing variants table  
- Activity distribution by generation  
- Variant lineage modelling
- Protein similarity network (mutation co-occurrence)
- Mutation Fingerprinting by Generation
- 3D Activity Landscape

---

## Technology Stack

- **Backend:** Python (Flask or Django)  
- **Database:** SQLite / PostgreSQL  
- **Analysis:** Pandas, NumPy, BioPython  
- **Visualisation:** Matplotlib / Plotly  
- **Version Control:** GitHub  

---

## Project Structure

```
DEM-Portal/
│
├── app/                # Web application source code
├── analysis/           # Data processing and analysis modules
├── database/           # Database models and schema
├── templates/          # HTML templates
├── static/             # CSS, JavaScript, images
├── docs/               # Documentation and logo files
├── data/               # Example datasets
├── tests/              # Unit tests
└── README.md
```

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-username/DEM-Portal.git
cd DEM-Portal
```

### 2. Create a virtual environment

**Mac/Linux**
```bash
python -m venv venv
source venv/bin/activate
```

**Windows**
```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the application

```bash
python app.py
```

Open your browser and go to:

```
http://127.0.0.1:5000
```

---

## Example Workflow

1. Register or log in  
2. Create a new experiment  
3. Enter UniProt accession ID  
4. Upload plasmid FASTA file  
5. Upload experimental dataset (TSV or JSON)  
6. View analysis results and visualisations  

---

## Assessment Context

This project was developed for:

**MSc Bioinformatics – Software Development Group Project**  
Academic Year: **2025–2026**

The system demonstrates:

- Full-stack web development  
- Biological sequence analysis  
- API integration  
- SQL database design  
- Scientific data visualisation  

---

## Team Tahoe
- LUCIANI, Maria-Paola
- OAKARR, Luke
- CHARLES, Candice
- ARAKIT-OSIRE, Patricia
- PUVANESWARAN, Reman


---

## Future Improvements

- Interactive mutation visualisation  
- 3D activity landscape  
- Cloud deployment  
- Real-time experiment monitoring  

---

## License

This project is for academic use only.
