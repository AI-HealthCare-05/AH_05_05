const TUTORIAL_SEEN_KEY = 'poke:tutorial-seen';

export function completeTutorial(): void {
  try {
    window.localStorage.setItem(TUTORIAL_SEEN_KEY, 'true');
  } catch {
    // Restricted browsers can still remember completion for the current tab.
  }
  try {
    window.sessionStorage.setItem(TUTORIAL_SEEN_KEY, 'true');
  } catch {
    // Storage restrictions must not prevent leaving the tutorial.
  }
}

export function hasCompletedTutorial(): boolean {
  try {
    if (window.localStorage.getItem(TUTORIAL_SEEN_KEY) === 'true') return true;
  } catch {
    // Fall back to the existing session marker when durable storage is blocked.
  }
  try {
    if (window.sessionStorage.getItem(TUTORIAL_SEEN_KEY) === 'true') {
      completeTutorial(); // Preserve completion from the previous session-only version.
      return true;
    }
  } catch {
    // A first-time visitor can still use the tutorial without browser storage.
  }
  return false;
}
