import React from 'react';
import { usePanta } from '../app/PantaContext';
import { decisionCriticalQuestions, recordedDecision } from '../app/selectors';
import { goTo, type PantaRoute } from '../app/routes';
import type { ActorContext, PantaCaseSnapshot } from '../types/domain';

export interface CaseLifecycleEntry {
  route: Extract<PantaRoute, 'formation' | 'review' | 'replay'>;
  label: string;
  state: string;
  precondition: string;
}

export function caseLifecycleEntries(snapshot: PantaCaseSnapshot, actor?: ActorContext): CaseLifecycleEntry[] {
  const formation = snapshot.formation;
  const pendingReviews = snapshot.pendingReviews.filter(item => item.status === 'NEW' || item.status === 'UNDER_REVIEW').length;
  const decision = recordedDecision(snapshot);
  const decisionIssues = decisionCriticalQuestions(snapshot).length;

  const formationState = !formation
    ? 'Not prepared'
    : formation.status === 'PROPOSED_NOT_LIVE'
      ? 'Needs adoption'
      : 'Live';
  const formationPrecondition = !formation
    ? 'Case material must first produce a formation draft.'
    : formation.status === 'PROPOSED_NOT_LIVE'
      ? actor?.entitlements.includes('ADOPT_FORMATION')
        ? 'Human adoption is required before the structure becomes live.'
        : 'Adoption requires the appropriate human authority.'
      : 'The adopted case structure is active.';

  const reviewState = pendingReviews ? `${pendingReviews} waiting` : 'Clear';
  const reviewPrecondition = pendingReviews
    ? actor?.entitlements.includes('ADMIT_CASE_READING')
      ? 'Material or judgment-bearing case changes need an accountable human decision.'
      : 'Updating the institutional case requires the appropriate human authority.'
    : 'Clear factual updates are automatic; nothing exceptional needs review.';

  const decisionState = decision ? 'Recorded' : decisionIssues ? `${decisionIssues} critical issue${decisionIssues === 1 ? '' : 's'}` : 'Ready for judgment';
  const decisionPrecondition = decision
    ? `Recorded against case version ${decision.caseVersion}.`
    : actor?.entitlements.includes('RECORD_DECISION')
      ? decisionIssues
        ? 'Review the decision-critical underwriting questions, then record accountable human judgment.'
        : 'Record an accountable human judgment against the current case.'
      : 'Recording requires the appropriate human authority.';

  return [
    { route: 'formation', label: 'Formation', state: formationState, precondition: formationPrecondition },
    { route: 'review', label: 'Review changes', state: reviewState, precondition: reviewPrecondition },
    { route: 'replay', label: 'Replay & Decision', state: decisionState, precondition: decisionPrecondition },
  ];
}

export function CaseLifecycle() {
  const { snapshot, actor } = usePanta();
  if (!snapshot) return null;
  const entries = caseLifecycleEntries(snapshot, actor);

  return <section className="p-case-lifecycle" aria-labelledby="case-lifecycle-title">
    <header>
      <div>
        <div className="p-kicker">Case lifecycle</div>
        <h2 id="case-lifecycle-title">Continue with the institutional case</h2>
      </div>
      <p>Formation, exceptional case changes, and the decision remain explicit human-governed steps.</p>
    </header>
    <div className="p-lifecycle-list">
      {entries.map((entry, index) => <button key={entry.route} onClick={() => goTo(entry.route)}>
        <span className="p-lifecycle-index">{String(index + 1).padStart(2, '0')}</span>
        <span className="p-lifecycle-copy"><strong>{entry.label}</strong><small>{entry.precondition}</small></span>
        <span className="p-lifecycle-state">{entry.state}</span>
        <span aria-hidden="true">→</span>
      </button>)}
    </div>
  </section>;
}
