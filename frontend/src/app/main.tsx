import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { Toaster } from '@/shared/ui/sonner';
import { AppRouter } from './router';
import { SessionProvider } from './SessionContext';
import './styles/index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <SessionProvider>
      <AppRouter />
      <Toaster />
    </SessionProvider>
  </StrictMode>,
);
