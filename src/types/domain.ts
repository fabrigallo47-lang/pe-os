/**
 * PANTA frontend projection contract — v4.0 FINAL
 *
 * AUTHORITY ORDER
 * 1. Existing versioned runtime contracts + conformance tests remain binding until explicitly migrated.
 * 2. Target semantic contract: panta.universal_investment_kernel@0.1.0 (DESIGN_HANDOFF).
 * 3. Target relation contract: panta.relation_and_update_contract@0.1.0 (DESIGN_HANDOFF).
 * 4. This file is a UI projection of those contracts. It is never the ontology/source of truth.
 *
 * UI-only containers are explicitly marked as projections below. Investor-facing labels may differ
 * from kernel names, but canonical object/relation identity must not.
 */

export type Id = string;

/** Canonical kernel object families exposed through the UI projection. */
export type KernelObjectKind =
  | 'case'
  | 'actor'
  | 'source'
  | 'sourceVersion'
  | 'claim'
  | 'metricDefinition'
  | 'metricObservation'
  | 'question'
  | 'unknown'
  | 'humanPosition'
  | 'caseReading'
  | 'assumption'
  | 'risk'
  | 'modelNode'
  | 'condition'
  | 'decision'
  | 'workItem'
  | 'artifact'
  | 'outcome';

/** UI/archetype projections. These are NOT new ontology types. */
export type ProjectionKind =
  | 'workstream'      // grouping from QuestionSpine / archetype projection
  | 'finding'         // review-queue projection over a proposed object/relation/reading change
  | 'quantity'        // unified UI projection of MetricObservation / ModelNode
  | 'artifactBlock'   // addressable region within an ArtifactVersion
  | 'caseEvent';      // ledger event projection for UI/history

export type ObjectKind = KernelObjectKind | ProjectionKind;

/** Exact canonical relation vocabulary from panta.relation_and_update_contract@0.1.0. */
export type RelationType =
  | 'ABOUT'
  | 'BEARS_ON'
  | 'SUPPORTS'
  | 'CHALLENGES'
  | 'CONTRADICTS'
  | 'CORROBORATES'
  | 'DERIVES_FROM'
  | 'DRIVES'
  | 'CONDITIONS'
  | 'RESOLVES'
  | 'ADOPTS'
  | 'SUPERSEDES'
  | 'PRODUCES';

/** Kernel state axes. Keep separate: epistemic truth is not freshness, question state or decision state. */
export type InstitutionalState = 'CANDIDATE' | 'CURRENT' | 'APPROVED' | 'REJECTED' | 'RETIRED';
export type EpistemicStatus = 'UNEXAMINED' | 'INSUFFICIENT' | 'SUPPORTED' | 'CONTESTED' | 'INVALIDATED' | 'STALE';
export type FreshnessStatus = 'CURRENT' | 'STALE' | 'EXPIRED' | 'UNKNOWN';
export type QuestionStatus = 'OPEN' | 'PARTIALLY_RESOLVED' | 'RESOLVED' | 'RISK_ACCEPTED' | 'BLOCKED' | 'RETIRED' | 'STALE';
export type WorkStatus = 'PROPOSED' | 'PLANNED' | 'ACTIVE' | 'BLOCKED' | 'COMPLETED' | 'CANCELLED' | 'REOPENED';
export type ConditionStatus = 'PROPOSED' | 'OPEN' | 'SATISFIED' | 'FAILED' | 'WAIVED' | 'EXPIRED' | 'STALE';
export type DecisionLinkStatus = 'NO_DECISION' | 'DECIDED' | 'DECIDED_WITH_CONDITIONS' | 'SUPERSEDED' | 'BASIS_STALE';

/** UI review/sync state, not epistemic ontology. */
export type ReviewStatus = 'NEW' | 'UNDER_REVIEW' | 'ADMITTED' | 'CORRECTED' | 'REJECTED';
export type ArtifactSyncStatus = 'CURRENT' | 'STALE' | 'SYNCING';
export type ArtifactAuthorship = 'CASE_BACKED' | 'HUMAN_AUTHORED' | 'PANTA_SUGGESTION';
/** UI decision-record availability. Canonical Decision itself is an immutable event-backed object. */
export type DecisionStatus = 'OPEN' | 'RECORDED';
/** UI projection over an Unknown lifecycle; closure must be backed by evidence/decision events. */
export type UnknownStatus = 'OPEN' | 'RESOLVED' | 'RISK_ACCEPTED' | 'RETIRED';

