import { Check } from 'lucide-react';
import './dose-selection.css';

/** Visual companion to the owning row's aria-pressed button, never a second control. */
export function DoseSelectionIndicator({ selected, kind }: {
  selected: boolean;
  kind: 'medication' | 'supplement';
}) {
  return (
    <span data-dose-selection data-selected={selected} aria-hidden="true" className="rx-dose-selection">
      <span
        data-episode-selection-glyph={kind === 'medication' ? true : undefined}
        data-supplement-selection-indicator={kind === 'supplement' ? true : undefined}
        className={`rx-dose-selection-mark flex size-6 shrink-0 items-center justify-center rounded-pill border ${
          selected ? 'border-primary bg-primary text-card' : 'border-border bg-card text-transparent'
        }`}
      >
        {selected && <Check className="size-4" strokeWidth={3} />}
      </span>
    </span>
  );
}
