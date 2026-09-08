import type { ReactNode } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { IntakeReport, ReportSource } from '@/entities/intake-report/types';

const evidenceLabels: Record<string, string> = {
  APPROVED_RULE: '승인된 규칙', PUBLIC_GUIDE: '공공 안내', RESEARCH: '연구 근거',
  REGISTERED_INTAKE: '등록한 복용 정보', UNVERIFIED: '확인되지 않은 정보',
};
const slotLabels: Record<string, string> = { MORNING: '아침', LUNCH: '점심', EVENING: '저녁', BEDTIME: '취침 전' };

function safeLink(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : undefined;
  } catch { return undefined; }
}

function ReportSection({ title, children }: { title: string; children: ReactNode }) {
  return <section className="min-w-0 space-y-4 rounded-card bg-card p-5 shadow-card">
    <h2 className="text-lg font-bold text-foreground">{title}</h2>{children}
  </section>;
}

function Sources({ sources }: { sources: ReportSource[] }) {
  if (!sources.length) return null;
  return <ul className="space-y-2 text-xs text-muted-foreground" aria-label="근거 출처">
    {sources.map((source, index) => {
      const href = safeLink(source.url);
      return <li key={index} className="break-words">
        {href ? <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-4">{source.title}</a> : <span>{source.title}</span>}
        {source.organization ? ` · ${source.organization}` : ''} · {evidenceLabels[source.evidenceLevel] ?? '근거 수준 미확인'}
      </li>;
    })}
  </ul>;
}

function CountChart({ title, items, unit }: { title: string; items: [string, number][]; unit: string }) {
  const maximum = Math.max(1, ...items.map(([, count]) => count));
  return <figure aria-label={title} className="space-y-3">
    <figcaption className="text-sm font-bold">{title}</figcaption>
    {items.map(([label, value]) => <div key={label} className="space-y-1">
      <div className="flex justify-between gap-3 text-sm"><span>{label}</span><span className="tabular-nums">{value}{unit}</span></div>
      <div className="h-2 overflow-hidden rounded-pill bg-muted" aria-hidden="true">
        <div className="h-full rounded-pill bg-primary" style={{ width: `${Math.max(0, Math.min(100, value / maximum * 100))}%` }} />
      </div>
    </div>)}
  </figure>;
}

const tableClass = 'w-full min-w-[28rem] text-left text-sm [&_th]:border-b [&_th]:border-border [&_th]:p-3 [&_th]:font-bold [&_td]:border-b [&_td]:border-border [&_td]:p-3 [&_td]:align-top';

export function IntakeReportBody({ report }: { report: IntakeReport }) {
  const chart = report.chartData;
  const generated = new Date(report.generatedAt);
  return <div className="min-w-0 space-y-5 text-foreground">
    <p className="text-xs text-muted-foreground">{Number.isNaN(generated.getTime()) ? '생성 시각 미확인' : `${generated.toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })} 기준`}</p>
    {report.reportStatus === 'PARTIAL' && <p role="status" className="rounded-card bg-primary-bg p-4 text-sm leading-relaxed">일부 정보를 확인하지 못했어요. 확인 가능한 정보만 담았으며, 정보 부족은 안전하다는 뜻이 아니에요.</p>}
    <ReportSection title="복용 정보 요약">
      <p className="break-keep text-sm leading-relaxed">{report.executiveSummary.summary}</p>
      <dl className="divide-y divide-border">{report.executiveSummary.summaryCards.map(card => <div key={card.key} className="flex items-center justify-between gap-3 py-3 text-sm"><dt>{card.label}</dt><dd className="shrink-0 font-bold tabular-nums text-primary">{card.value}{card.unit}</dd></div>)}</dl>
      <p className="text-xs leading-relaxed text-muted-foreground">확인 항목이 0건이어도 안전성이 보장되는 것은 아니에요. 복용 변경은 의료진과 상의하세요.</p>
    </ReportSection>
    <ReportSection title="한눈에 보기">
      <CountChart title="검토한 제품 수" unit="개" items={[["복용약", chart.medicationCount], ["영양제", chart.supplementCount]]} />
      <CountChart title="확인 항목 수" unit="건" items={[["상호작용", chart.interactionCardCount], ["중복", chart.redundancyCardCount], ["주의", chart.cautionCardCount], ["정보 부족", chart.missingInfoCardCount]]} />
    </ReportSection>
    {report.currentStack.length > 0 && <ReportSection title="현재 복용 목록">
      <div role="region" aria-label="현재 복용 목록 표 가로 스크롤" tabIndex={0} className="overflow-x-auto focus-visible:outline-2 focus-visible:outline-primary">
        <table aria-label="현재 복용 목록" className={tableClass}>
          <thead><tr><th scope="col">제품</th><th scope="col">등록한 복용 정보</th><th scope="col">시간대</th></tr></thead>
          <tbody>{report.currentStack.map(item => <tr key={`${item.itemType}-${item.itemId}`}>
            <td><strong className="block">{item.productName}</strong><span className="text-xs text-muted-foreground">{item.itemType === 'MEDICATION' ? '복용약' : item.itemType === 'SUPPLEMENT' ? '영양제' : '기타'}{item.ingredientName ? ` · ${item.ingredientName}` : ''}</span></td>
            <td>{item.registeredIntakeInfo}<span className="mt-1 block text-xs text-muted-foreground">{evidenceLabels[item.evidenceLevel] ?? '근거 수준 미확인'}</span></td>
            <td>{item.scheduledSlots.map(slot => slotLabels[slot.toUpperCase()] ?? slot).join(' · ') || '미등록'}</td>
          </tr>)}</tbody>
        </table>
      </div>
    </ReportSection>}
    {report.reviewCards.length > 0 && <ReportSection title="확인이 필요한 항목">
      {report.reviewCards.map((card, index) => <article key={index} className="space-y-2 border-b border-border pb-4 last:border-0 last:pb-0">
        <h3 className="font-bold">{card.title}</h3><p className="text-sm leading-relaxed">{card.summary}</p>
        <p className="text-xs text-muted-foreground">{card.relatedItems.join(' · ')} · {evidenceLabels[card.evidenceLevel] ?? '근거 수준 미확인'}</p>
        <p className="text-sm font-medium">{card.checkItem}</p><Sources sources={card.sources} />
      </article>)}
    </ReportSection>}
    {report.nutrientTotals.length > 0 && <ReportSection title="일일 성분 합계">
      <p className="text-xs text-muted-foreground">함량·단위·복용 횟수를 확인할 수 있는 성분만 표시해요. 식단은 포함하지 않아요.</p>
      <div role="region" aria-label="일일 성분 합계 표 가로 스크롤" tabIndex={0} className="overflow-x-auto focus-visible:outline-2 focus-visible:outline-primary">
        <table aria-label="일일 성분 합계" className={tableClass}><thead><tr><th scope="col">성분</th><th scope="col">하루 합계</th><th scope="col">포함 제품</th></tr></thead><tbody>
          {report.nutrientTotals.map((item, index) => <tr key={index}><td>{item.nutrientName}</td><td>{item.dailyTotal}</td><td>{item.includedProductNames.join(' · ')}</td></tr>)}
        </tbody></table>
      </div>
    </ReportSection>}
    {report.productGuides.length > 0 && <ReportSection title="제품별 안내">
      {report.productGuides.map((guide, index) => <article key={index} className="space-y-2 border-b border-border pb-4 last:border-0 last:pb-0"><h3 className="font-bold">{guide.productName}</h3><p className="text-sm">{guide.oneLineSummary}</p>{guide.generalRole && <p className="text-sm">{guide.generalRole}</p>}<p className="text-sm text-muted-foreground">{guide.checkItem}</p><Sources sources={guide.sources} /></article>)}
    </ReportSection>}
    {report.unverifiedItems.length > 0 && <ReportSection title="정보가 부족한 항목">
      {report.unverifiedItems.map((item, index) => <article key={index} className="space-y-2 text-sm"><h3 className="font-bold">{item.title}</h3><p>{item.message}</p><p className="text-muted-foreground">{item.relatedItems.join(' · ')}</p><p>{item.nextStep}</p></article>)}
    </ReportSection>}
    {report.reportMarkdown && <ReportSection title="상세 보고서">
      <div className="break-words text-sm leading-relaxed [&_h2]:my-4 [&_h2]:text-lg [&_h2]:font-bold [&_h3]:my-3 [&_h3]:font-bold [&_p]:my-3 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_li]:my-1 [&_pre]:overflow-x-auto">
        <Markdown remarkPlugins={[remarkGfm]} skipHtml urlTransform={url => safeLink(url) ?? ''} disallowedElements={['img']} components={{
          h1: ({ children }) => <h2>{children}</h2>,
          a: ({ href, children }) => safeLink(href) ? <a href={safeLink(href)} target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-4">{children}</a> : <span>{children}</span>,
          table: ({ children }) => <div className="overflow-x-auto" role="region" aria-label="보고서 본문 표 가로 스크롤" tabIndex={0}><table className={tableClass}>{children}</table></div>,
        }}>{report.reportMarkdown}</Markdown>
      </div>
    </ReportSection>}
    <p className="text-xs leading-relaxed text-muted-foreground">이 보고서는 참고용이며 진단이나 처방을 대신하지 않아요. 보고서와 채팅 이력에 저장되지 않으며, 화면을 나가거나 새로고침하면 사라져요.</p>
  </div>;
}