export type Entitlement =
  | 'READ_CASE'
  | 'ADD_MATERIAL'
  | 'REVIEW_CASE_CHANGE'
  | 'ADMIT_CASE_READING'
  | 'EDIT_HUMAN_POSITION'
  | 'ADOPT_WORK_ITEM'
  | 'ASSIGN_WORK_ITEM'
  | 'ADOPT_FORMATION'
  | 'RECORD_DECISION'
  | 'EDIT_ARTIFACT'
  | 'SYNC_ARTIFACT'
  | 'EXTERNAL_ACTION';

export interface Actor {
  id: Id;
  type: 'PERSON' | 'TEAM' | 'COMMITTEE' | 'ORGANISATION' | 'SYSTEM';
  displayName: string;
  role?: string;
  organisation?: string;
}

export interface ActorContext {
  actorId: Id;
  entitlements: Entitlement[];
}

export interface SessionContext {
  actor: ActorContext;
  actors?: Actor[];
}

export interface ObjectRef {
  id: Id;
  kind: ObjectKind;
  label: string;
}

/** Lightweight case header projection; the canonical Case remains in the ledger. */
export interface CaseRef {
  id: Id;
  name: string;
  stage?: string;
  sector?: string;
  geography?: string;
}

/** UI decision context; RECORD_DECISION is the only action that creates a canonical Decision. */
export interface DecisionContext {
  id: Id;
  label: string;
  dueAt?: string;
  status: DecisionStatus;
  requiredEntitlement: Entitlement;
  recordedDecisionId?: Id;
}

export interface SourceLocator {
  sourceId: Id;
  sourceVersionId?: Id;
  locator?: string;
  claimId?: Id;
}

/** UI projection of the canonical relation contract. */
export interface Relation {
  id: Id;
  caseId: Id;
  sourceObjectId: Id;
  sourceObjectType: KernelObjectKind;
  targetObjectId: Id;
  targetObjectType: KernelObjectKind;
  type: RelationType;
  semanticRole?: string;
  materiality?: string;
  effectiveAt?: string;
  knownAt?: string;
  producerType?: string;
  producerVersion?: string;
  rationale?: string;
  evidenceRefs?: Id[];
  institutionalState: InstitutionalState;
  contractVersion: string;
}

export interface Unknown {
  id: Id;
  unknownType?: string;
  title: string;
  targetObjectIds: Id[];
  materiality?: string;
  resolutionPath?: string;
  status: UnknownStatus;
  ownerActorId?: Id;
  dueAt?: string;
  workItemIds?: Id[];
  openedAtEventId?: Id;
  resolvedAtEventId?: Id;
}

/** kernel: CaseReading — system synthesis for one Question. Never attributed to an actor. */
export interface CaseReading {
  id: Id;
  questionId?: Id;
  text: string;
  supportingLine?: string;
  epistemicStatus: EpistemicStatus;
  freshnessStatus: FreshnessStatus;
  decisionLinkStatus: DecisionLinkStatus;
  computedAt?: string;
  computationVersion?: string;
  supportObjectIds: Id[];
  independentSupportObjectIds: Id[];
  supportRouteIds?: Id[];
  challengeRelationIds?: Id[];
  unknownIds: Id[];
  relatedObjectIds: Id[];
  lastChangeEventId?: Id;
}

/** UI/archetype grouping over the active QuestionSpine; not a new kernel ontology object. */
export interface Workstream {
  id: Id;
  name: string;
  currentCaseReadingId: Id;
  ownerActorId?: Id;
  latestChangeEventId?: Id;
  activeWorkItemIds: Id[];
  openUnknownIds: Id[];
  questionIds: Id[];
  outputArtifactIds?: Id[];
}

