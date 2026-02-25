# Validation Checks

Complete reference of all validation checks performed by the QC system.

---

## Check Categories

```mermaid
flowchart TB
    subgraph Checks["QC Validation Checks"]
        direction TB
        subgraph PerRecord["Per-Record Checks"]
            PR1[Required Fields]
            PR2[Yield Range]
            PR3[Data Type Validation]
        end
        
        subgraph CrossRecord["Cross-Record Checks"]
            CR1[Duplicate Detection]
            CR2[Batch Consistency]
            CR3[Generation Sequence]
        end
    end
    
    style PerRecord fill:#4dabf7,color:#fff
    style CrossRecord fill:#7950f2,color:#fff
```

---

## Per-Record Checks

These checks validate each row individually.

### 1. Required Fields

| Field | Required | Example |
|-------|----------|---------|
| `plasmid_variant_index` | ✅ Yes | `BSU_Pol_001` |
| `generation` | ✅ Yes | `G0`, `G1`, `G2` |
| `dna_yield_fg` | ✅ Yes | `1523.45` |
| `protein_yield_pg` | ✅ Yes | `456.78` |

!!! failure "Missing Field Error"
    ```
    ERROR: Row 45 - Missing required field: dna_yield_fg
    ```

---

### 2. Yield Range Validation

#### DNA Yield Checks

| Check Type | Condition | Result |
|------------|-----------|--------|
| **Critical Low** | `< 300 fg` | ❌ ERROR |
| **Warning Low** | `< P1` | ⚠️ WARNING |
| **Normal** | `P1 ≤ x ≤ P99` | ✅ OK |
| **Warning High** | `> P99` | ⚠️ WARNING |
| **Critical High** | `> 5000 fg` | ❌ ERROR |

#### Protein Yield Checks

| Check Type | Condition | Result |
|------------|-----------|--------|
| **Critical Low** | `< 20 pg` | ❌ ERROR |
| **Warning Low** | `< P1` | ⚠️ WARNING |
| **Normal** | `P1 ≤ x ≤ P99` | ✅ OK |
| **Warning High** | `> P99` | ⚠️ WARNING |
| **Critical High** | `> 2000 pg` | ❌ ERROR |

---

### 3. Data Type Validation

```mermaid
flowchart LR
    V[Value] --> T{Type Check}
    T -->|Valid Number| OK[✅ Accept]
    T -->|Empty/Null| M[Handle Missing]
    T -->|Invalid| E[❌ ERROR]
    
    M --> M1{Required?}
    M1 -->|Yes| E
    M1 -->|No| OK
    
    style OK fill:#51cf66
    style E fill:#ff6b6b,color:#fff
```

| Field | Expected Type | Invalid Examples |
|-------|---------------|------------------|
| `dna_yield_fg` | Float | `"N/A"`, `"pending"`, `""` |
| `protein_yield_pg` | Float | `"null"`, `"#REF!"`, `"-"` |
| `generation` | String | (must not be empty) |
| `plasmid_variant_index` | String | (must not be empty) |

---

## Cross-Record Checks

These checks validate relationships between records.

### 1. Duplicate Detection

Checks for duplicate `plasmid_variant_index` within the same generation.

```mermaid
flowchart LR
    subgraph Records["Uploaded Records"]
        R1["BSU_Pol_001 (G1)"]
        R2["BSU_Pol_002 (G1)"]
        R3["BSU_Pol_001 (G1)"]
    end
    
    subgraph Check["Duplicate Check"]
        D{Same variant<br/>+ Same gen?}
    end
    
    subgraph Result["Result"]
        W["⚠️ WARNING:<br/>Duplicate detected"]
    end
    
    R1 --> D
    R3 --> D
    D -->|Yes| W
    
    style W fill:#ffd43b
```

!!! warning "Duplicate Warning"
    ```
    WARNING: Duplicate plasmid_variant_index 'BSU_Pol_001' in generation G1 (rows 12, 78)
    ```

---

### 2. Batch Consistency

Validates that batch metadata is consistent across files.

| Check | Description |
|-------|-------------|
| Experiment Name | Must match existing experiment or will be created |
| Generation Sequence | G0 → G1 → G2 (no gaps) |
| Wild Type Reference | Must exist in database |

---

### 3. Generation Sequence

```mermaid
flowchart LR
    subgraph Valid["✅ Valid Sequences"]
        V1["G0"]
        V2["G0 → G1"]
        V3["G0 → G1 → G2"]
    end
    
    subgraph Invalid["❌ Invalid"]
        I1["G1 (no G0)"]
        I2["G0 → G2 (gap)"]
        I3["G-1"]
    end
    
    style Valid fill:#51cf66
    style Invalid fill:#ff6b6b,color:#fff
```

---

## Check Execution Order

```mermaid
sequenceDiagram
    participant F as File
    participant P as Parser
    participant V as Validator
    participant DB as Database
    
    F->>P: Upload file
    P->>P: Parse records
    
    loop Each Record
        P->>V: Per-record validation
        V-->>P: Errors/Warnings
    end
    
    P->>V: Cross-record validation
    V-->>P: Errors/Warnings
    
    alt No Errors
        P->>DB: Insert records
        DB-->>P: Success
    else Has Errors
        P-->>F: Reject with details
    end
```

---

## Error vs Warning Behaviour

| Severity | Effect | Record Saved? |
|----------|--------|---------------|
| ❌ ERROR | Upload rejected | No |
| ⚠️ WARNING | Flagged but accepted | Yes |

!!! danger "One Error = Full Rejection"
    If **any** record has an error, the entire upload is rejected. Fix all errors before re-uploading.

---

## QC Report Structure

After validation, you receive a structured report:

```json
{
  "status": "warnings",
  "total_records": 301,
  "errors": [],
  "warnings": [
    {
      "row": 45,
      "field": "dna_yield_fg",
      "value": 312.5,
      "message": "Below P1 threshold (395.2)",
      "severity": "warning"
    },
    {
      "row": 198,
      "field": "protein_yield_pg", 
      "value": 1847.3,
      "message": "Above P99 threshold (1823.1)",
      "severity": "warning"
    }
  ],
  "thresholds_used": {
    "dna_yield_low": 395.2,
    "dna_yield_high": 1823.4,
    "protein_yield_low": 45.6,
    "protein_yield_high": 1789.2
  }
}
```

---

## Customising Checks

To add custom validation rules, modify `parsing/qc.py`:

```python
def custom_check(record: dict) -> list[dict]:
    """Add your custom validation logic."""
    warnings = []
    
    # Example: Flag specific variant patterns
    if "control" in record.get("plasmid_variant_index", "").lower():
        if record.get("dna_yield_fg", 0) < 500:
            warnings.append({
                "field": "dna_yield_fg",
                "message": "Control variant has unusually low yield"
            })
    
    return warnings
```

---

## Related Topics

- [QC Overview](overview.md) - Architecture explanation
- [Threshold Configuration](thresholds.md) - Adjust limits
