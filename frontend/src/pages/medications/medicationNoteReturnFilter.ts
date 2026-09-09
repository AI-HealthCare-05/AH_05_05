import { AUTH_SESSION_EXPIRED_EVENT } from '@/shared/api/client';

interface SavedNoteFilter {
  listKey: string;
  principalKey: string;
  episodeId: number;
}

let pendingFilter: SavedNoteFilter | null = null;

export function clearSavedNoteFilter() {
  pendingFilter = null;
  window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, clearSavedNoteFilter);
}

export function rememberSavedNoteFilter(filter: SavedNoteFilter) {
  clearSavedNoteFilter();
  pendingFilter = filter;
  window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, clearSavedNoteFilter, { once: true });
}

export function consumeSavedNoteFilter(listKey: string, principalKey: string | null): number | null {
  const filter = pendingFilter;
  clearSavedNoteFilter();
  return filter?.listKey === listKey && filter.principalKey === principalKey
    ? filter.episodeId
    : null;
}
