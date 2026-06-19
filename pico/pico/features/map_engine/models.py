"""MapEngine-owned data transfer objects."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal


@dataclass(frozen=True)
class PromptAnalysis:
    branch: Literal["specific", "fuzzy"]
    mentioned_files: tuple[str, ...]
    mentioned_idents: tuple[str, ...]
    effective_symbol_hits: tuple[str, ...]
    path_ident_hits: tuple[str, ...]
    path_ident_hit_files: Mapping[str, tuple[str, ...]]

    def __post_init__(self) -> None:
        hit_files = {
            ident: tuple(paths)
            for ident, paths in self.path_ident_hit_files.items()
        }
        if tuple(hit_files) != self.path_ident_hits:
            raise ValueError("path_ident_hit_files keys must match path_ident_hits order")
        if any(paths != tuple(sorted(paths)) for paths in hit_files.values()):
            raise ValueError("path_ident_hit_files values must be sorted")
        object.__setattr__(
            self,
            "path_ident_hit_files",
            MappingProxyType(hit_files),
        )


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


@dataclass(frozen=True)
class MapContextEvidence:
    schema_version: str
    index_snapshot_id: str
    analysis: PromptAnalysis
    ranking: RankingEvidence
    rendering: RenderingEvidence
    rendered_files: tuple[RenderedFileEvidence, ...]
    omitted_files: tuple[OmittedFileEvidence, ...]
    cache_status: CacheEvidence
    duration_ms: int


@dataclass(frozen=True)
class MapResult:
    mode: Literal["broad", "focused"]
    repo_map_text: str
    focus_fnames: tuple[str, ...]
    rendered_files: tuple[str, ...]
    rendered_symbols: tuple[str, ...]
    evidence: MapContextEvidence

    def __post_init__(self) -> None:
        if self.focus_fnames != self.evidence.ranking.focus_fnames:
            raise ValueError("focus_fnames must match evidence.ranking.focus_fnames")


@dataclass(frozen=True)
class SelectorCandidateCatalog:
    index_snapshot_id: str
    candidate_paths: tuple[str, ...]
    rendered_paths: tuple[str, ...]
    rendered_text: str
    file_count: int
    definition_count: int
    rendered_file_count: int
    rendered_definition_count: int
    estimated_tokens: int
    truncated: bool

    def __post_init__(self) -> None:
        if self.candidate_paths != tuple(sorted(self.candidate_paths)):
            raise ValueError("candidate_paths must be sorted")
        if self.rendered_paths != tuple(sorted(self.rendered_paths)):
            raise ValueError("rendered_paths must be sorted")
        candidate_path_set = set(self.candidate_paths)
        if any(path not in candidate_path_set for path in self.rendered_paths):
            raise ValueError("rendered_paths must be a subset of candidate_paths")