/** kernel: Question — the decision-relative epistemic unit. */
export interface Question {
  id: Id;
  workstreamId: Id; // UI/archetype projection placement
  name: string;
  questionStatus: QuestionStatus;
  currentCaseReadingId: Id;
  claimIds: Id[];
  workItemIds: Id[];
  openUnknownIds: Id[];
  chronologyEventIds: Id[];
  resolutionCriteria?: string[];
  evidenceNeeded?: string[];
  decisionRelevance?: string;
}

export interface Source {
  id: Id;
  type: string;
  title: string;
  origin?: string;
  permissionScope?: string;
  currentVersionId?: Id;
  originActorId?: Id;
  occurredAt?: string;
  locator?: string;
  excerpt?: string;
  limitation?: string;
}

export interface SourceVersion {
  id: Id;
  sourceId: Id;
  contentHash: string;
  capturedAt?: string;
  knownAt: string;
  permissionScope: string;
  availabilityStatus?: string;
}

/** kernel: Claim — one atomic proposition from one SourceVersion. */
export interface Claim {
  id: Id;
  sourceId?: Id; // convenience projection; canonical provenance is SourceVersion + locator
  sourceVersionId: Id;
  locator: string;
  knownAt?: string;
  type: string; // investor-facing evidence/source class
  label: string;
  claimKind?: 'QUALITATIVE' | 'QUANTITATIVE' | 'DEFINITION' | 'FORECAST' | 'ESTIMATE' | 'COMMITMENT' | 'CONDITION' | 'DECISION_OBSERVATION' | 'OTHER';
  normalizedStatement: string;
  semanticIdentity?: string;
  verbatimOrLosslessSpan?: string;
  contribution?: string;
  excerpt?: string;
  limitation?: string;
}

/** kernel: MetricDefinition — governed definition of a measurable concept. */
export interface MetricDefinition {
  id: Id;
  canonicalName: string;
  unitType?: string;
  basisDefinition?: string;
  allowedDimensions?: string[];
  definitionVersion?: string;
}

/** kernel: MetricObservation — source/model observation under a precise semantic identity. */
export interface MetricObservation {
  id: Id;
  metricDefinitionId: Id;
  entityId?: Id;
  period?: string;
  scope?: string;
  basis?: string;
  measurement?: string;
  scenario?: string;
  value?: number | string | null;
  unit?: string;
  currency?: string;
  sourceObjectIds: Id[];
  institutionalState: InstitutionalState;
  freshnessStatus?: FreshnessStatus;
  displayLabel?: string;
}

/** kernel: Assumption — a versioned boundary condition. */
export interface Assumption {
  id: Id;
  statementOrValue: string;
  scope?: string;
  scenario?: string;
  status: 'PROPOSED' | 'CURRENT' | 'CHALLENGED' | 'BROKEN' | 'SUPERSEDED' | 'RETIRED';
  epistemicStatus?: EpistemicStatus;
  freshnessStatus?: FreshnessStatus;
  sourceBasisIds: Id[];
}

/** kernel: Risk — an adverse mechanism, not an auto-accepted judgment. */
export interface Risk {
  id: Id;
  mechanism: string;
  affectedObjectIds: Id[];
  horizon?: string;
  severity?: string;
  epistemicStatus?: EpistemicStatus;
  evidenceBasisIds: Id[];
  ownerActorId?: Id;
}

/** kernel: ModelNode — executable or auditable model node. */
export interface ModelNode {
  id: Id;
  modelId: Id;
  label: string;
  semanticIdentity?: string;
  nodeRole?: string;
  unit?: string;
  currentValue?: number | string | null;
  valueOrFormulaRef?: string;
  freshnessStatus?: FreshnessStatus;
  executionStatus?: string;
  coverageLimitUnknownIds?: Id[];
}

/** kernel: Outcome — immutable observed real-world result. */
export interface Outcome {
  id: Id;
  outcomeType: string;
  observedValueOrState: string | number | boolean | null;
  effectiveAt: string;
  knownAt: string;
  affectedObjectIds: Id[];
  displayLabel?: string;
}

