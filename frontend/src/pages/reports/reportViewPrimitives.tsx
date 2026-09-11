import type { ReactNode } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export const slotLabels: Record<string, string> = { MORNING: '아침', LUNCH: '점심', EVENING: '저녁', BEDTIME: '취침 전' };

export function safeLink(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : undefined;
  } catch { return undefined; }
}

export function ReportSection({ title, children, id }: { title: string; children: ReactNode; id?: string }) {
  return <section aria-labelledby={id} className="min-w-0 space-y-4 rounded-card bg-card p-5 shadow-card">
    <h2 id={id} className="text-lg font-bold text-foreground">{title}</h2>{children}
  </section>;
}

export const reportTableClass = 'w-full min-w-[28rem] text-left text-sm [&_th]:border-b [&_th]:border-border [&_th]:p-3 [&_th]:font-bold [&_td]:border-b [&_td]:border-border [&_td]:p-3 [&_td]:align-top';

/** Renders server-provided Markdown without raw HTML, images, or unsafe URLs. */
export function ReportMarkdown({ markdown }: { markdown: string }) {
  return <div className="break-words text-sm leading-relaxed [&_h2]:my-4 [&_h2]:text-lg [&_h2]:font-bold [&_h3]:my-3 [&_h3]:font-bold [&_p]:my-3 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_li]:my-1 [&_pre]:overflow-x-auto">
    <Markdown remarkPlugins={[remarkGfm]} skipHtml urlTransform={url => safeLink(url) ?? ''} disallowedElements={['img']} components={{
      h1: ({ children }) => <h2>{children}</h2>,
      a: ({ href, children }) => {
        const safeHref = safeLink(href);
        return safeHref ? <a href={safeHref} target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-4">{children}</a> : <span>{children}</span>;
      },
      table: ({ children }) => <div className="overflow-x-auto" role="region" aria-label="보고서 본문 표 가로 스크롤" tabIndex={0}><table className={reportTableClass}>{children}</table></div>,
    }}>{markdown}</Markdown>
  </div>;
}
