import type { ReactNode } from 'react';
import './pending-bubble.css';

/** Shared chat-style progress surface; decorative dots never repeat the announcement. */
export function PendingBubble({ children, role }: { children: ReactNode; role?: 'status' }) {
  return (
    <p role={role} className="chat-pending-bubble px-3.5 py-2.5 text-base text-muted-foreground">
      <span className="min-w-0 break-keep">{children}</span>
      <span aria-hidden="true" className="chat-pending-loader" data-chat-pending-loader>
        {Array.from({ length: 5 }, (_, index) => (
          <span key={index} className="chat-pending-dot" data-chat-pending-dot />
        ))}
      </span>
    </p>
  );
}
