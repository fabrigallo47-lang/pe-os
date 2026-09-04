"""Internal, bounded truth-maintenance primitives for consequence evaluation.

The public V20 contract remains three-valued.  Internally, however, missing
evidence and conflicting evidence are different states.  This module models
that distinction as two independent evidence bits and retains bounded minimal
support environments for deterministic why/why-not reasoning.

It is intentionally independent of the Canonical Investment Case ontology and
does not serialize into the transition output.  The runtime adapter decides how
an internal state maps to the existing public contract and governance stops.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Sequence


class EvidenceState(Enum):
    """Belnap-style evidence state represented by support/refutation bits."""

    NEITHER = (False, False)
    TRUE = (True, False)
    FALSE = (False, True)
    BOTH = (True, True)

    @property
    def supports(self) -> bool:
        return bool(self.value[0])

    @property
    def refutes(self) -> bool:
        return bool(self.value[1])

    @property
    def public_state(self) -> str:
        """Map to the unchanged V20 ``TRUE/FALSE/UNKNOWN`` vocabulary."""

        if self is EvidenceState.TRUE:
            return "TRUE"
        if self is EvidenceState.FALSE:
            return "FALSE"
        return "UNKNOWN"

    @classmethod
    def from_public(cls, value: str) -> "EvidenceState":
        return {
            "TRUE": cls.TRUE,
            "FALSE": cls.FALSE,
            "UNKNOWN": cls.NEITHER,
            # Accepted only at internal call sites and never emitted publicly.
            "CONFLICTED": cls.BOTH,
        }.get(str(value), cls.NEITHER)


def evidence_and(states: Sequence[EvidenceState]) -> EvidenceState:
    """Conjunction in the four-valued evidence lattice."""

    if not states:
        return EvidenceState.NEITHER
    return EvidenceState((
        all(state.supports for state in states),
        any(state.refutes for state in states),
    ))


def evidence_or(states: Sequence[EvidenceState]) -> EvidenceState:
    """Disjunction in the four-valued evidence lattice."""

    if not states:
        return EvidenceState.NEITHER
    return EvidenceState((
        any(state.supports for state in states),
        all(state.refutes for state in states),
    ))


Environment = frozenset[str]


def _minimal_environments(
    environments: Iterable[Environment],
    limit: int,
) -> tuple[tuple[Environment, ...], bool]:
    """Return deterministic subset-minimal labels with a bounded witness set."""

    ordered = sorted(
        {frozenset(environment) for environment in environments},
        key=lambda environment: (len(environment), tuple(sorted(environment))),
    )
    minimal: list[Environment] = []
    for environment in ordered:
        if any(existing <= environment for existing in minimal):
            continue
        minimal.append(environment)
    truncated = len(minimal) > limit
    return tuple(minimal[:limit]), truncated


def _bounded_environment_product(
    labels: Sequence[Sequence[Environment]],
    limit: int,
) -> tuple[tuple[Environment, ...], bool]:
    """Build conjunction labels without materializing an unbounded product.

    Each intermediate frontier is subset-minimized and capped before the next
    antecedent is joined.  This keeps explanation work bounded by ``limit^2``
    per antecedent; the independent evidence bits remain the source of exact
    truth semantics.
    """

    if not labels or any(not environments for environments in labels):
        return (), False

    frontier: tuple[Environment, ...] = (frozenset(),)
    truncated = False
    for environments in labels:
        frontier, step_truncated = _minimal_environments(
            (
                base_environment | extension_environment
                for base_environment in frontier
                for extension_environment in environments
            ),
            limit,
        )
        truncated = truncated or step_truncated
    return frontier, truncated


@dataclass(frozen=True)
class ProofNode:
    proposition_id: str
    state: EvidenceState
    positive_environments: tuple[Environment, ...]
    negative_environments: tuple[Environment, ...]
    labels_truncated: bool = False


@dataclass(frozen=True)
class Justification:
    proposition_id: str
    rule_id: str
    operator: str
    antecedent_ids: tuple[str, ...]


class ProofGraph:
    """Small ATMS-like graph retaining bounded minimal derivation labels.

    Truth bits are exact.  Only the number of explanatory environments is
    bounded, preventing combinatorial label growth from changing semantics.
    """

    def __init__(self, *, max_environments_per_sign: int = 64) -> None:
        if max_environments_per_sign < 1:
            raise ValueError("max_environments_per_sign must be positive")
        self.max_environments_per_sign = max_environments_per_sign
        self._nodes: dict[str, ProofNode] = {}
        self._justifications: list[Justification] = []

    @property
    def justifications(self) -> tuple[Justification, ...]:
        return tuple(self._justifications)

    def node(self, proposition_id: str) -> ProofNode:
        return self._nodes[proposition_id]

    def ensure_fact(
        self,
        proposition_id: str,
        state: EvidenceState,
        *,
        evidence_token: str | None = None,
    ) -> ProofNode:
        existing = self._nodes.get(proposition_id)
        if existing is not None:
            if existing.state is not state:
                raise ValueError(
                    f"fact {proposition_id} was registered with conflicting states"
                )
            return existing
        token = evidence_token or proposition_id
        positive = (frozenset({token}),) if state.supports else ()
        negative = (frozenset({token}),) if state.refutes else ()
        node = ProofNode(proposition_id, state, positive, negative)
        self._nodes[proposition_id] = node
        return node

    def _store_derived(
        self,
        proposition_id: str,
        state: EvidenceState,
        positive_environments: Iterable[Environment],
        negative_environments: Iterable[Environment],
        *,
        rule_id: str,
        operator: str,
        antecedent_ids: Sequence[str],
        labels_truncated: bool = False,
    ) -> ProofNode:
        if proposition_id in self._nodes:
            raise ValueError(f"duplicate proof proposition: {proposition_id}")
        positive, positive_truncated = _minimal_environments(
            positive_environments,
            self.max_environments_per_sign,
        )
        negative, negative_truncated = _minimal_environments(
            negative_environments,
            self.max_environments_per_sign,
        )
        node = ProofNode(
            proposition_id=proposition_id,
            state=state,
            positive_environments=positive,
            negative_environments=negative,
            labels_truncated=(
                labels_truncated or positive_truncated or negative_truncated
            ),
        )
        self._nodes[proposition_id] = node
        self._justifications.append(
            Justification(
                proposition_id=proposition_id,
                rule_id=rule_id,
                operator=operator,
                antecedent_ids=tuple(antecedent_ids),
            )
        )
        return node

    def derive_and(
        self,
        proposition_id: str,
        antecedent_ids: Sequence[str],
        *,
        rule_id: str,
    ) -> ProofNode:
        antecedents = [self.node(item) for item in antecedent_ids]
        state = evidence_and([item.state for item in antecedents])
        positive, product_truncated = _bounded_environment_product(
            [item.positive_environments for item in antecedents],
            self.max_environments_per_sign,
        )
        negative = (
            environment
            for item in antecedents
            for environment in item.negative_environments
        )
        return self._store_derived(
            proposition_id,
            state,
            positive,
            negative,
            rule_id=rule_id,
            operator="AND",
            antecedent_ids=antecedent_ids,
            labels_truncated=(
                product_truncated
                or any(item.labels_truncated for item in antecedents)
            ),
        )

    def derive_or(
        self,
        proposition_id: str,
        antecedent_ids: Sequence[str],
        *,
        rule_id: str,
    ) -> ProofNode:
        antecedents = [self.node(item) for item in antecedent_ids]
        state = evidence_or([item.state for item in antecedents])
        positive = (
            environment
            for item in antecedents
            for environment in item.positive_environments
        )
        negative, product_truncated = _bounded_environment_product(
            [item.negative_environments for item in antecedents],
            self.max_environments_per_sign,
        )
        return self._store_derived(
            proposition_id,
            state,
            positive,
            negative,
            rule_id=rule_id,
            operator="OR",
            antecedent_ids=antecedent_ids,
            labels_truncated=(
                product_truncated
                or any(item.labels_truncated for item in antecedents)
            ),
        )

    def derive_with_counterevidence(
        self,
        proposition_id: str,
        support_id: str,
        counterevidence_id: str,
        *,
        rule_id: str,
    ) -> ProofNode:
        """Retain support and refutation independently for a governed route."""

        support = self.node(support_id)
        counterevidence = self.node(counterevidence_id)
        state = EvidenceState((
            support.state.supports,
            support.state.refutes or counterevidence.state.supports,
        ))
        return self._store_derived(
            proposition_id,
            state,
            support.positive_environments,
            (
                *support.negative_environments,
                *counterevidence.positive_environments,
            ),
            rule_id=rule_id,
            operator="AND_NOT_COUNTEREVIDENCE",
            antecedent_ids=(support_id, counterevidence_id),
            labels_truncated=(
                support.labels_truncated or counterevidence.labels_truncated
            ),
        )
