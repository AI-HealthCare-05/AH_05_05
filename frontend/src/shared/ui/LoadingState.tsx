import { useEffect, useState } from 'react';

/** Fast requests resolve before the status appears, avoiding a flash on entry. */
export function LoadingState({ label, children }: { label: string; children: string }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setVisible(true), 250);
    return () => window.clearTimeout(timer);
  }, []);

  if (!visible) return null;

  return (
    <p
      role="status"
      aria-label={label}
      className="flex min-h-12 items-center text-sm text-muted-foreground motion-safe:animate-[rx-overlay-in_200ms_ease-out]"
    >
      {children}
    </p>
  );
}
