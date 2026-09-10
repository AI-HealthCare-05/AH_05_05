import { useId, useRef, useState, type ReactNode } from 'react';
import { mealSlotLabel, type MealSlot } from '@/shared/model/mealSlot';

/** Keeps each slot mounted so selections and in-flight saves stay with their records. */
export function TimeSlotNavigator<T extends { slot: MealSlot }>({ items, initialSlot, label, children }: {
  items: T[];
  initialSlot: MealSlot;
  label: string;
  children: (item: T) => ReactNode;
}) {
  const id = useId();
  const [selectedSlot, setSelectedSlot] = useState(initialSlot);
  const tabs = useRef<Array<HTMLButtonElement | null>>([]);
  const gesture = useRef<{ id: number; x: number; y: number } | null>(null);
  const swiped = useRef(false);
  const selectedIndex = Math.max(0, items.findIndex(item => item.slot === selectedSlot));
  const multiple = items.length > 1;

  function select(index: number, focus = false) {
    const nextIndex = Math.max(0, Math.min(items.length - 1, index));
    setSelectedSlot(items[nextIndex].slot);
    if (focus) tabs.current[nextIndex]?.focus();
  }

  return (
    <div className="flex min-w-0 flex-col gap-3">
      {multiple && (
        <div role="tablist" aria-label={`${label} 시간대`} className="flex rounded-card bg-muted-bg p-1">
          {items.map((item, index) => (
            <button
              key={item.slot}
              ref={element => { tabs.current[index] = element; }}
              id={`${id}-tab-${item.slot}`}
              type="button"
              role="tab"
              aria-selected={index === selectedIndex}
              aria-controls={`${id}-panel-${item.slot}`}
              tabIndex={index === selectedIndex ? 0 : -1}
              className={`min-h-touch min-w-0 flex-1 rounded-button px-1 text-sm font-bold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                index === selectedIndex ? 'bg-card text-primary-strong shadow-card' : 'text-muted-foreground'
              }`}
              onClick={() => select(index)}
              onKeyDown={event => {
                const next = event.key === 'ArrowRight' ? index + 1
                  : event.key === 'ArrowLeft' ? index - 1
                    : event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : null;
                if (next === null) return;
                event.preventDefault();
                select(next, true);
              }}
            >
              {mealSlotLabel(item.slot, 'short')}
            </button>
          ))}
        </div>
      )}
      <div
        className="min-w-0 touch-pan-y"
        onPointerDown={event => {
          swiped.current = false;
          gesture.current = multiple && event.isPrimary
            ? { id: event.pointerId, x: event.clientX, y: event.clientY } : null;
        }}
        onPointerCancel={() => { gesture.current = null; }}
        onPointerUp={event => {
          const start = gesture.current;
          gesture.current = null;
          if (!start || start.id !== event.pointerId) return;
          const dx = event.clientX - start.x;
          const dy = event.clientY - start.y;
          if (Math.abs(dx) < 48 || Math.abs(dx) <= Math.abs(dy) * 1.5) return;
          swiped.current = true;
          select(selectedIndex + (dx < 0 ? 1 : -1));
        }}
        onClickCapture={event => {
          // A drag starting on a dose button must never become a dose action.
          if (!swiped.current || event.detail === 0) return;
          swiped.current = false;
          event.preventDefault();
          event.stopPropagation();
        }}
      >
        {items.map((item, index) => (
          <div
            key={item.slot}
            id={`${id}-panel-${item.slot}`}
            role={multiple ? 'tabpanel' : undefined}
            aria-labelledby={multiple ? `${id}-tab-${item.slot}` : undefined}
            tabIndex={multiple ? 0 : undefined}
            hidden={index !== selectedIndex}
            className="min-w-0 rounded-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {children(item)}
          </div>
        ))}
      </div>
    </div>
  );
}
