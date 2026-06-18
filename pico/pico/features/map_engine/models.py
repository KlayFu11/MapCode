"""MapEngine-owned data transfer objects."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class DefinitionRecord:
    name: str
    path: str
    line: int
    kind: str


@dataclass(frozen=True)
class ReferenceRecord:
    name: str
    path: str
    line: int


@dataclass(frozen=True)
class FileRecord:
    path: str
    mtime_ns: int
    size: int
    parser_version: str
    query_version: str
    schema_version: str


@dataclass(frozen=True)
class RankContributorEvidence:
    source_path: str
    identifier: str
    weighted_edge: float
    weight_multiplier: float
    weight_reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class RenderedFileEvidence:
    path: str
    node_pagerank: float
    pagerank_norm: float
    definition_rank_sum: float
    render_rank: int
    reason_codes: tuple[str, ...]
    prompt_symbol_hits: tuple[str, ...]
    prompt_path_ident_hits: tuple[str, ...]
    rendered_symbols: tuple[str, ...]
    top_rank_contributors: tuple[RankContributorEvidence, ...]


@dataclass(frozen=True)
class OmittedFileEvidence:
    path: str
    node_pagerank: float
    pagerank_norm: float
    definition_rank_sum: float
    omission_reason: str
    reason_codes: tuple[str, ...]
    prompt_symbol_hits: tuple[str, ...]
    prompt_path_ident_hits: tuple[str, ...]
    top_rank_contributors: tuple[RankContributorEvidence, ...]


@dataclass(frozen=True)
class RankingEvidence:
    policy_version: str
    algorithm: Literal["pagerank", "personalized_pagerank", "stable_path_fallback"]
    focus_fnames: tuple[str, ...]
    ident_boost_inputs: tuple[str, ...]
    focus_personalization_files: tuple[str, ...]
    path_personalization_files: tuple[str, ...]
    personalization_files: tuple[str, ...]
    top_ranked_files: tuple[str, ...]


@dataclass(frozen=True)
class RenderingEvidence:
    target_tokens: int
    target_chars: int
    used_chars: int
    estimated_tokens: int
    budget_reduction_applied: bool
    focus_truncated: bool


@dataclass(frozen=True)
class CacheEvidence:
    read_status: Literal["hit", "miss", "read_failed"]
    write_status: Literal["not_needed", "written", "write_failed"]
    reused_files: tuple[str, ...]
    parsed_files: tuple[str, ...]
    skipped_files: tuple[str, ...]


@dataclass(frozen=True)
class IndexStatus:
    index_snapshot_id: str
    cache_status: CacheEvidence
    file_count: int
    definition_count: int
    reference_count: int
