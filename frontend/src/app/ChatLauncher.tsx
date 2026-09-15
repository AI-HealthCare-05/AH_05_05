import { useCallback, useState, type ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { LoginPromptSheet } from '@/pages/home/LoginPromptSheet';
import { useSession } from './SessionContext';
import { useDraggableChatLauncher } from './useDraggableChatLauncher';
import './ChatLauncher.css';

/** Shared by tab and non-tab routes. Entry flows and the chat itself need no launcher. */
export function ChatLauncher({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { authenticated, principalKey } = useSession();
  const [loginOpen, setLoginOpen] = useState(false);
  const registrationPath = pathname.replace(/^\/dev(?=\/)/, '').replace(/\/$/, '');
  const inMedicationRegistration = ['/document-upload', '/ocr-review', '/medication-schedule'].includes(registrationPath);
  const hidden = inMedicationRegistration || ['/', '/login', '/tutorial', '/dev/gallery'].includes(pathname)
    || pathname === '/chat' || pathname.startsWith('/chat/') || pathname.startsWith('/dev/chat');
  const activate = useCallback(() => {
    if (authenticated && principalKey) navigate('/chat');
    else setLoginOpen(true);
  }, [authenticated, navigate, principalKey]);
  const drag = useDraggableChatLauncher(pathname, activate);

  return <div className={hidden ? 'contents' : 'chat-launcher-layout contents'}>
    {children}
    {!hidden && <>
      <button
        ref={drag.launcherRef}
        type="button"
        aria-label="챗봇"
        className={`chat-launcher fixed z-40${drag.positioned ? ' chat-launcher-positioned' : ''}${drag.dragging ? ' is-dragging' : ''}`}
        style={drag.style}
        onClick={drag.handleClick}
        onPointerDown={drag.handlePointerDown}
        onPointerMove={drag.handlePointerMove}
        onPointerUp={drag.handlePointerUp}
        onPointerCancel={drag.handlePointerCancel}
        onLostPointerCapture={drag.handleLostPointerCapture}
      >
        <span className="chat-launcher-portrait" aria-hidden="true">
          <img src="/images/default-profile.png" alt="" draggable={false} />
        </span>
      </button>
      <LoginPromptSheet open={loginOpen} onOpenChange={setLoginOpen} onLogin={() => {
        setLoginOpen(false);
        navigate('/login');
      }} />
    </>}
  </div>;
}
