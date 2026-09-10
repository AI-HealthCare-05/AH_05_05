import { useId, useRef, useState, type ReactNode } from 'react';
import { mealSlotLabel, type MealSlot } from '@/shared/model/mealSlot';
import { ContinuousTabs } from '@/shared/ui/ContinuousTabs';

/** Keeps each slot mounted so selections and in-flight saves stay with their records. */
export function TimeSlotNavigator<T extends { slot: MealSlot }>({ items, initialSlot, label, children }: {
  items: T[];
  initialSlot: MealSlot;
  label: string;
  children: (item: T) => ReactNode;
}) {
  const id = useId();
  const [selectedSlot, setSelectedSlot] = useState(initialSlot);
  const gesture = useRef<{ id: number; x: number; y: number } | null>(null);
  const swiped = useRef(false);
  const selectedIndex = Math.max(0, items.findIndex(item => item.slot === selectedSlot));
  const multiple = items.length > 1;

  function select(index: number) {
    const nextIndex = Math.max(0, Math.min(items.length - 1, index));
    setSelectedSlot(items[nextIndex].slot);
  }

  return (
    <div className="flex min-w-0 flex-col gap-3">
      {multiple && (
        <ContinuousTabs
          label={`${label} 시간대`}
          value={items[selectedIndex].slot}
          onChange={setSelectedSlot}
          items={items.map(item => ({ value: item.slot, label: mealSlotLabel(item.slot, 'short'), id: `${id}-tab-${item.slot}`, controls: `${id}-panel-${item.slot}` }))}
        />
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
