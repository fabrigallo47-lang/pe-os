import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
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
} from '../types/domain';
import type { InspectOptions, PantaBackendAdapter, SearchResult } from '../providers/PantaBackendAdapter';

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
  caseId?: Id;
  asOf?: string;
  focusedWorkstreamId?: Id;
  focusedQuestionId?: Id;
  activeObjectId?: Id;
  inspection?: InspectionPayload | null;
  searchResults: SearchResult[];
  simulationResult?: SimulationResult | null;
  selectedSourceId?: Id;
  sourcesOpen: boolean;
  setCase: (id: Id) => Promise<void>;
  setAsOf: (asOf?: string) => Promise<void>;
  returnToCurrent: () => Promise<void>;
  setFocusedWorkstream: (id?: Id) => void;
  setFocusedQuestion: (id?: Id) => void;
  setActiveObject: (id?: Id, options?: InspectOptions) => Promise<void>;
  refresh: () => Promise<void>;
  execute: (action: PantaAction) => Promise<void>;
  search: (query: string) => Promise<void>;
  runSimulation: (request: SimulationRequest) => Promise<SimulationResult | null>;
  clearSimulation: () => void;
  openSource: (sourceId?: Id) => void;
  closeSources: () => void;
}

const Ctx = createContext<PantaContextValue | null>(null);

export function PantaProvider({ adapter, initialCaseId, children }: { adapter: PantaBackendAdapter; initialCaseId?: Id; children: React.ReactNode }) {
  const [session, setSession] = useState<SessionContext>();
  const [snapshot, setSnapshot] = useState<PantaCaseSnapshot | null>(null);
  const [cases, setCases] = useState<CaseOption[]>([]);
  const [moments, setMoments] = useState<CaseMoment[]>([]);
  const [caseId, setCaseId] = useState<Id | undefined>(initialCaseId);
  const [asOf, setAsOfState] = useState<string>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [focusedWorkstreamId, setFocusedWorkstreamId] = useState<Id>();
  const [focusedQuestionId, setFocusedQuestionId] = useState<Id>();
  const [activeObjectId, setActiveObjectId] = useState<Id>();
  const [inspection, setInspection] = useState<InspectionPayload | null>(null);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [simulationResult, setSimulationResult] = useState<SimulationResult | null>(null);
  const [selectedSourceId, setSelectedSourceId] = useState<Id>();
  const [sourcesOpen, setSourcesOpen] = useState(false);

  useEffect(() => {
    void adapter.getSession().then(setSession).catch(() => setSession(undefined));
    void adapter.listCases().then(setCases).catch(() => setCases([]));
  }, [adapter]);

  const load = useCallback(async (nextCaseId = caseId, nextAsOf = asOf) => {
    setLoading(true);
    setError(undefined);
    try {
      const loaded = await adapter.loadCase(nextCaseId, nextAsOf ? { asOf: nextAsOf } : undefined);
      setSnapshot(loaded);
      if (loaded?.caseRef.id && !nextCaseId) setCaseId(loaded.caseRef.id);
      if (loaded) {
        setFocusedWorkstreamId(prev => prev && loaded.workstreams.some(w => w.id === prev) ? prev : loaded.workstreams[0]?.id);
        setFocusedQuestionId(prev => prev && loaded.questions.some(t => t.id === prev) ? prev : undefined);
        try { setMoments(await adapter.listCaseMoments(loaded.caseRef.id)); } catch { setMoments([]); }
      } else {
        setMoments([]);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to load case');
    } finally {
      setLoading(false);
    }
  }, [adapter, caseId, asOf]);

  const refresh = useCallback(async () => { await load(); }, [load]);
  useEffect(() => { void load(); }, [load]);

  const setCase = useCallback(async (id: Id) => {
    setCaseId(id);
    setAsOfState(undefined);
    setFocusedWorkstreamId(undefined);
    setFocusedQuestionId(undefined);
    setActiveObjectId(undefined);
    setInspection(null);
    setSimulationResult(null);
    await load(id, undefined);
  }, [load]);

  const setAsOf = useCallback(async (value?: string) => {
    setAsOfState(value);
    setActiveObjectId(undefined);
    setInspection(null);
    setSimulationResult(null);
    await load(caseId, value);
  }, [caseId, load]);

  const returnToCurrent = useCallback(async () => { await setAsOf(undefined); }, [setAsOf]);

  const setFocusedWorkstream = useCallback((id?: Id) => {
    setFocusedWorkstreamId(id);
    setFocusedQuestionId(undefined);
    setActiveObjectId(undefined);
    setInspection(null);
  }, []);

  const setFocusedQuestion = useCallback((id?: Id) => {
    setFocusedQuestionId(id);
    setActiveObjectId(undefined);
    setInspection(null);
  }, []);

  const setActiveObject = useCallback(async (id?: Id, options?: InspectOptions) => {
    setActiveObjectId(id);
    if (!id || !snapshot) { setInspection(null); return; }
    setInspection(await adapter.inspectObject(snapshot.caseRef.id, id, options));
  }, [adapter, snapshot]);

  const execute = useCallback(async (action: PantaAction) => {
    if (!snapshot || !session?.actor.actorId) return;
    const next = await adapter.execute(snapshot.caseRef.id, {
      actorId: session.actor.actorId,
      submittedAt: new Date().toISOString(),
      action,
    });
    if (next) {
      setSnapshot(next);
      try { setMoments(await adapter.listCaseMoments(next.caseRef.id)); } catch { /* keep prior */ }
    }
  }, [adapter, snapshot, session]);

  const search = useCallback(async (query: string) => {
    if (!snapshot || !query.trim()) { setSearchResults([]); return; }
    setSearchResults(await adapter.searchCase(snapshot.caseRef.id, query.trim()));
  }, [adapter, snapshot]);

  const runSimulation = useCallback(async (request: SimulationRequest) => {
    if (!snapshot) return null;
    const result = await adapter.runSimulation(snapshot.caseRef.id, request);
    setSimulationResult(result);
    return result;
  }, [adapter, snapshot]);

  const clearSimulation = useCallback(() => setSimulationResult(null), []);
  const openSource = useCallback((sourceId?: Id) => { setSelectedSourceId(sourceId); setSourcesOpen(true); }, []);
  const closeSources = useCallback(() => { setSourcesOpen(false); setSelectedSourceId(undefined); }, []);

  const value = useMemo(() => ({
    adapter, session, actor: session?.actor, snapshot, cases, moments, loading, error, caseId, asOf,
    focusedWorkstreamId, focusedQuestionId, activeObjectId, inspection, searchResults, simulationResult,
    selectedSourceId, sourcesOpen,
    setCase, setAsOf, returnToCurrent, setFocusedWorkstream, setFocusedQuestion, setActiveObject,
    refresh, execute, search, runSimulation, clearSimulation, openSource, closeSources,
  }), [adapter, session, snapshot, cases, moments, loading, error, caseId, asOf, focusedWorkstreamId, focusedQuestionId,
    activeObjectId, inspection, searchResults, simulationResult, selectedSourceId, sourcesOpen,
    setCase, setAsOf, returnToCurrent, setFocusedWorkstream, setFocusedQuestion, setActiveObject,
    refresh, execute, search, runSimulation, clearSimulation, openSource, closeSources]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function usePanta() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('usePanta must be used inside PantaProvider');
  return ctx;
}
