import type {
  CaseMoment,
  Id,
  InspectionPayload,
  ObjectKind,
  PantaCaseSnapshot,
  PantaCommand,
  SessionContext,
  SimulationRequest,
  SimulationResult,
} from '../types/domain';

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

export interface PantaBackendAdapter {
  getSession(): Promise<SessionContext>;
  listCases(): Promise<Array<{ id: Id; name: string }>>;
  loadCase(caseId?: Id, options?: LoadCaseOptions): Promise<PantaCaseSnapshot | null>;
  listCaseMoments(caseId: Id): Promise<CaseMoment[]>;
  inspectObject(caseId: Id, objectId: Id, options?: InspectOptions): Promise<InspectionPayload | null>;
  searchCase(caseId: Id, query: string): Promise<SearchResult[]>;
  runSimulation(caseId: Id, request: SimulationRequest): Promise<SimulationResult | null>;
  execute(caseId: Id, command: PantaCommand): Promise<PantaCaseSnapshot | null>;
}
