import type { IntakeReport, NutrientTotal } from '@/entities/intake-report/types';
import { ReportMarkdown, ReportSection, reportTableClass, slotLabels } from './reportViewPrimitives';

const fallbackLabels: Record<string, string> = { CLIENT_ERROR: 'AI 응답을 받지 못했어요.', VALIDATION_FAILED: '생성된 내용이 근거 검증을 통과하지 못했어요.' };

function nutrientWidth(percent: number): number {
  if (!Number.isFinite(percent) || percent <= 0) return 0;
  if (percent <= 100) return percent * 0.75;
  return Math.min(100, 75 + (percent - 100) * (25 / 30));
}

function NutrientBar({ item }: { item: NutrientTotal }) {
  const percent = item.referencePercent === null || item.referencePercent === undefined ? Number.NaN : Number(item.referencePercent);
  const hasComparableAmount = item.amount !== null && item.amount !== undefined && item.amount !== '' && item.referenceValue !== null && item.referenceValue !== undefined && item.referenceValue !== '' && Number.isFinite(percent);
  const referenceLabel = item.referenceKind === 'RNI' ? '권장섭취량' : item.referenceKind === 'AI' ? '충분섭취량' : null;
  const amount = item.amount && item.unit ? `${item.amount}${item.unit}` : item.dailyTotal;
  return <article className="min-w-0 space-y-2 border-b border-border pb-4 last:border-0 last:pb-0">
    <div className="flex min-w-0 items-baseline justify-between gap-3">
      <h3 className="min-w-0 break-words font-bold">{item.nutrientName} <span className="font-normal text-muted-foreground">{amount}</span></h3>
      <strong className="shrink-0 tabular-nums text-primary">{hasComparableAmount ? `${item.referencePercent}%` : '미확인'}</strong>
    </div>
    {hasComparableAmount ? <>
      <div className="h-2 overflow-hidden rounded-pill bg-muted" role="img" aria-label={`${item.nutrientName} ${item.referencePercent}%`}>
        <span className="block h-full rounded-pill bg-primary" style={{ width: `${nutrientWidth(percent)}%` }} />
      </div>
      <div className="relative h-4 text-micro text-muted-foreground" aria-hidden="true"><span className="absolute left-0">0%</span><span className="absolute left-[75%] -translate-x-1/2">100%</span><span className="absolute right-0">130%+</span></div>
      <p className="text-xs text-muted-foreground">{referenceLabel} {item.referenceValue}{item.unit ?? ''} 기준 · 확인된 합계 {amount}</p>
    </> : <p className="text-xs leading-relaxed text-muted-foreground">비교 기준 또는 함량이 미확인이라 막대를 표시하지 않았어요.</p>}
    {item.unknownProductNames?.length ? <p className="break-words text-xs text-muted-foreground">확인 필요 제품: {item.unknownProductNames.join(' · ')}</p> : null}
    {item.includedProductNames.length > 0 && <p className="break-words text-xs text-muted-foreground">포함 제품 · {item.includedProductNames.join(' · ')}</p>}
  </article>;
}

export function AiReportBody({ report }: { report: IntakeReport }) {
  const fallbackUsed = report.fallbackUsed ?? false;
  const fallbackReason = report.fallbackReason?.trim();
  const hasMarkdown = report.reportMarkdown.trim().length > 0;
  const profile = report.profileLabel ?? `등록한 복용약 ${report.dataAvailability.activeMedicationCount}종 · 영양제 ${report.dataAvailability.activeSupplementCount}종`;

  return <div className="min-w-0 space-y-5 text-foreground">
    <section aria-label="AI 보고서 개요" className="min-w-0 space-y-3 rounded-card bg-primary-bg p-5 shadow-card">
      <p className="w-fit rounded-pill bg-card px-2 py-1 text-micro font-bold text-primary">AI 보고서</p>
      <h1 className="text-2xl font-bold leading-tight">맞춤 복용 보고서</h1>
      <p className="break-words text-sm text-muted-foreground">{profile}</p>
      {report.basisNote && <p className="break-words text-sm leading-relaxed">{report.basisNote}</p>}
    </section>

    {fallbackUsed && <section role="alert" className="rounded-card border border-primary bg-primary-bg p-4 text-sm leading-relaxed">
      <p className="font-bold">AI 생성 결과가 아니라 확인된 등록정보·근거를 표시합니다.</p>
      {fallbackReason && <p className="mt-1 text-muted-foreground">사유: {fallbackLabels[fallbackReason] ?? fallbackReason}</p>}
    </section>}

    <ReportSection title={fallbackUsed ? '확인된 정보 보고서' : 'AI 분석 보고서'} id="ai-report-markdown">
      {hasMarkdown ? <ReportMarkdown markdown={report.reportMarkdown} /> : <p role="status" className="text-sm leading-relaxed text-muted-foreground">{fallbackUsed ? '확인된 등록정보와 근거만 표시할 수 있습니다.' : 'AI 보고서 본문을 받지 못했습니다.'}</p>}
    </ReportSection>

    {report.currentStack.length > 0 && <ReportSection title="등록한 복용 정보" id="ai-report-stack">
      <div role="region" aria-label="현재 복용 목록 표 가로 스크롤" tabIndex={0} className="overflow-x-auto focus-visible:outline-2 focus-visible:outline-primary">
        <table aria-label="현재 복용 목록" className={reportTableClass}>
          <thead><tr><th scope="col">제품</th><th scope="col">등록한 복용 정보</th><th scope="col">시간대</th></tr></thead>
          <tbody>{report.currentStack.map(item => <tr key={`${item.itemType}-${item.itemId}`}>
            <td><strong className="block">{item.productName}</strong><span className="text-xs text-muted-foreground">{item.itemType === 'MEDICATION' ? '복용약' : item.itemType === 'SUPPLEMENT' ? '영양제' : '기타'}{item.ingredientName ? ` · ${item.ingredientName}` : ''}</span></td>
            <td>{item.registeredIntakeInfo}</td>
            <td>{item.scheduledSlots.map(slot => slotLabels[slot.toUpperCase()] ?? slot).join(' · ') || '미등록'}</td>
          </tr>)}</tbody>
        </table>
      </div>
    </ReportSection>}

    {report.nutrientTotals.length > 0 && <ReportSection title="영양소 합계" id="ai-report-nutrients">
      <p className="text-xs leading-relaxed text-muted-foreground">식단은 포함하지 않으며, 확인되지 않은 함량은 0으로 계산하지 않았어요. 100%는 권장·충분섭취량 비교 기준이며, 이 비율만으로 부족·과다를 판단하지 않아요.</p>
      {report.nutrientTotals.map((item, index) => <NutrientBar key={`${item.nutrientName}-${index}`} item={item} />)}
    </ReportSection>}

    {report.unverifiedItems.length > 0 && <ReportSection title="확인하지 못한 정보" id="ai-report-unverified">
      {report.unverifiedItems.map((item, index) => <p key={`${item.title}-${index}`} className="break-words text-sm leading-relaxed"><strong>{item.title}</strong> · {item.message} {item.nextStep}</p>)}
    </ReportSection>}

    <p className="text-xs leading-relaxed text-muted-foreground">이 보고서는 참고용이며 진단이나 처방을 대신하지 않아요. 복용 변경은 의료진과 상의하세요. 보고서는 저장되지 않으며 화면을 나가거나 새로고침하면 사라져요.</p>
  </div>;
}
