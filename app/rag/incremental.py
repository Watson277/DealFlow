"""Hashing and deterministic Child classification for incremental knowledge updates."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from app.rag.hierarchical import ChildChunk

ChangeKind = Literal["UNCHANGED", "MOVED", "MODIFIED", "ADDED"]


@dataclass(frozen=True, slots=True)
class ExistingChild:
    child_chunk_id: str
    parent_id: str
    qdrant_point_id: str
    chunk_order: int
    child_order: int
    structural_hash: str
    content_hash: str
    embedding_hash: str


@dataclass(frozen=True, slots=True)
class ChildCandidate:
    chunk: ChildChunk
    structural_hash: str
    embedding_hash: str


@dataclass(frozen=True, slots=True)
class ChildDecision:
    candidate: ChildCandidate
    kind: ChangeKind
    previous: ExistingChild | None = None


@dataclass(frozen=True, slots=True)
class ChunkChangeSet:
    decisions: tuple[ChildDecision, ...]
    deleted: tuple[ExistingChild, ...]

    def of_kind(self, *kinds: ChangeKind) -> tuple[ChildDecision, ...]:
        return tuple(item for item in self.decisions if item.kind in kinds)


def normalize_document_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]
    compact: list[str] = []
    blank = False
    for line in lines:
        if line:
            compact.append(line)
            blank = False
        elif not blank:
            compact.append("")
            blank = True
    return "\n".join(compact).strip()


def document_content_hash(text: str) -> str:
    return hashlib.sha256(normalize_document_text(text).encode("utf-8")).hexdigest()


def child_structural_hash(chunk: ChildChunk) -> str:
    payload = {
        "source_type": chunk.location.source_type,
        "section_path": list(chunk.section_path),
        "block_types": list(chunk.block_types),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def child_embedding_hash(chunk: ChildChunk, *, model: str, dimensions: int) -> str:
    material = f"{model}\x1f{dimensions}\x1f{chunk.embedding_text}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def candidates_for(
    chunks: Sequence[ChildChunk],
    *,
    model: str,
    dimensions: int,
) -> tuple[ChildCandidate, ...]:
    return tuple(
        ChildCandidate(
            chunk=chunk,
            structural_hash=child_structural_hash(chunk),
            embedding_hash=child_embedding_hash(chunk, model=model, dimensions=dimensions),
        )
        for chunk in chunks
    )


def classify_children(
    previous: Sequence[ExistingChild],
    current: Sequence[ChildCandidate],
) -> ChunkChangeSet:
    remaining_old = list(previous)
    remaining_new = list(current)
    decisions: list[ChildDecision] = []

    def match(
        predicate: Callable[[ExistingChild, ChildCandidate], bool],
        kind: ChangeKind,
    ) -> None:
        nonlocal remaining_new
        next_new: list[ChildCandidate] = []
        for candidate in remaining_new:
            matches = [old for old in remaining_old if predicate(old, candidate)]
            if not matches:
                next_new.append(candidate)
                continue
            selected = min(matches, key=lambda old: abs(old.chunk_order - candidate.chunk.order))
            remaining_old.remove(selected)
            decisions.append(ChildDecision(candidate=candidate, kind=kind, previous=selected))
        remaining_new = next_new

    match(
        lambda old, new: (
            old.child_chunk_id == new.chunk.chunk_id
            and old.embedding_hash == new.embedding_hash
        ),
        "UNCHANGED",
    )
    match(lambda old, new: old.embedding_hash == new.embedding_hash, "MOVED")
    match(lambda old, new: old.child_chunk_id == new.chunk.chunk_id, "MODIFIED")
    match(lambda old, new: old.structural_hash == new.structural_hash, "MODIFIED")
    decisions.extend(ChildDecision(candidate=item, kind="ADDED") for item in remaining_new)
    decisions.sort(key=lambda item: item.candidate.chunk.order)
    return ChunkChangeSet(decisions=tuple(decisions), deleted=tuple(remaining_old))
