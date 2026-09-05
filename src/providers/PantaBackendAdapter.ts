import type {
  CaseJournal,
  CaseMoment,
  Id,
  InspectionPayload,
  JournalStateRef,
  ObjectKind,
  PantaCaseSnapshot,
  PantaCommand,
  SessionContext,
  SourceLocator,
  SimulationRequest,
  SimulationResult,
  SimulationProposal,
  SimulationProposalRequest,
} from '../types/domain';
import type { SourceDocument } from './sourceDocuments';

export interface SearchResult {
  objectId: Id;
  label: string;
  kind: ObjectKind;
  contextObjectId?: Id;
}

export interface LoadCaseOptions {
  asOf?: string;
}

export interface InspectOptions {
  excludeObjectIds?: Id[];
}

export interface JournalQuery {
  since?: string;
  until?: string;
  asOf?: string;
  workstream?: Id;
  kind?: string;
  baselineStateId?: Id;
  currentStateId?: Id;
  closeStateId?: Id;
}

export interface PantaBackendAdapter {
  proposeSimulation?(caseId: Id, request: SimulationProposalRequest): Promise<SimulationProposal>;
  exportArtifact?(caseId: Id, artifactId: Id, revision: string, format: 'html' | 'json' | 'csv'): Promise<{ filename: string; blob: Blob }>;
  /** Read the original bytes at the cited version; the app supplies a same-origin HTTP default. */
  loadSourceDocument?(caseId: Id, target: SourceLocator): Promise<SourceDocument>;
  getSession(): Promise<SessionContext>;
  listCases(): Promise<Array<{ id: Id; name: string }>>;
  loadCase(caseId?: Id, options?: LoadCaseOptions): Promise<PantaCaseSnapshot | null>;
  listCaseMoments(caseId: Id): Promise<CaseMoment[]>;
  /** Read GET /api/v20/cases/{caseId}/journal through the validated Journal projection. */
  loadJournal(caseId: Id, query?: JournalQuery): Promise<CaseJournal | null>;
  /** List immutable CURRENT states available to the Journal comparison controls. */
  listJournalStates(caseId: Id): Promise<JournalStateRef[]>;
  inspectObject(caseId: Id, objectId: Id, options?: InspectOptions): Promise<InspectionPayload | null>;
  searchCase(caseId: Id, query: string): Promise<SearchResult[]>;
  runSimulation(caseId: Id, request: SimulationRequest): Promise<SimulationResult | null>;
  execute(caseId: Id, command: PantaCommand): Promise<PantaCaseSnapshot | null>;
}
