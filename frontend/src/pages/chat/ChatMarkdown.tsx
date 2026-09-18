import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// 수치 범위의 ~와 ~~를 원문 그대로 보존한다. CSS로 선만 숨기면
// 파서가 소모한 물결표는 복원되지 않으므로 취소선 문법만 비활성화한다.
function remarkLiteralTildes(this: { data(): object }) {
  const data = this.data() as { micromarkExtensions?: unknown[] };
  const extensions = data.micromarkExtensions ?? (data.micromarkExtensions = []);
  extensions.push({ disable: { null: ['strikethrough'] } });
}

// Match the report renderer's policy: only explicit HTTP(S) sources may navigate.
function safeLink(value: string | undefined): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : undefined;
  } catch { return undefined; }
}

export function ChatMarkdown({ text }: { text: string }) {
  return <div aria-label="답변 본문" className="min-w-0 text-base leading-relaxed text-foreground [overflow-wrap:anywhere] [&_h2]:my-3 [&_h2]:text-lg [&_h2]:font-bold [&_h3]:my-2 [&_h3]:font-bold [&_h4]:font-bold [&_h5]:font-bold [&_h6]:font-bold [&_p]:whitespace-pre-wrap [&_p+p]:mt-3 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_li]:my-1 [&_blockquote]:my-3 [&_blockquote]:border-l-2 [&_blockquote]:border-primary [&_blockquote]:pl-3 [&_hr]:my-3 [&_hr]:border-border [&_code]:rounded [&_code]:bg-card [&_code]:px-1 [&_code]:text-sm">
    <Markdown remarkPlugins={[remarkGfm, remarkLiteralTildes]} skipHtml disallowedElements={['img']} urlTransform={url => safeLink(url) ?? ''} components={{
      h1: ({ children }) => <h2>{children}</h2>,
      a: ({ href, children }) => safeLink(href)
        ? <a href={safeLink(href)} target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-4">{children}</a>
        : <span>{children}</span>,
      pre: ({ children }) => <pre tabIndex={0} aria-label="답변 코드 가로 스크롤" className="my-3 max-w-full overflow-x-auto rounded-input bg-card p-3 [overflow-wrap:normal]">{children}</pre>,
      table: ({ children }) => <div role="region" aria-label="답변 표 가로 스크롤" tabIndex={0} className="my-3 max-w-full overflow-x-auto"><table className="min-w-[24rem] text-left text-sm [&_th]:min-w-24 [&_th]:border-b [&_th]:border-border [&_th]:p-2 [&_td]:min-w-24 [&_td]:border-b [&_td]:border-border [&_td]:p-2 [&_td]:align-top">{children}</table></div>,
    }}>{text}</Markdown>
  </div>;
}
