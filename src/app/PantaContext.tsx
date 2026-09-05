import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import type {
  ActorContext,
  CaseMoment,
  Id,
  InspectionPayload,
  PantaAction,
  PantaCaseSnapshot,
  SessionContext,
  SimulationRequest,
  SimulationResult,
  SourceLocator,
} from '../types/domain';
import type { InspectOptions, PantaBackendAdapter, SearchResult } from '../providers/PantaBackendAdapter';
import { PANTA_NAVIGATION_EVENT, parseRouteLocation, updateRouteContext } from './routes';

interface CaseOption { id: Id; name: string }

interface PantaContextValue {
  adapter: PantaBackendAdapter;
  session?: SessionContext;
  actor?: ActorContext;
  snapshot: PantaCaseSnapshot | null;
  cases: CaseOption[];
  moments: CaseMoment[];
  loading: boolean;
  error?: string;
  pendingAction?: PantaAction['type'];
  simulationRunning: boolean;
  searching: boolean;
  inspecting: boolean;
  operationError?: string;
  caseId?: Id;
  asOf?: string;
  focusedWorkstreamId?: Id;
  focusedQuestionId?: Id;
  activeObjectId?: Id;
  inspection?: InspectionPayload | null;
  searchResults: SearchResult[];
  simulationResult?: SimulationResult | null;
  selectedSourceId?: Id;
  selectedSourceLocator?: SourceLocator;
  sourcesOpen: boolean;
  setCase: (id: Id) => Promise<void>;
  setAsOf: (asOf?: string) => Promise<void>;
  returnToCurrent: () => Promise<void>;
  setFocusedWorkstream: (id?: Id) => void;
  setFocusedQuestion: (id?: Id) => void;
  setActiveObject: (id?: Id, options?: InspectOptions) => Promise<void>;
  refresh: () => Promise<void>;
  execute: (action: PantaAction) => Promise<boolean>;
  search: (query: string) => Promise<void>;
  runSimulation: (request: SimulationRequest) => Promise<SimulationResult | null>;
  clearSimulation: () => void;
  clearOperationError: () => void;
  openSource: (source?: Id | SourceLocator) => void;
  closeSources: () => void;
}

const Ctx = createContext<PantaContextValue | null>(null);
const projectionKey = (caseId?: Id, asOf?: string) => `${caseId ?? ''}|${asOf ?? ''}`;

