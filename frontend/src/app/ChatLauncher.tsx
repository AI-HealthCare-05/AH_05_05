import { useState, type ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { MessageCircle } from 'lucide-react';
import { LoginPromptSheet } from '@/pages/home/LoginPromptSheet';
import { useSession } from './SessionContext';

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
        className="chat-launcher fixed z-40 flex size-14 items-center justify-center rounded-pill bg-primary text-card shadow-sheet hover:bg-primary-strong"
        onClick={() => authenticated && principalKey ? navigate('/chat') : setLoginOpen(true)}
      >
        <MessageCircle aria-hidden className="size-6" />
      </button>
      <LoginPromptSheet open={loginOpen} onOpenChange={setLoginOpen} onLogin={() => {
        setLoginOpen(false);
        navigate('/login');
      }} />
    </>}
  </div>;
}
