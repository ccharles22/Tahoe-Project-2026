# Direct Evolution Monitoring Portal

This guide is the main orientation point for the platform. It explains how to
move through the website, which documentation area to open for each task, and
how the major workflow stages relate to one another.

## Start here

The platform is designed around a simple flow:

1. open the homepage
2. move into the workspace for experiment operations
3. use the User Guide when you need definitions, workflows, or troubleshooting

The documentation is organized to match that same journey, so users can move
from basic navigation to technical detail without losing context.

## Navigating the website

### Home

The homepage is the public landing page. It is meant to:

- introduce the platform visually
- preview the kinds of outputs the pipeline can generate
- route users into the operational workspace

Use `Home` whenever you want to return to the landing page, reorient yourself,
or share the main entry point with someone else.

### Workspace

The workspace is the main operational area of the application. This is where
users:

- fetch and stage the wild-type reference
- validate plasmid inputs
- upload parsing data
- run sequence processing
- run analysis and generate report outputs
- review result and bonus visualisations

Use `Workspace` whenever you want to work on a real experiment or inspect
outputs that depend on live experiment data.

### User Guide

`User Guide` opens the documentation hub and the unified docs pages. It is the
best place to:

- understand what a workflow step does before running it
- learn how metrics are computed
- interpret plots correctly
- troubleshoot missing outputs or failed runs

The guide is written to support both first-time users and users who need
technical detail during debugging.

## Documentation areas

The guide is split into sections that match the main parts of the platform:

### Parsing & QC

Use this section when you need to understand:

- supported upload formats
- field normalization
- warning and error thresholds
- validation behavior during data ingestion

This is the right section for upload problems, unexpected warnings, and record
validation questions.

### Database & Schema

Use this section when you need:

- the overall table relationships
- schema design rationale
- database-level support for experiments, variants, metrics, and analysis

This section is the best starting point for understanding how the platform
stores experimental data and why the data model supports the workflow it does.

### Metric Computations

Use this section when you want to understand:

- how raw measurements are stored
- how normalization works
- how `activity_score` is calculated
- what QC rules exclude a metric from downstream analysis

This is the key section for understanding why rankings and distributions look
the way they do.

### Visualisation Guide

Use this section to interpret the core analysis outputs:

- Top 10 ranking
- activity score distribution
- lineage
- protein similarity network

It explains what each plot shows, what data it depends on, and how to read it
scientifically.

### Bonus Visualisations

Use this section for the optional Section 6 outputs, such as:

- activity landscape
- mutation fingerprinting
- domain enrichment
- mutation frequency

This section is most useful when you want deeper exploratory analysis beyond
the core report outputs.

### Ownership Notes

Use this section when contributing to the repository. It explains the main
documentation ownership boundaries so updates stay consistent with the intended
areas of responsibility.

## Recommended reading paths

### If you are new to the platform

1. `Guide Home`
2. `Parsing & QC`
3. `Workspace`
4. `Metric Computations`
5. `Visualisation Guide`

### If you are validating analysis outputs

1. `Metric Computations`
2. `Visualisation Guide`
3. `Bonus Visualisations`

### If you are troubleshooting a run

1. `Workspace`
2. `Parsing & QC`
3. `Metric Computations`
4. `Database & Schema`

## Practical use

The guide works best when used alongside the live application:

- use the homepage and workspace headers to move between the app and the docs
- open the relevant guide tab when a workflow step or output needs explanation
- return to the workspace once you know what to check or what to run next

The goal is not just to document the project, but to make the workflow easier
to understand while users are actively using the system.
