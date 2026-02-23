from app.services.sequence.sequence_service import call_mutations_against_wt


def test_mutation_calling_entrypoint_imports():
    assert callable(call_mutations_against_wt)