export function PantaProvider({ adapter, initialCaseId, children }: { adapter: PantaBackendAdapter; initialCaseId?: Id; children: React.ReactNode }) {
  const initialContext = useMemo(() => parseRouteLocation(window.location.hash).context, []);
  const [session, setSession] = useState<SessionContext>();
  const [snapshot, setSnapshot] = useState<PantaCaseSnapshot | null>(null);
  const [cases, setCases] = useState<CaseOption[]>([]);
  const [moments, setMoments] = useState<CaseMoment[]>([]);
  const [caseId, setCaseId] = useState<Id | undefined>(initialContext.caseId ?? initialCaseId);
  const [asOf, setAsOfState] = useState<string | undefined>(initialContext.asOf);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [pendingAction, setPendingAction] = useState<PantaAction['type']>();
  const [simulationRunning, setSimulationRunning] = useState(false);
  const [searching, setSearching] = useState(false);
  const [inspecting, setInspecting] = useState(false);
  const [operationError, setOperationError] = useState<string>();
  const [focusedWorkstreamId, setFocusedWorkstreamId] = useState<Id | undefined>(initialContext.workstreamId);
  const [focusedQuestionId, setFocusedQuestionId] = useState<Id | undefined>(initialContext.questionId);
  const [activeObjectId, setActiveObjectId] = useState<Id>();
  const [inspection, setInspection] = useState<InspectionPayload | null>(null);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [simulationResult, setSimulationResult] = useState<SimulationResult | null>(null);
  const [selectedSourceId, setSelectedSourceId] = useState<Id>();
  const [selectedSourceLocator, setSelectedSourceLocator] = useState<SourceLocator>();
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const loadRequestId = useRef(0);
  const scheduledLoadKey = useRef<string>();
  const searchRequestId = useRef(0);
  const inspectionRequestId = useRef(0);
  const inspectionInFlight = useRef<string>();
  const simulationRequestId = useRef(0);
  const commandRequestId = useRef(0);
  const commandInFlight = useRef(false);
  const simulationInFlight = useRef(false);
  const navigationContext = useRef({ ...initialContext, caseId: initialContext.caseId ?? initialCaseId });

  useEffect(() => {
    void adapter.getSession().then(setSession).catch(() => setSession(undefined));
    void adapter.listCases().then(setCases).catch(() => setCases([]));
  }, [adapter]);

  useEffect(() => {
    const syncContext = () => {
      const next = parseRouteLocation(window.location.hash).context;
      const previous = navigationContext.current;
      const nextCaseId = next.caseId ?? initialCaseId;
      const projectionChanged = previous.caseId !== nextCaseId || previous.asOf !== next.asOf;
      navigationContext.current = { ...next, caseId: nextCaseId };
      setCaseId(nextCaseId);
      setAsOfState(next.asOf);
      setFocusedWorkstreamId(next.workstreamId);
      setFocusedQuestionId(next.questionId);
      if (projectionChanged) {
        ++loadRequestId.current;
        ++searchRequestId.current;
        ++inspectionRequestId.current;
        ++simulationRequestId.current;
        ++commandRequestId.current;
        commandInFlight.current = false;
        setSnapshot(null);
        setMoments([]);
        setLoading(true);
        setPendingAction(undefined);
        setSearching(false);
        setSearchResults([]);
        setActiveObjectId(undefined);
        inspectionInFlight.current = undefined;
        setInspection(null);
        setInspecting(false);
        setSimulationResult(null);
        setSimulationRunning(false);
        setSourcesOpen(false);
        setSelectedSourceId(undefined);
        setSelectedSourceLocator(undefined);
      }
    };
    window.addEventListener('hashchange', syncContext);
    window.addEventListener('popstate', syncContext);
    window.addEventListener(PANTA_NAVIGATION_EVENT, syncContext);
    return () => {
      window.removeEventListener('hashchange', syncContext);
      window.removeEventListener('popstate', syncContext);
      window.removeEventListener(PANTA_NAVIGATION_EVENT, syncContext);
    };
  }, [initialCaseId]);

  const load = useCallback(async (nextCaseId?: Id, nextAsOf?: string) => {
    const requestId = ++loadRequestId.current;
    setLoading(true);
    setError(undefined);
    setOperationError(undefined);
    setSnapshot(null);
    setMoments([]);
    try {
      const loaded = await adapter.loadCase(nextCaseId, nextAsOf ? { asOf: nextAsOf } : undefined);
      if (requestId !== loadRequestId.current) return;
      setSnapshot(loaded);
      if (!loaded) return;

      const routeContext = parseRouteLocation(window.location.hash).context;
      const workstreamId = routeContext.workstreamId && loaded.workstreams.some(item => item.id === routeContext.workstreamId)
        ? routeContext.workstreamId
        : loaded.workstreams[0]?.id;
      const questionId = routeContext.questionId && loaded.questions.some(item => item.id === routeContext.questionId)
        ? routeContext.questionId
        : loaded.questions.find(item => item.workstreamId === workstreamId)?.id;
      const normalizedContext = { caseId: loaded.caseRef.id, workstreamId, questionId, asOf: nextAsOf };
      navigationContext.current = normalizedContext;
      setCaseId(loaded.caseRef.id);
      setFocusedWorkstreamId(workstreamId);
      setFocusedQuestionId(questionId);
      scheduledLoadKey.current = projectionKey(loaded.caseRef.id, nextAsOf);
      updateRouteContext(normalizedContext, { replace: true });

      try {
        const loadedMoments = await adapter.listCaseMoments(loaded.caseRef.id);
        if (requestId === loadRequestId.current) setMoments(loadedMoments);
      } catch {
        if (requestId === loadRequestId.current) setMoments([]);
      }
    } catch (caught) {
      if (requestId === loadRequestId.current) {
        setSnapshot(null);
        setMoments([]);
        setError(caught instanceof Error ? caught.message : 'Unable to load case');
      }
    } finally {
      if (requestId === loadRequestId.current) setLoading(false);
    }
  }, [adapter]);

  useEffect(() => {
    const key = projectionKey(caseId, asOf);
    if (scheduledLoadKey.current === key) return;
    scheduledLoadKey.current = key;
    void load(caseId, asOf);
  }, [caseId, asOf, load]);

  const refresh = useCallback(async () => { await load(caseId, asOf); }, [asOf, caseId, load]);

  const setCase = useCallback(async (id: Id) => {
    updateRouteContext({ caseId: id, asOf: undefined, workstreamId: undefined, questionId: undefined });
  }, []);

  const setAsOf = useCallback(async (value?: string) => {
    updateRouteContext({ asOf: value });
  }, []);

  const returnToCurrent = useCallback(async () => { await setAsOf(undefined); }, [setAsOf]);

  const setFocusedWorkstream = useCallback((id?: Id) => {
    updateRouteContext({ workstreamId: id, questionId: undefined });
    setActiveObjectId(undefined);
    setInspection(null);
  }, []);

  const setFocusedQuestion = useCallback((id?: Id) => {
    updateRouteContext({ questionId: id });
    setActiveObjectId(undefined);
    setInspection(null);
  }, []);

  const setActiveObject = useCallback(async (id?: Id, options?: InspectOptions) => {
    const requestSignature = id ? `${id}|${JSON.stringify(options ?? {})}` : undefined;
    if (requestSignature && inspectionInFlight.current === requestSignature) return;
    const requestId = ++inspectionRequestId.current;
    setActiveObjectId(id);
    setOperationError(undefined);
    if (!id || !snapshot) {
      inspectionInFlight.current = undefined;
      setInspection(null);
      setInspecting(false);
      return;
    }
    setInspection(null);
    setInspecting(true);
    inspectionInFlight.current = requestSignature;
    try {
      const nextInspection = await adapter.inspectObject(snapshot.caseRef.id, id, options);
      if (requestId === inspectionRequestId.current) setInspection(nextInspection);
    } catch (caught) {
      if (requestId === inspectionRequestId.current) {
        setInspection(null);
        setOperationError(caught instanceof Error ? caught.message : 'Unable to inspect this case object');
      }
    } finally {
      if (requestId === inspectionRequestId.current) {
        inspectionInFlight.current = undefined;
        setInspecting(false);
      }
    }
  }, [adapter, snapshot]);

  const execute = useCallback(async (action: PantaAction) => {
    if (!snapshot || !session?.actor.actorId || commandInFlight.current) return false;
    const requestId = ++commandRequestId.current;
    const targetCaseId = snapshot.caseRef.id;
    commandInFlight.current = true;
    setPendingAction(action.type);
    setOperationError(undefined);
    try {
      const next = await adapter.execute(targetCaseId, {
        actorId: session.actor.actorId,
        submittedAt: new Date().toISOString(),
        action,
      });
      if (requestId !== commandRequestId.current || navigationContext.current.caseId !== targetCaseId) return false;
      if (next) {
        setSnapshot(next);
        try {
          const nextMoments = await adapter.listCaseMoments(next.caseRef.id);
          if (requestId === commandRequestId.current && navigationContext.current.caseId === targetCaseId) setMoments(nextMoments);
        } catch { /* keep prior moments */ }
        return true;
      }
      return false;
    } catch (caught) {
      if (requestId === commandRequestId.current) setOperationError(caught instanceof Error ? caught.message : 'Unable to update the case');
      return false;
    } finally {
      if (requestId === commandRequestId.current) {
        commandInFlight.current = false;
        setPendingAction(undefined);
      }
    }
  }, [adapter, snapshot, session]);

  const search = useCallback(async (query: string) => {
    const requestId = ++searchRequestId.current;
    if (!snapshot || !query.trim()) {
      setSearchResults([]);
      setSearching(false);
      return;
    }
    setSearching(true);
    setSearchResults([]);
    setOperationError(undefined);
    try {
      const results = await adapter.searchCase(snapshot.caseRef.id, query.trim());
      if (requestId === searchRequestId.current) setSearchResults(results);
    } catch (caught) {
      if (requestId === searchRequestId.current) {
        setSearchResults([]);
        setOperationError(caught instanceof Error ? caught.message : 'Unable to search this case');
      }
    } finally {
      if (requestId === searchRequestId.current) setSearching(false);
    }
  }, [adapter, snapshot]);

  const runSimulation = useCallback(async (request: SimulationRequest) => {
    if (!snapshot || simulationInFlight.current) return null;
    const requestId = ++simulationRequestId.current;
    simulationInFlight.current = true;
    setSimulationRunning(true);
    setOperationError(undefined);
    try {
      const result = await adapter.runSimulation(snapshot.caseRef.id, request);
      if (requestId !== simulationRequestId.current) return null;
      setSimulationResult(result);
      return result;
    } catch (caught) {
      if (requestId === simulationRequestId.current) {
        setSimulationResult(null);
        setOperationError(caught instanceof Error ? caught.message : 'Unable to run the impact trace');
      }
      return null;
    } finally {
      simulationInFlight.current = false;
      if (requestId === simulationRequestId.current) setSimulationRunning(false);
    }
  }, [adapter, snapshot]);

  const clearSimulation = useCallback(() => {
    ++simulationRequestId.current;
    setSimulationResult(null);
    setSimulationRunning(false);
  }, []);
  const clearOperationError = useCallback(() => setOperationError(undefined), []);
  const openSource = useCallback((source?: Id | SourceLocator) => {
    setSelectedSourceId(typeof source === 'string' ? source : source?.sourceId);
    setSelectedSourceLocator(typeof source === 'object' ? { ...source } : undefined);
    setSourcesOpen(true);
  }, []);
  const closeSources = useCallback(() => { setSourcesOpen(false); setSelectedSourceId(undefined); setSelectedSourceLocator(undefined); }, []);

  const value = useMemo(() => ({
    adapter, session, actor: session?.actor, snapshot, cases, moments, loading, error, pendingAction,
    simulationRunning, searching, inspecting, operationError, caseId, asOf,
    focusedWorkstreamId, focusedQuestionId, activeObjectId, inspection, searchResults, simulationResult,
    selectedSourceId, selectedSourceLocator, sourcesOpen,
    setCase, setAsOf, returnToCurrent, setFocusedWorkstream, setFocusedQuestion, setActiveObject,
    refresh, execute, search, runSimulation, clearSimulation, clearOperationError, openSource, closeSources,
  }), [adapter, session, snapshot, cases, moments, loading, error, pendingAction, simulationRunning, searching,
    inspecting, operationError, caseId, asOf, focusedWorkstreamId, focusedQuestionId, activeObjectId,
    inspection, searchResults, simulationResult, selectedSourceId, selectedSourceLocator, sourcesOpen, setCase, setAsOf,
    returnToCurrent, setFocusedWorkstream, setFocusedQuestion, setActiveObject, refresh, execute, search,
    runSimulation, clearSimulation, clearOperationError, openSource, closeSources]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function usePanta() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('usePanta must be used inside PantaProvider');
  return ctx;
}
