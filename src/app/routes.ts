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
  return routeOrder.some(r => r.key === key) ? key : 'deal';
}

export function goTo(route: PantaRoute) {
  window.location.hash = `/${route}`;
}
