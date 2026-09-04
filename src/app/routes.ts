import type { Id } from '../types/domain';

export type PantaRoute =
  | 'deal'
  | 'workstream'
  | 'trace'
  | 'simulate'
  | 'review'
  | 'resolve'
  | 'formation'
  | 'replay'
  | 'outputs';

export interface PantaRouteContext {
  caseId?: Id;
  workstreamId?: Id;
  questionId?: Id;
  asOf?: string;
}

export const PANTA_NAVIGATION_EVENT = 'panta:navigation';

export const routeOrder: Array<{ key: PantaRoute; label: string; path: string }> = [
  { key: 'deal', label: 'Deal Home', path: '#/deal' },
  { key: 'workstream', label: 'Workstream Focus', path: '#/workstream' },
  { key: 'trace', label: 'Trace', path: '#/trace' },
  { key: 'simulate', label: 'Simulate', path: '#/simulate' },
  { key: 'review', label: 'Review & Admit', path: '#/review' },
  { key: 'resolve', label: 'Resolve', path: '#/resolve' },
  { key: 'formation', label: 'Formation', path: '#/formation' },
  { key: 'replay', label: 'Replay & Decision', path: '#/replay' },
  { key: 'outputs', label: 'Outputs', path: '#/outputs' },
];

export function parseRoute(hash: string): PantaRoute {
  const key = hash.replace(/^#\/?/, '').split('?')[0] as PantaRoute;
  return routeOrder.some(route => route.key === key) ? key : 'deal';
}

export function parseRouteLocation(hash: string): { route: PantaRoute; context: PantaRouteContext } {
  const query = hash.includes('?') ? hash.slice(hash.indexOf('?') + 1) : '';
  const params = new URLSearchParams(query);
  return {
    route: parseRoute(hash),
    context: {
      caseId: params.get('caseId') || undefined,
      workstreamId: params.get('workstreamId') || undefined,
      questionId: params.get('questionId') || undefined,
      asOf: params.get('asOf') || undefined,
    },
  };
}

export function buildRouteHash(route: PantaRoute, context: PantaRouteContext = {}): string {
  const params = new URLSearchParams();
  if (context.caseId) params.set('caseId', context.caseId);
  if (context.workstreamId) params.set('workstreamId', context.workstreamId);
  if (context.questionId) params.set('questionId', context.questionId);
  if (context.asOf) params.set('asOf', context.asOf);
  const query = params.toString();
  return `#/${route}${query ? `?${query}` : ''}`;
}

function mergedContext(patch: Partial<PantaRouteContext>): PantaRouteContext {
  const context = { ...parseRouteLocation(window.location.hash).context };
  for (const key of Object.keys(patch) as Array<keyof PantaRouteContext>) {
    const value = patch[key];
    if (value) context[key] = value;
    else delete context[key];
  }
  return context;
}

function commitNavigation(route: PantaRoute, context: PantaRouteContext, replace: boolean) {
  const hash = buildRouteHash(route, context);
  if (hash === window.location.hash) return;
  window.history[replace ? 'replaceState' : 'pushState'](null, '', hash);
  window.dispatchEvent(new Event(PANTA_NAVIGATION_EVENT));
}

export function goTo(route: PantaRoute, patch: Partial<PantaRouteContext> = {}) {
  commitNavigation(route, mergedContext(patch), false);
}

export function replaceRoute(route: PantaRoute, patch: Partial<PantaRouteContext> = {}) {
  commitNavigation(route, mergedContext(patch), true);
}

export function updateRouteContext(patch: Partial<PantaRouteContext>, options: { replace?: boolean } = {}) {
  const route = parseRoute(window.location.hash);
  commitNavigation(route, mergedContext(patch), options.replace ?? false);
}
