# Quality Control Overview

The QC system uses a **two-tier threshold architecture** to identify data quality issues while accommodating batch-to-batch variation.

---

## Architecture Overview

```mermaid
flowchart TB
    subgraph Input["📥 Input Data"]
        R[Parsed Records]
    end
    
    subgraph Adaptive["🎯 Tier 1: Adaptive Thresholds"]
        direction TB
        A1[Collect all yield values]
        A2[Calculate P1 & P99 percentiles]
        A3[Set warning bounds]
        A1 --> A2 --> A3
    end
    
    subgraph Critical["🚨 Tier 2: Critical Limits"]
        direction TB
        C1[Fixed biological limits]
        C2[Instrument specifications]
        C1 --- C2
    end
    
    subgraph Validation["✅ Validation"]
        V1[Per-Record Checks]
        V2[Cross-Record Checks]
    end
    
    subgraph Output["📤 Results"]
        O1[⚠️ Warnings]
        O2[❌ Errors]
    end
    
    R --> Adaptive
    R --> Critical
    Adaptive --> V1
    Critical --> V1
    V1 --> V2
    V2 --> O1
    V2 --> O2
```

---

## Two-Tier Threshold System

### Tier 1: Adaptive Warnings (Percentile-Based)

Warnings flag **statistical outliers** relative to the current dataset.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '14px'}}}%%
graph LR
    subgraph Dataset["Your Dataset (n=301)"]
        D1["DNA Yields: 389 - 2000 fg"]
    end
    
    subgraph Calculation["Percentile Calculation"]
        P1["P1 = 395 fg"]
        P99["P99 = 1850 fg"]
    end
    
    subgraph Result["Warning Thresholds"]
        W1["< 395 fg → ⚠️ Low"]
        W2["> 1850 fg → ⚠️ High"]
    end
    
    Dataset --> Calculation --> Result
```

**Why percentiles?**

| Method | Problem |
|--------|---------|
| Fixed thresholds | Don't adapt to batch variation |
| Mean ± 2σ (Z-scores) | Assumes normal distribution |
| **P1/P99 Percentiles** | ✅ Non-parametric, robust to skew |

---

### Tier 2: Critical Errors (Fixed Limits)

Errors flag values that are **biologically impossible** or indicate instrument failure.

| Metric | Critical Min | Critical Max | Rationale |
|--------|--------------|--------------|-----------|
| DNA Yield | 300 fg | 5,000 fg | Below detection / saturation |
| Protein Yield | 20 pg | 2,000 pg | Expression system limits |

!!! danger "Critical Limit Violations"
    Values outside critical limits **always generate errors** and the upload is rejected.

---

## Threshold Visualisation

```
DNA Yield Thresholds
═══════════════════════════════════════════════════════════════════════════════

     0        300              P1            MEDIAN           P99           5000
     │         │                │               │               │              │
     ▼         ▼                ▼               ▼               ▼              ▼
─────┴─────────┼────────────────┼───────────────┼───────────────┼──────────────┴─────
     │  ERROR  │    WARNING     │      OK       │    WARNING    │     ERROR    │
     │ (reject)│  (flag only)   │   (accept)    │  (flag only)  │   (reject)   │
     └─────────┴────────────────┴───────────────┴───────────────┴──────────────┘
         ▲                            ▲                              ▲
         │                            │                              │
    Instrument                   Batch-specific                 Instrument
    Detection                    percentiles                    Saturation
    Limit                                                       Limit
```

---

## Configuration

Thresholds are configured in `parsing/config.py`:

=== "Adaptive Settings"

    ```python
    # Percentile-based thresholds
    QC_PERCENTILE_MODE = True
    QC_PERCENTILE_LOW = 1.0      # P1
    QC_PERCENTILE_HIGH = 99.0    # P99
    QC_MIN_SAMPLES_FOR_PERCENTILES = 30
    ```

=== "Critical Limits"

    ```python
    # Absolute safety limits
    DNA_YIELD_CRITICAL_MIN = 300.0
    DNA_YIELD_CRITICAL_MAX = 5000.0
    PROTEIN_YIELD_CRITICAL_MIN = 20.0
    PROTEIN_YIELD_CRITICAL_MAX = 2000.0
    ```

---

## Decision Flow

```mermaid
flowchart TD
    V[Yield Value] --> C1{Below Critical Min?}
    C1 -->|Yes| E1[❌ ERROR: Reject]
    C1 -->|No| C2{Above Critical Max?}
    C2 -->|Yes| E2[❌ ERROR: Reject]
    C2 -->|No| W1{Below P1?}
    W1 -->|Yes| W3[⚠️ WARNING: Flag]
    W1 -->|No| W2{Above P99?}
    W2 -->|Yes| W4[⚠️ WARNING: Flag]
    W2 -->|No| OK[✅ OK: Accept]
    
    W3 --> OK2[Record Accepted]
    W4 --> OK2
    
    style E1 fill:#ff6b6b,color:#fff
    style E2 fill:#ff6b6b,color:#fff
    style W3 fill:#ffd43b
    style W4 fill:#ffd43b
    style OK fill:#51cf66
    style OK2 fill:#51cf66
```

---

## Benefits of This Approach

!!! success "Adaptive to Each Experiment"
    Different batches, reagent lots, and assay conditions produce different expected ranges. Percentile-based thresholds automatically adjust.

!!! success "Catches Real Errors"
    Critical limits based on physical reality ensure impossible values are always flagged.

!!! success "Reduces False Positives"
    Using P1/P99 (not P5/P95) means only the most extreme 2% of values are flagged, reducing noise.

!!! success "Non-Parametric"
    Works correctly even when yield distributions are skewed (common in biological data).

---

## Related Topics

- [Validation Checks](validation-checks.md) - Detailed list of all checks
- [Threshold Configuration](thresholds.md) - How to customise thresholds