/** UI review projection over a machine proposal. Not a canonical kernel object type. */
export interface Finding {
  id: Id;
  title: string;
  proposition: string;
  scopeObjectId?: Id;
  foundAtEventId: Id;
  derivationObjectIds: Id[];
  affectedObjectIds: Id[];
  proposedObjectIds?: Id[];
  status: ReviewStatus;
}

/** kernel: HumanPosition — immutable attributed view. Never graded by epistemic status. */
export interface HumanPosition {
  id: Id;
  authorActorId: Id;
  recordedAt: string;
  text: string;
  scopeObjectId: Id;
  institutionalState: InstitutionalState;
  sourceLocator?: SourceLocator;
  lastChangeEventId?: Id;
}

/** kernel: WorkItem — bounded work tied to a target object. */
export interface WorkItem {
  id: Id;
  name: string;
  ownerActorId?: Id;
  status: WorkStatus;
  institutionalState?: InstitutionalState;
  kind: 'CURRENT_WORK' | 'EVIDENCE_ROUTE' | 'VERIFICATION_ROUTE' | 'PANTA_PROPOSAL';
  whatToObtain?: string;
  canChangeObjectIds: Id[];
  remainingUnknownIds: Id[];
  adoptedAtEventId?: Id;
  externalActionRequired?: boolean;
}

/** Metric identity / perimeter dimensions required before comparison or contradiction. */
export interface QuantityPerimeter {
  scope?: string;
  basis?: string;
  measurement?: string;
  period?: string;
  scenario?: string;
  geographyOrEnvironment?: string;
}

/** UI projection over MetricObservation / ModelNode. */
export interface Quantity {
  id: Id;
  label: string;
  value?: number | string | null;
  display?: string;
  metricDefinitionId?: Id;
  entityId?: Id;
  unit?: string;
  currency?: string;
  perimeter: QuantityPerimeter;
  sourceObjectIds: Id[];
  formula?: string;
  assumptionObjectIds: Id[];
  downstreamObjectIds: Id[];
  editable: boolean;
  institutionalState: InstitutionalState;
  freshnessStatus: FreshnessStatus;
  coverageLimitUnknownIds?: Id[];
  lastChangeEventId?: Id;
}

export interface ArtifactBlock {
  id: Id;
  artifactId: Id;
  title?: string;
  text?: string;
  authorship: ArtifactAuthorship;
  authorActorId?: Id;
  recordedAt?: string;
  boundObjectIds: Id[];
  suggestion?: {
    signal: string;
    suggestedText: string;
    reasonObjectIds: Id[];
  };
}

export interface Artifact {
  id: Id;
  type: 'IC_MEMO' | 'MODEL' | 'DECISION_PACK' | string;
  title: string;
  freshnessStatus: FreshnessStatus;
  institutionalState?: InstitutionalState;
  lastSyncedAt?: string;
  lastSyncedCaseVersion?: string;
  pendingCaseChangeCount: number;
  syncStatus: ArtifactSyncStatus;
  blockIds: Id[];
  quantityIds: Id[];
}

export interface ArtifactDiff {
  id: Id;
  artifactId: Id;
  blockId?: Id;
  quantityId?: Id;
  before?: string;
  after?: string;
  causeEventId: Id;
  changeType: 'CASE_BACKED_RERENDER' | 'HUMAN_EDIT_PROPOSED' | 'QUANTITY_UPDATE' | 'STRUCTURE_UPDATE';
}

export interface ReviewItem {
  id: Id;
  kind: 'NEW_EVIDENCE' | 'FINDING';
  title: string;
  sourceId?: Id;
  findingId?: Id;
  proposedCaseReading: CaseReading;
  effectPreview: ImpactChange[];
  status: ReviewStatus;
}

/** UI impact language; not kernel state. */
export type ImpactState = 'STRENGTHENS' | 'WEAKENS' | 'HOLDS' | 'NARROWS' | 'RISK_WORSENS' | 'BECOMES_STALE';

export interface ImpactChange {
  objectId: Id;
  objectLabel: string;
  state: ImpactState;
  before?: string;
  after?: string;
  reasonRelationIds: Id[];
}

