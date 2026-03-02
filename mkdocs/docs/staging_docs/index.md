# Staging & Workspace

This section explains how to use the experiment workspace, what each workflow
step is responsible for, and how the staging interface connects sequence
processing, reporting, and visual interpretation.

## What the workspace is for

The staging workspace is the operational core of the platform. It is where
users move from setup into analysis for a specific experiment.

Use the workspace when you need to:

- fetch the experiment wild-type reference
- validate the plasmid used as the reference sequence context
- upload and validate parsed experiment data
- run sequence processing
- generate result visualisations and reports
- inspect bonus visualisations after analysis

## Main workspace layout

The page is organized into three practical layers:

### Top header

The top header provides direct app navigation:

- `Home` returns to the homepage
- `Workspace` keeps you inside the current experiment workspace
- `User Guide` opens the documentation hub

This header is intended to help users move between the live app and the
documentation without losing context.

### Left taskbar and workflow panel

The left side of the workspace is split into:

- a taskbar (`Experiments`, `Tools`)
- the workflow sidebar

The workflow sidebar is the clearest way to understand the execution order of
the platform. It maps the experiment process into the staged sequence of
actions users are expected to follow.

### Main content area

The main workspace area shows:

- current experiment status
- WT output
- validation and parsing summaries
- sequence processing state
- result visualisations
- bonus visualisations
- downloads and experiment summary

This means the workspace is designed both as an execution page and as a review
page.

## Workflow steps

The operational flow is organized into five main steps.

### 1. Fetch WT (UniProt)

This step retrieves and stages the wild-type protein reference for the current
experiment. It is the first reference point for downstream sequence
interpretation.

### 2. Validate Plasmid

This step checks the plasmid reference sequence used for mapping and CDS
extraction. If the plasmid is wrong, later sequence processing can become slow,
misleading, or invalid.

### 3. Upload Parsing Data

This step loads the parsed experiment data and runs upload-time validation. It
is the point where record counts, warnings, and parsing quality become visible.

### 4. Process Sequences

This step performs the biological sequence-processing pipeline. It is
responsible for:

- extracting coding sequence
- translating sequence into protein
- comparing variants against the wild type
- computing mutation outputs

This is usually the most computationally expensive step.

### 5. Run Analysis

This step generates the report outputs and visualisations from the processed
data. It is where:

- activity metrics are refreshed
- result plots are regenerated
- bonus visualisations are generated when their required inputs exist

If the sequence-processing step is incomplete or invalid, the analysis outputs
can also be incomplete.

## What users should check

When using the workspace, the most important checks are:

- whether the wild-type reference is correct
- whether parsing warnings indicate missing or malformed input data
- whether sequence processing completed successfully
- whether the result visualisations reflect the expected experiment state
- whether bonus visualisations were generated or skipped with a stated reason

## When to use this section

Use this `Staging Docs` section when you need to understand:

- how the workspace is organized
- what each workflow step actually does
- why a run may feel slow
- why outputs may be missing from Sections 5 or 6

For technical details beyond the workspace itself, continue into:

- `Parsing & QC` for upload and validation rules
- `Metric Computations` for score logic
- `Visualisation Guide` for core plots
- `Bonus Visualisations` for Section 6 outputs
