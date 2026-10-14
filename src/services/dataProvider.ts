import { APP_CONFIG } from './config.ts';
import { api } from './api.ts';
import { demoDataService } from './demoDataService.ts';

// Demo data is opt-in in production. An API failure must remain visible instead
// of silently showing synthetic patients as though they came from the backend.
export type DataSource = 'demo' | 'api';
let cachedSource: DataSource | null = null;

export function resolveDataSource(override?: DataSource): DataSource {
  if (override) { cachedSource = override; return override; }
  if (cachedSource) return cachedSource;
  cachedSource = APP_CONFIG.demoMode ? 'demo' : 'api';
  return cachedSource;
}

export function isDemoMode(override?: DataSource): boolean {
  return resolveDataSource(override) === 'demo';
}

export async function fetchPatients(override?: DataSource) {
  if (isDemoMode(override)) return demoDataService.listPatients();
  const res = await api.listPatients();
  return res.items as unknown as ReturnType<typeof demoDataService.listPatients>;
}

export const dataProvider = { fetchPatients, demo: demoDataService, api };