/** Affected does not mean changed. Every touched object is counted exactly once. */
export interface Coverage {
  examinedCount: number;
  changedCount: number;
  heldCount: number;
  unmappedCount: number;
}

export interface SimulationOption {
  id: Id;
  originObjectId: Id;
  label: string;
  assumption: string;
  enabled: boolean;
}

export interface SimulationRequest {
  optionId: Id;
  originObjectId: Id;
  assumption: string;
}

export interface SimulationResult {
  id: Id;
  request: SimulationRequest;
  effects: ImpactChange[];
  coverage: Coverage;
}

/** Exact kernel event vocabulary from panta.universal_investment_kernel@0.1.0. */
export type CaseEventType =
  | 'CASE_CREATED'
  | 'SOURCE_REGISTERED'
  | 'SOURCE_VERSION_RECORDED'
  | 'CLAIM_RECORDED'
  | 'METRIC_OBSERVATION_RECORDED'
  | 'QUESTION_PROPOSED'
  | 'QUESTION_SPINE_CHANGED'
  | 'UNKNOWN_RECORDED'
  | 'HUMAN_POSITION_RECORDED'
  | 'CASE_READING_RECOMPUTED'
  | 'ASSUMPTION_PROPOSED'
  | 'ASSUMPTION_ADOPTED'
  | 'ASSUMPTION_CHALLENGED'
  | 'RISK_RECORDED'
  | 'MODEL_NODE_BOUND'
  | 'RELATION_ESTABLISHED'
  | 'CONDITION_RECORDED'
  | 'CONDITION_STATE_RECORDED'
  | 'DECISION_RECORDED'
  | 'WORK_ITEM_RECORDED'
  | 'WORK_ITEM_STATE_RECORDED'
  | 'ARTIFACT_VERSION_RECORDED'
  | 'OUTCOME_RECORDED'
  | 'PROPOSAL_REJECTED'
  | 'OBJECT_SUPERSEDED'
  | 'OBJECT_RETIRED';

/** Ledger event projection. effectiveAt / knownAt / recordedAt are distinct by contract. */
export interface CaseEvent {
  id: Id;
  caseId: Id;
  eventType: CaseEventType;
  objectType?: KernelObjectKind;
  objectId?: Id;
  effectiveAt?: string;
  knownAt: string;
  recordedAt: string;
  actorOrPolicyId: Id;
  schemaVersion: string;
  idempotencyKey: string;
  sourceEventId?: Id;
  causationId?: Id;
  correlationId?: Id;
  authorityBasisId?: Id;
  objectIds?: Id[];
}

/** Sparse replay navigation aid only; history is always loaded via loadCase(...,{asOf}). */
export interface CaseMoment {
  id: Id;
  asOf: string;
  label: string;
  eventId?: Id;
}

/** UI projection of kernel Condition. */
export interface Condition {
  id: Id;
  label: string;
  predicate?: string;
  targetObjectIds: Id[];
  ownerActorId?: Id;
  status: ConditionStatus;
  waiverAuthorityRuleId?: Id;
  evidenceIds?: Id[];
  dueAt?: string;
  freshnessStatus?: FreshnessStatus;
  unknownIds: Id[];
  relatedObjectIds: Id[];
}

/** UI branch choice; the canonical record is a Decision after RECORD_DECISION. */
export interface DecisionPath {
  id: Id;
  label: 'COMMIT' | 'COMMIT_WITH_CONDITIONS' | 'DEFER' | 'DECLINE' | string;
  meaning: string;
}

/** Projection of an immutable kernel Decision plus UI branch/rationale fields. */
export interface DecisionRecord {
  id: Id;
  decisionType?: string;
  decision?: string;
  pathId: Id;
  actorOrBodyId: Id;
  authorityBasisId?: Id;
  scope?: string;
  rationale: string;
  conditionIds?: Id[];
  effectiveAt?: string;
  recordedAt: string;
  basisObjectIds?: Id[];
  caseVersion: string;
}

