"""A minimal, numpy-free pgvector column type.

pgvector-python pulls numpy (~66 MB in the serverless bundle) but we never do
numpy math — embeddings are stored as float lists and Postgres computes the
distances. This implements just the `vector(n)` column type and the
cosine-distance operator we use, so numpy can be dropped from the tree. The
Postgres `vector` extension, the HNSW index, and the `<=>` operator are
unaffected: they live in the database, not this package.
"""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import Float
from sqlalchemy.types import UserDefinedType


class Vector(UserDefinedType[Sequence[float]]):
    """Postgres `vector(dim)` column, storing/reading the `[x,y,...]` text form."""

    cache_ok = True

    def __init__(self, dim: int) -> None:
        self.dim = dim

    def get_col_spec(self, **_kw: Any) -> str:
        return f"vector({self.dim})"

    # return types are inferred: SQLAlchemy's processor Protocol wants a `value`
    # parameter that an explicit Callable[...] annotation can't express
    def bind_processor(self, dialect: Any):
        def process(value: Any) -> str | None:
            if value is None:
                return None
            return "[" + ",".join(repr(float(component)) for component in value) + "]"

        return process

    def result_processor(self, dialect: Any, coltype: Any):
        def process(value: Any) -> list[float] | None:
            if value is None:
                return None
            return [float(part) for part in value.strip("[]").split(",") if part]

        return process

    class comparator_factory(UserDefinedType.Comparator[Sequence[float]]):
        def cosine_distance(self, other: Sequence[float]) -> Any:
            # pgvector's cosine-distance operator; the right operand is bound with
            # this same type, so a query vector is formatted as `[x,y,...]`
            return self.op("<=>", return_type=Float())(other)
