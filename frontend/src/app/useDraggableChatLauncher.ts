import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react';

const POSITION_STORAGE_KEY = 'rxvita.chat-launcher-position.v1';
const DRAG_THRESHOLD = 6;
const VIEWPORT_INSET = 16;

interface LauncherPosition {
  left: number;
  top: number;
}

interface PointerGesture {
  pointerId: number;
  originX: number;
  originY: number;
  initialLeft: number;
  initialTop: number;
  initialPosition: LauncherPosition | null;
  dragging: boolean;
}

function readPreferredPosition(): LauncherPosition | null {
  if (typeof window === 'undefined') return null;
  try {
    const value: unknown = JSON.parse(window.localStorage.getItem(POSITION_STORAGE_KEY) ?? 'null');
    if (!value || typeof value !== 'object') return null;
    const { left, top } = value as Partial<LauncherPosition>;
    return Number.isFinite(left) && Number.isFinite(top) ? { left: left!, top: top! } : null;
  } catch {
    return null;
  }
}

function savePreferredPosition(position: LauncherPosition) {
  try {
    window.localStorage.setItem(POSITION_STORAGE_KEY, JSON.stringify(position));
  } catch {
    // Position is a best-effort UI preference; dragging remains available without storage.
  }
}

function clampPosition(position: LauncherPosition, element: HTMLButtonElement): LauncherPosition {
  const viewport = window.visualViewport;
  const viewportLeft = viewport?.offsetLeft ?? 0;
  const viewportTop = viewport?.offsetTop ?? 0;
  const viewportWidth = viewport?.width ?? window.innerWidth;
  const viewportHeight = viewport?.height ?? window.innerHeight;
  const viewportRight = viewportLeft + viewportWidth;
  const viewportBottom = viewportTop + viewportHeight;
  const rect = element.getBoundingClientRect();
  const nav = document.querySelector<HTMLElement>("nav[aria-label='주요 화면']");
  const navRect = nav?.getBoundingClientRect();
  const navIsVisible = navRect
    && navRect.width > 0
    && navRect.height > 0
    && navRect.bottom > viewportTop
    && navRect.top < viewportBottom
    && getComputedStyle(nav!).visibility !== 'hidden';
  const elementStyle = getComputedStyle(element);
  const safeAreaBottom = Number.parseFloat(
    elementStyle.getPropertyValue('--chat-launcher-safe-area-bottom'),
  );
  const nonTabBottom = viewportBottom
    - (Number.isFinite(safeAreaBottom) ? Math.max(0, safeAreaBottom) : 0);
  const visibleBottom = navIsVisible ? Math.min(viewportBottom, navRect.top) : nonTabBottom;
  const tailBottom = Number.parseFloat(getComputedStyle(element, '::after').bottom);
  const tailOverflow = Number.isFinite(tailBottom) ? Math.max(0, -tailBottom) : 0;
  const minLeft = viewportLeft + VIEWPORT_INSET;
  const minTop = viewportTop + VIEWPORT_INSET;
  const maxLeft = Math.max(minLeft, viewportRight - VIEWPORT_INSET - rect.width);
  const maxTop = Math.max(
    minTop,
    visibleBottom - VIEWPORT_INSET - rect.height - tailOverflow,
  );

  return {
    left: Math.min(maxLeft, Math.max(minLeft, position.left)),
    top: Math.min(maxTop, Math.max(minTop, position.top)),
  };
}

