import { useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import './smooth-height.css';

/** Animate measured content changes, not every render or the child's controls. */
export function SmoothHeight({ children }: { children: ReactNode }) {
  const content = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState<number>();
  useLayoutEffect(() => {
    const element = content.current;
    if (!element) return;
    const measure = () => setHeight(Math.ceil(element.getBoundingClientRect().height));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return <div className="rx-smooth-height min-w-0 shrink-0" style={{ height }}>
    <div ref={content} className="flow-root min-w-0">{children}</div>
  </div>;
}
