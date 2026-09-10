import { useId, useLayoutEffect, useRef } from 'react';
import { cn } from '@/shared/lib/cn';
import './continuous-tabs.css';

// Adapted from Watermelon Continuous Tabs (source: ui.watermelon.sh).
// Keeps its shared sliding pill and spring { stiffness: 380, damping: 30,
// mass: 0.9 }, using native animations instead of a motion dependency.
interface ContinuousTabItem<T extends string> {
  value: T;
  label: string;
  id?: string;
  controls?: string;
}

interface ContinuousTabsProps<T extends string> {
  items: ContinuousTabItem<T>[];
  value: T;
  onChange: (value: T) => void;
  label: string;
  role?: 'tablist' | 'group';
  className?: string;
}

interface SpringAxis { from: number; to: number; velocity: number }
const DURATION = 600;
const DECAY = 30 / (2 * 0.9);
const FREQUENCY = Math.sqrt(380 / 0.9 - DECAY * DECAY);

function spring(axis: SpringAxis, seconds: number) {
  const displacement = axis.from - axis.to;
  const coefficient = (axis.velocity + DECAY * displacement) / FREQUENCY;
  const cosine = Math.cos(FREQUENCY * seconds);
  const sine = Math.sin(FREQUENCY * seconds);
  const envelope = Math.exp(-DECAY * seconds);
  const offset = displacement * cosine + coefficient * sine;
  return {
    position: axis.to + envelope * offset,
    velocity: envelope * (-DECAY * offset - displacement * FREQUENCY * sine + coefficient * FREQUENCY * cosine),
  };
}

/** A controlled, per-instance pill. It never remounts or moves the controls. */
export function ContinuousTabs<T extends string>({ items, value, onChange, label, role = 'tablist', className }: ContinuousTabsProps<T>) {
  const instanceId = useId();
  const trackRef = useRef<HTMLDivElement>(null);
  const pillRef = useRef<HTMLSpanElement>(null);
  const inkRef = useRef<HTMLSpanElement>(null);
  const buttons = useRef(new Map<string, HTMLButtonElement>());
  const selected = useRef(value);
  const move = useRef<(animate: boolean) => void>(() => {});
  selected.current = value;
  const itemKey = items.map(item => `${item.value}:${item.label}`).join('|');

  useLayoutEffect(() => {
    const track = trackRef.current;
    const pill = pillRef.current;
    const ink = inkRef.current;
    if (!track || !pill || !ink) return;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    let positioned = false;
    let motion: { pill: Animation; ink: Animation; x: SpringAxis; width: SpringAxis } | null = null;

    const cancel = () => { motion?.pill.cancel(); motion?.ink.cancel(); motion = null; };
    const place = (animate: boolean) => {
      const button = buttons.current.get(selected.current);
      if (!button) return;
      const trackBox = track.getBoundingClientRect();
      const target = button.getBoundingClientRect();
      if (!target.width || !target.height) return;
      const x = target.left - trackBox.left - track.clientLeft;
      const top = target.top - trackBox.top - track.clientTop;
      const current = pill.getBoundingClientRect();
      const fromX = current.left - trackBox.left - track.clientLeft;
      const elapsed = Number(motion?.pill.currentTime ?? DURATION) / 1000;
      const moving = motion?.pill.playState !== 'finished' ? motion : null;
      const xVelocity = moving ? spring(moving.x, elapsed).velocity : 0;
      const widthVelocity = moving ? spring(moving.width, elapsed).velocity : 0;
      cancel();

      // Keep the white label layer fixed over the actual buttons as its clip
      // moves. Both light-track and dark-pill text stay readable mid-transition.
      Array.from(ink.children).forEach((node, index) => {
        const peer = track.querySelectorAll<HTMLButtonElement>('.rx-continuous-trigger')[index];
        if (!peer) return;
        const box = peer.getBoundingClientRect();
        const span = node as HTMLElement;
        span.style.left = `${box.left - trackBox.left - track.clientLeft}px`;
        span.style.width = `${box.width}px`;
      });
      pill.style.top = `${top}px`;
      pill.style.height = `${target.height}px`;
      pill.style.width = `${target.width}px`;
      pill.style.transform = `translateX(${x}px)`;
      pill.style.visibility = 'visible';
      ink.style.width = `${track.clientWidth}px`;
      ink.style.transform = `translateX(${-x}px)`;

      if (positioned && animate && !reduced.matches && (Math.abs(fromX - x) > 0.1 || Math.abs(current.width - target.width) > 0.1)) {
        const xAxis = { from: fromX, to: x, velocity: xVelocity };
        const widthAxis = { from: current.width, to: target.width, velocity: widthVelocity };
        const frames = Array.from({ length: 37 }, (_, index) => {
          const seconds = index * DURATION / 36 / 1000;
          return {
            x: index === 36 ? x : spring(xAxis, seconds).position,
            width: index === 36 ? target.width : spring(widthAxis, seconds).position,
          };
        });
        const options: KeyframeAnimationOptions = { duration: DURATION, easing: 'linear', fill: 'both' };
        const pillAnimation = pill.animate(frames.map(frame => ({ transform: `translateX(${frame.x}px)`, width: `${frame.width}px` })), options);
        const inkAnimation = ink.animate(frames.map(frame => ({ transform: `translateX(${-frame.x}px)` })), options);
        pillAnimation.startTime = inkAnimation.startTime = document.timeline.currentTime;
        motion = { pill: pillAnimation, ink: inkAnimation, x: xAxis, width: widthAxis };
      }
      positioned = true;
    };
    move.current = place;
    place(false);
    const resize = new ResizeObserver(() => place(false));
    resize.observe(track);
    buttons.current.forEach(button => resize.observe(button));
    const motionPreferenceChanged = () => place(false);
    reduced.addEventListener('change', motionPreferenceChanged);
    return () => {
      cancel();
      resize.disconnect();
      reduced.removeEventListener('change', motionPreferenceChanged);
      move.current = () => {};
    };
  }, [itemKey]);

  useLayoutEffect(() => { move.current(true); }, [value, itemKey]);

  return <div ref={trackRef} role={role} aria-label={label} className={cn('rx-continuous-tabs', className)}>
    {items.map((item, index) => <button
      key={item.value}
      ref={element => { if (element) buttons.current.set(item.value, element); else buttons.current.delete(item.value); }}
      id={item.id ?? `${instanceId}-${item.value}`}
      type="button"
      role={role === 'tablist' ? 'tab' : undefined}
      aria-selected={role === 'tablist' ? value === item.value : undefined}
      aria-pressed={role === 'group' ? value === item.value : undefined}
      aria-controls={item.controls}
      tabIndex={role === 'tablist' ? value === item.value ? 0 : -1 : undefined}
      className="rx-continuous-trigger"
      onClick={() => onChange(item.value)}
      onKeyDown={event => {
        if (role !== 'tablist') return;
        const next = event.key === 'ArrowRight' ? index + 1 : event.key === 'ArrowLeft' ? index - 1
          : event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : null;
        if (next === null) return;
        event.preventDefault();
        const target = items[Math.max(0, Math.min(items.length - 1, next))];
        onChange(target.value);
        buttons.current.get(target.value)?.focus();
      }}
    ><span>{item.label}</span></button>)}
    <span ref={pillRef} data-continuous-pill className="rx-continuous-pill" aria-hidden="true">
      <span ref={inkRef} data-continuous-ink className="rx-continuous-ink">
        {items.map(item => <span key={item.value}>{item.label}</span>)}
      </span>
    </span>
  </div>;
}
