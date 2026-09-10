import type { ComponentProps, CSSProperties } from 'react';
import { cn } from '@/shared/lib/cn';
import './drawn-arrows.css';

type Direction = 'up' | 'right' | 'down' | 'left';
type DrawnArrowProps = Omit<ComponentProps<'svg'>, 'children'> & { direction?: Direction };
type DrawnChevronProps = DrawnArrowProps & { expanded?: boolean };

const chevrons: Record<Direction, string> = {
  up: 'm18 15-6-6-6 6',
  right: 'm9 18 6-6-6-6',
  down: 'm6 9 6 6 6-6',
  left: 'm15 18-6-6 6-6',
};
const arrows: Record<Direction, [string, string]> = {
  up: ['m5 12 7-7 7 7', 'M12 19V5'],
  right: ['m12 5 7 7-7 7', 'M5 12h14'],
  down: ['m5 12 7 7 7-7', 'M12 5v14'],
  left: ['m12 19-7-7 7-7', 'M19 12H5'],
};

/** Decorative Lucide-shaped stroke, drawn once when its DOM node mounts. */
export function DrawnArrow({ direction = 'left', className, ...props }: DrawnArrowProps) {
  return <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"
    fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
    {...props} aria-hidden="true" focusable="false" className={cn('rx-drawn-icon', className)}>
    {arrows[direction].map((path, index) => <path key={index} d={path} pathLength="1" />)}
  </svg>;
}

/** `expanded` turns a down-chevron upwards without restarting its drawing. */
export function DrawnChevron({ direction = 'down', expanded = false, className, style, ...props }: DrawnChevronProps) {
  return <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"
    fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
    {...props} aria-hidden="true" focusable="false" className={cn('rx-drawn-icon rx-drawn-chevron', className)}
    style={{ '--drawn-chevron-turn': expanded ? '180deg' : '0deg', ...style } as CSSProperties}>
    <g><path d={chevrons[direction]} pathLength="1" /></g>
  </svg>;
}
