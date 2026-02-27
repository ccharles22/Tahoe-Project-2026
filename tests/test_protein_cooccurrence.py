import pandas as pd

from src.analysis_MPL.plots.protein_similarity_network import build_protein_cooccurrence_edges


def test_build_protein_cooccurrence_edges_matches_shared_mutation_sets():
    nodes = pd.DataFrame(
        {
            "variant_id": [101, 102, 103],
        }
    )

    mutations = pd.DataFrame(
        [
            {"variant_id": 101, "position": 10, "original": "A", "mutated": "V"},
            {"variant_id": 101, "position": 22, "original": "G", "mutated": "D"},
            {"variant_id": 102, "position": 10, "original": "A", "mutated": "V"},
            {"variant_id": 102, "position": 30, "original": "L", "mutated": "P"},
            {"variant_id": 103, "position": 50, "original": "Q", "mutated": "R"},
        ]
    )

    edges = build_protein_cooccurrence_edges(
        nodes,
        mutations,
        id_col="variant_id",
        variant_col="variant_id",
        position_col="position",
        original_col="original",
        mutated_col="mutated",
        min_shared=1,
        jaccard_threshold=None,
    )

    edge_records = [
        (int(row.u), int(row.v), int(row.shared), round(float(row.jaccard), 6))
        for row in edges.itertuples(index=False)
    ]

    assert edge_records == [(101, 102, 1, round(1 / 3, 6))]


def test_build_protein_cooccurrence_edges_respects_min_shared_threshold():
    nodes = pd.DataFrame({"variant_id": [201, 202]})
    mutations = pd.DataFrame(
        [
            {"variant_id": 201, "position": 5, "original": "M", "mutated": "I"},
            {"variant_id": 201, "position": 9, "original": "T", "mutated": "A"},
            {"variant_id": 202, "position": 5, "original": "M", "mutated": "I"},
        ]
    )

    edges = build_protein_cooccurrence_edges(
        nodes,
        mutations,
        id_col="variant_id",
        variant_col="variant_id",
        position_col="position",
        original_col="original",
        mutated_col="mutated",
        min_shared=2,
        jaccard_threshold=None,
    )

    assert edges.empty
