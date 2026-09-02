import type { ReactNode } from 'react';
import { useNavigate } from 'react-router';
import { Header } from '@/shared/ui';

interface LegalDocumentPageProps {
  title: string;
  description: ReactNode;
  children: ReactNode;
}

export function LegalDocumentPage({ title, description, children }: LegalDocumentPageProps) {
  const navigate = useNavigate();

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title={title} onBack={() => navigate(-1)} />
      <main className="flex flex-1 flex-col gap-6 px-page-x py-6 text-sm leading-7 text-foreground">
        <div className="rounded-card bg-primary-bg px-4 py-4 text-muted-foreground">
          {description}
        </div>
        {children}
        <p className="border-t border-border pt-5 text-xs text-muted-foreground">
          시행일: 2026년 9월 2일
        </p>
      </main>
    </div>
  );
}

export function LegalSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-base font-bold text-foreground">{title}</h2>
      <div className="text-muted-foreground">{children}</div>
    </section>
  );
}

export function LegalList({ children }: { children: ReactNode }) {
  return <ul className="list-disc space-y-1 pl-5">{children}</ul>;
}