export interface FormationMaterial {
  id: Id;
  sourceId: Id;
  understoodObjectIds: Id[];
  limitationUnknownIds: Id[];
  mappedWorkstreamIds: Id[];
  status: 'READ' | 'PARTIAL' | 'UNREADABLE';
}

/** UI formation review state; canonical adoption is event/relation-backed. */
export interface FormationDraft {
  premise?: string;
  materialIds: Id[];
  proposedWorkstreamIds: Id[];
  blindSpotUnknownIds: Id[];
  unplacedSourceIds: Id[];
  status: 'PROPOSED_NOT_LIVE' | 'ADOPTED';
}

export type LensAction = 'TRACE' | 'SIMULATE' | 'RESOLVE' | 'OPEN_SOURCE' | 'VIEW_IN_CASE';

/** Backend returns identities/refs/facts only. Investor-facing sentences are composed in the frontend. */
export interface InspectionPayload {
  objectId: Id;
  supportObjectIds: Id[];
  independentSupportObjectIds: Id[];
  unknownIds: Id[];
  dependentObjectIds: Id[];
  lastChangeEventId?: Id;
  relatedObjectIds: Id[];
  sourceLocators: SourceLocator[];
  allowedActions: LensAction[];
}

/** Materialized UI projection rebuilt from the append-only ledger. Never source truth. */
export interface PantaCaseSnapshot {
  caseRef: CaseRef;
  caseVersion: string;
  asOf: string;
  decision?: DecisionContext;
  premiseCaseReadingId?: Id;
  actors: Actor[];
  workstreams: Workstream[];
  questions: Question[];
  caseReadings: CaseReading[];
  unknowns: Unknown[];
  sources: Source[];
  sourceVersions: SourceVersion[];
  claims: Claim[];
  metricDefinitions: MetricDefinition[];
  metricObservations: MetricObservation[];
  assumptions: Assumption[];
  risks: Risk[];
  modelNodes: ModelNode[];
  outcomes: Outcome[];
  findings: Finding[];
  humanPositions: HumanPosition[];
  workItems: WorkItem[];
  quantities: Quantity[];
  artifacts: Artifact[];
  artifactBlocks: ArtifactBlock[];
  artifactDiffs: ArtifactDiff[];
  relations: Relation[];
  events: CaseEvent[];
  pendingReviews: ReviewItem[];
  simulationOptions: SimulationOption[];
  conditions: Condition[];
  decisionPaths: DecisionPath[];
  decisions: DecisionRecord[];
  formation?: FormationDraft;
}

export type PantaAction =
  | { type: 'ADD_MATERIAL'; files: File[] }
  | { type: 'REVIEW_ITEM'; reviewId: Id; disposition: 'ADMIT' | 'CORRECT' | 'REJECT'; correctedText?: string }
  | { type: 'ADOPT_WORK_ITEM'; workItemId: Id }
  | { type: 'UPDATE_WORK_ITEM_PROPOSAL'; workItemId: Id; whatToObtain: string }
  | { type: 'DISMISS_WORK_ITEM_PROPOSAL'; workItemId: Id }
  | { type: 'ASSIGN_WORK_ITEM'; workItemId: Id; ownerActorId: Id }
  | { type: 'ADOPT_FORMATION' }
  | { type: 'CORRECT_FORMATION'; patch: unknown }
  | { type: 'RECORD_DECISION'; pathId: Id; rationale: string; conditionText?: string }
  | { type: 'CREATE_ARTIFACT'; artifactType: string }
  | { type: 'SYNC_ARTIFACT'; artifactId: Id }
  | { type: 'SYNC_ALL_ARTIFACTS' }
  | { type: 'UPDATE_ARTIFACT_BLOCK'; artifactId: Id; blockId: Id; text: string }
  | { type: 'ACCEPT_ARTIFACT_SUGGESTION'; artifactId: Id; blockId: Id }
  | { type: 'DISMISS_ARTIFACT_SUGGESTION'; artifactId: Id; blockId: Id };

/** Every governed mutation carries an Actor. Backend authority policy is definitive. */
export interface PantaCommand {
  actorId: Id;
  submittedAt: string;
  action: PantaAction;
}
