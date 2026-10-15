"""Tests for Working Memory task specifications and DAG model verification."""

import pytest
from app.memory.working import SubTaskSpec


def test_subtask_spec_creation():
    st = SubTaskSpec(
        title="Check DB",
        description="Verify database configuration",
        depends_on=["st_prev_1"],
    )
    assert st.title == "Check DB"
    assert st.depends_on == ["st_prev_1"]
    assert st.id.startswith("st_")
