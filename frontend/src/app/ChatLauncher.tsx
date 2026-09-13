import { useState, type ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { LoginPromptSheet } from '@/pages/home/LoginPromptSheet';
import { useSession } from './SessionContext';
import './ChatLauncher.css';

/** Shared by tab and non-tab routes. Entry flows and the chat itself need no launcher. */
export function ChatLauncher({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { authenticated, principalKey } = useSession();
  const [loginOpen, setLoginOpen] = useState(false);
  const hidden = ['/', '/login', '/tutorial', '/dev/gallery'].includes(pathname)
    || pathname === '/chat' || pathname.startsWith('/chat/') || pathname.startsWith('/dev/chat');

  return <div className={hidden ? 'contents' : 'chat-launcher-layout contents'}>
    {children}
    {!hidden && <>
      <button
        type="button"
        aria-label="챗봇"
        className="chat-launcher fixed z-40"
        onClick={() => authenticated && principalKey ? navigate('/chat') : setLoginOpen(true)}
      >
        <span className="chat-launcher-portrait" aria-hidden="true">
          <img src="/images/default-profile.png" alt="" />
        </span>
      </button>
      <LoginPromptSheet open={loginOpen} onOpenChange={setLoginOpen} onLogin={() => {
        setLoginOpen(false);
        navigate('/login');
      }} />
    </>}
  </div>;
}
