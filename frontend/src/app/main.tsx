import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { Toaster } from '@/shared/ui/sonner';
import { AppRouter } from './router';
import './styles/index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppRouter />
    <Toaster />
  </StrictMode>,
);
