"""The numpy-free Vector column type: DDL, bind/result formats, and operator.

End-to-end retrieval correctness (the operator against real pgvector) is guarded
by the golden workflow; these lock the wire format the Postgres side expects.
"""

from sqlalchemy import select

from citebear_api.models import Chunk
from citebear_api.vector import Vector


def test_col_spec_renders_the_pg_vector_type() -> None:
    assert Vector(1536).get_col_spec() == "vector(1536)"


def test_bind_processor_formats_the_pgvector_text_literal() -> None:
    process = Vector(3).bind_processor(None)
    assert process([0.1, 0.2, 0.3]) == "[0.1,0.2,0.3]"
    assert process(None) is None


def test_result_processor_parses_back_to_floats() -> None:
    process = Vector(3).result_processor(None, None)
    assert process("[0.1,0.2,0.3]") == [0.1, 0.2, 0.3]
    assert process(None) is None


def test_bind_result_round_trip() -> None:
    dim, values = 4, [0.5, -1.5, 2.0, 0.0]
    bound = Vector(dim).bind_processor(None)(values)
    assert Vector(dim).result_processor(None, None)(bound) == values


def test_cosine_distance_compiles_to_the_operator() -> None:
    statement = select(Chunk.id).order_by(Chunk.embedding.cosine_distance([0.1, 0.2]))
    assert "<=>" in str(statement)