/** Keeps launcher pointer mechanics separate from its existing auth/navigation action. */
export function useDraggableChatLauncher(pathname: string, onActivate: () => void) {
  const launcherRef = useRef<HTMLButtonElement>(null);
  const preferredRef = useRef<LauncherPosition | null>(null);
  const gestureRef = useRef<PointerGesture | null>(null);
  const suppressPointerClickRef = useRef(false);
  const frameRef = useRef<number | null>(null);
  const [position, setPosition] = useState<LauncherPosition | null>(null);
  const [dragging, setDragging] = useState(false);

  const applyPreferredPosition = useCallback(() => {
    const launcher = launcherRef.current;
    const preferred = preferredRef.current;
    if (!launcher || !preferred) return;
    setPosition(clampPosition(preferred, launcher));
  }, []);

  const schedulePreferredClamp = useCallback(() => {
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    frameRef.current = requestAnimationFrame(() => {
      frameRef.current = null;
      applyPreferredPosition();
    });
  }, [applyPreferredPosition]);

  const abortGesture = useCallback(() => {
    const gesture = gestureRef.current;
    if (!gesture) return;
    gestureRef.current = null;
    suppressPointerClickRef.current = gesture.dragging;
    setDragging(false);
    setPosition(gesture.initialPosition);
    const launcher = launcherRef.current;
    if (launcher?.hasPointerCapture(gesture.pointerId)) {
      try {
        launcher.releasePointerCapture(gesture.pointerId);
      } catch {
        // Capture may already have been released by the browser.
      }
    }
  }, []);

  useLayoutEffect(() => {
    preferredRef.current = readPreferredPosition();
    applyPreferredPosition();
  }, [applyPreferredPosition]);

  useLayoutEffect(() => {
    abortGesture();
    schedulePreferredClamp();
  }, [abortGesture, pathname, schedulePreferredClamp]);

  useEffect(() => {
    const handleBoundsChange = () => {
      abortGesture();
      schedulePreferredClamp();
    };
    const viewport = window.visualViewport;
    const observer = typeof ResizeObserver === 'undefined'
      ? null
      : new ResizeObserver(handleBoundsChange);
    const launcher = launcherRef.current;
    const nav = document.querySelector<HTMLElement>("nav[aria-label='주요 화면']");
    if (launcher) observer?.observe(launcher);
    if (nav) observer?.observe(nav);
    window.addEventListener('resize', handleBoundsChange);
    window.addEventListener('orientationchange', handleBoundsChange);
    viewport?.addEventListener('resize', handleBoundsChange);
    viewport?.addEventListener('scroll', handleBoundsChange);
    return () => {
      observer?.disconnect();
      window.removeEventListener('resize', handleBoundsChange);
      window.removeEventListener('orientationchange', handleBoundsChange);
      viewport?.removeEventListener('resize', handleBoundsChange);
      viewport?.removeEventListener('scroll', handleBoundsChange);
    };
  }, [abortGesture, pathname, schedulePreferredClamp]);

  useEffect(() => () => {
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    const gesture = gestureRef.current;
    const launcher = launcherRef.current;
    gestureRef.current = null;
    if (gesture && launcher?.hasPointerCapture(gesture.pointerId)) {
      try {
        launcher.releasePointerCapture(gesture.pointerId);
      } catch {
        // The browser can release capture as part of removing the element.
      }
    }
  }, []);

  const handlePointerDown = useCallback((event: ReactPointerEvent<HTMLButtonElement>) => {
    if (!event.isPrimary || event.button !== 0 || gestureRef.current) return;
    suppressPointerClickRef.current = false;
    const rect = event.currentTarget.getBoundingClientRect();
    gestureRef.current = {
      pointerId: event.pointerId,
      originX: event.clientX,
      originY: event.clientY,
      initialLeft: rect.left,
      initialTop: rect.top,
      initialPosition: position,
      dragging: false,
    };
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      gestureRef.current = null;
    }
  }, [position]);

  const handlePointerMove = useCallback((event: ReactPointerEvent<HTMLButtonElement>) => {
    const gesture = gestureRef.current;
    if (!gesture || event.pointerId !== gesture.pointerId) return;
    const deltaX = event.clientX - gesture.originX;
    const deltaY = event.clientY - gesture.originY;
    if (!gesture.dragging && Math.hypot(deltaX, deltaY) <= DRAG_THRESHOLD) return;
    if (!gesture.dragging) {
      gesture.dragging = true;
      setDragging(true);
    }
    event.preventDefault();
    const launcher = launcherRef.current;
    if (!launcher) return;
    setPosition(clampPosition({
      left: gesture.initialLeft + deltaX,
      top: gesture.initialTop + deltaY,
    }, launcher));
  }, []);

  const handlePointerUp = useCallback((event: ReactPointerEvent<HTMLButtonElement>) => {
    const gesture = gestureRef.current;
    if (!gesture || event.pointerId !== gesture.pointerId) return;
    gestureRef.current = null;
    setDragging(false);
    if (gesture.dragging) {
      event.preventDefault();
      suppressPointerClickRef.current = true;
      const launcher = launcherRef.current;
      if (launcher) {
        const rect = launcher.getBoundingClientRect();
        const preferred = clampPosition({
          left: Math.round(rect.left),
          top: Math.round(rect.top),
        }, launcher);
        const committed = { left: Math.round(preferred.left), top: Math.round(preferred.top) };
        preferredRef.current = committed;
        setPosition(committed);
        savePreferredPosition(committed);
      }
    } else if (event.pointerType !== 'mouse') {
      // Some touch/pen browsers omit the compatibility click after pointer capture.
      // Activate here and suppress one if the browser does emit it.
      suppressPointerClickRef.current = true;
      onActivate();
    }
  }, [onActivate]);

  const handlePointerCancel = useCallback((event: ReactPointerEvent<HTMLButtonElement>) => {
    if (gestureRef.current?.pointerId === event.pointerId) abortGesture();
  }, [abortGesture]);

  const handleLostPointerCapture = useCallback((event: ReactPointerEvent<HTMLButtonElement>) => {
    if (gestureRef.current?.pointerId === event.pointerId) abortGesture();
  }, [abortGesture]);

  const handleClick = useCallback((event: ReactMouseEvent<HTMLButtonElement>) => {
    if (event.detail !== 0 && suppressPointerClickRef.current) {
      suppressPointerClickRef.current = false;
      event.preventDefault();
      event.stopPropagation();
      return;
    }
    onActivate();
  }, [onActivate]);

  const style: CSSProperties | undefined = position
    ? { left: position.left, top: position.top, right: 'auto', bottom: 'auto' }
    : undefined;

  return {
    launcherRef,
    dragging,
    positioned: position !== null,
    style,
    handleClick,
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
    handlePointerCancel,
    handleLostPointerCapture,
  };
}
