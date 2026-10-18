"""Tests for semantic entity triple extraction and bi-temporal concepts."""

import pytest
from app.memory.semantic import semantic_memory


def test_devops_triple_extraction_migration():
    text = "We migrated Prod_DB from Postgres to FalkorDB for real-time memory."
    triples = semantic_memory.extract_triples_from_text(text)

    assert len(triples) >= 1
    t = triples[0]
    assert t.subject == "Prod_DB"
    assert t.predicate == "USES_TECH"
    assert t.object == "FalkorDB"


def test_devops_triple_extraction_baseline():
    text = "Our primary production database is Postgres."
    triples = semantic_memory.extract_triples_from_text(text)

    assert len(triples) >= 1
    t = triples[0]
    assert t.subject in ("Prod_DB", "Primary_Production_DB", "Primary_Production_Database", "Production_Database")
    assert t.predicate in ("USES_TECH", "IS_A", "IS")
    assert t.object in ("PostgreSQL", "Postgres")
