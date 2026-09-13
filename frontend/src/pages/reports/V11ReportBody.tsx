import { useId, useLayoutEffect, useRef, useState, type ReactElement } from 'react';
import type { IntakeReport, NutrientTotal } from '@/entities/intake-report/types';
import { safeLink } from './reportViewPrimitives';
import './V11ReportBody.css';

function decodeEntitiesOnce(text: string): string {
  if (typeof document === 'undefined' || !text.includes('&')) return text;
  const decoder = document.createElement('textarea');
  return text.replace(/&(?:#[0-9]+|#[xX][0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]+);/g, token => {
    // Only an entity token, never markup or the whole source string, reaches the parser.
    decoder.innerHTML = token;
    return decoder.value;
  });
}

const evidenceLabels: Record<string, string> = {
  APPROVED_RULE: '승인된 규칙', PUBLIC_GUIDE: '공개 안내', RESEARCH: '연구 근거',
  REGISTERED_INTAKE: '등록한 복용 정보', UNVERIFIED: '확인되지 않은 정보',
};

function CollapsibleText({ text, forceOpen = false }: { text: string; forceOpen?: boolean }) {
  const decoded = decodeEntitiesOnce(text);
  const textRef = useRef<HTMLParagraphElement>(null);
  const textId = useId();
  const [canExpand, setCanExpand] = useState(false);
  const [expanded, setExpanded] = useState(false);
  useLayoutEffect(() => {
    setExpanded(false);
    const element = textRef.current;
    if (!element || forceOpen) return;
    let active = true;
    const measure = () => {
      if (!active) return;
      const lineHeight = Number.parseFloat(getComputedStyle(element).lineHeight);
      const clipped = element.scrollHeight > lineHeight * 3 + 1;
      setCanExpand(clipped);
      if (!clipped) setExpanded(false);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    void document.fonts.ready.then(measure);
    document.fonts.addEventListener('loadingdone', measure);
    return () => {
      active = false;
      observer.disconnect();
      document.fonts.removeEventListener('loadingdone', measure);
    };
  }, [decoded, forceOpen]);
  if (forceOpen) return <p>{decoded}</p>;
  return <div className="v11-collapsible">
    <p ref={textRef} id={textId} className={expanded ? 'v11-collapsible-full' : 'v11-collapsible-preview'}>{decoded}</p>
    {canExpand ? <button type="button" className={expanded ? 'v11-collapse-label' : 'v11-expand-label'} aria-expanded={expanded} aria-controls={textId} onClick={() => setExpanded(value => !value)}>
      {expanded ? '접기' : '자세히 펼쳐보기'}<span aria-hidden="true">{expanded ? '▴' : '▾'}</span>
    </button> : null}
  </div>;
}

function ActionGroupedCards<T extends { action?: string | null }>({ cards, contextKey, renderCard }: {
  cards: T[];
  contextKey: (card: T) => string;
  renderCard: (card: T, showAction: boolean, index: number) => ReactElement;
}) {
  const groups: { action: string; members: { card: T; index: number }[] }[] = [];
  const byKey = new Map<string, number>();
  cards.forEach((card, index) => {
    const action = decodeEntitiesOnce(card.action ?? '').replace(/\s+/g, ' ').trim();
    const key = JSON.stringify([contextKey(card), action]);
    const existing = action ? byKey.get(key) : undefined;
    if (existing !== undefined) groups[existing].members.push({ card, index });
    else {
      if (action) byKey.set(key, groups.length);
      groups.push({ action, members: [{ card, index }] });
    }
  });
  return <>{groups.map(group => group.members.length > 1
    ? <div className="v11-action-group" key={group.members[0].index}>
      <p className="v11-action v11-action-shared"><span className="v11-action-shared-label">공통 안내 · {group.members.length}개 항목</span>{group.action}</p>
      {group.members.map(({ card, index }) => renderCard(card, false, index))}
    </div>
    : renderCard(group.members[0].card, true, group.members[0].index))}</>;
}

const nutrientValueFormatter = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 10 });

function nutrientNumber(value: string | null | undefined): number | null {
  if (value == null || value.trim() === '') return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}

function NutrientBar({ item }: { item: NutrientTotal }) {
  const amount = nutrientNumber(item.amount);
  const reference = nutrientNumber(item.referenceValue) || null;
  const suppliedUpper = nutrientNumber(item.upperLimitValue) || null;
  const upper = suppliedUpper !== null && (reference === null || suppliedUpper >= reference) ? suppliedUpper : null;
  const scale = upper ?? reference;
  const comparable = amount !== null && scale !== null && Boolean(item.unit);
  const position = (value: number) => Math.min(100, Math.max(0, value / (scale ?? 1) * 80));
  const referencePosition = reference === null ? null : position(reference);
  const closeLabels = upper !== null && referencePosition !== null && 80 - referencePosition < 20;
  const overUpper = upper !== null && amount !== null && amount > upper;
  const referenceLabel = item.referenceKind === 'AI' ? '충분' : item.referenceKind === 'RNI' ? '권장' : '기준';
  const threshold = (kind: 'reference' | 'upper', value: number, left: number, label: string) => <div
    data-threshold={kind}
    className={`v11-range-label${closeLabels ? ` v11-range-label-close-${kind}` : ''}`}
    style={{ left: `${Math.min(90, Math.max(8, left))}%` }}
  ><span>{label}</span><span>{nutrientValueFormatter.format(value)}</span></div>;
  return <article className="v11-nutrient">
    <h3>{item.nutrientName}</h3>
    <p className="v11-nutrient-amount">{amount === null ? '미확인' : item.amount}<span>{amount === null ? '' : item.unit}</span></p>
    {comparable ? <div className={`v11-range${overUpper ? ' v11-range-over' : ''}`} role="img"
      aria-label={`${item.nutrientName} 합계 ${item.amount}${item.unit}${reference === null ? '' : `, ${referenceLabel} ${item.referenceValue}${item.unit}`}${upper === null ? '' : `, 상한 ${item.upperLimitValue}${item.unit}`}${overUpper ? ', 상한 초과' : ''}`}>
      <div className="v11-range-track"><span style={{ width: `${position(amount)}%` }} /></div>
      {reference !== null && <><i className="v11-range-tick" data-range-tick="reference" style={{ left: `${referencePosition}%` }} />{threshold('reference', reference, referencePosition!, referenceLabel)}</>}
      {upper !== null && <><i className="v11-range-tick" data-range-tick="upper" style={{ left: '80%' }} />{threshold('upper', upper, 80, '상한')}</>}
      <i className="v11-range-dot" data-range-dot style={{ left: `${position(amount)}%` }} />
    </div> : <p className="v11-reference">{amount === null ? '함량 또는 복용량을 확인할 수 없어 합계와 막대를 표시하지 않았어요.' : '비교 기준 없음 · 확인된 합계만 표시했어요.'}</p>}
    {overUpper ? <p className="v11-range-warning">상한 초과</p> : null}
    {comparable && upper === null ? <p className="v11-reference">{item.upperLimitNote || '상한 기준을 확인할 수 없어요.'}</p> : null}
  </article>;
}

function interactionLabel(evidenceLevel: string, actionLevel: 'WARNING' | 'CHECK' | 'INFORMATION') {
  if (evidenceLevel === 'PUBLIC_GUIDE') return '공개 안내 · 개인 조합 확인 필요';
  if (actionLevel === 'WARNING') return '중요 주의';
  if (actionLevel === 'CHECK') return '복용 전 상담';
  return '확인할 점';
}

export function V11ReportBody({ report }: { report: IntakeReport }) {
  const cards = report.cards;
  if (!cards) return null;
  const medications = report.currentStack.filter(item => item.itemType === 'MEDICATION');
  const supplements = report.currentStack.filter(item => item.itemType === 'SUPPLEMENT');
  const nutrientTotals = report.nutrientTotals.filter(item => item.amount == null || item.amount.trim() === '' || Number(item.amount) !== 0);
  const registeredByMedicationId = new Map(medications.map(item => [item.itemId, item.registeredIntakeInfo]));
  const sortedInteractions = cards.interactions.slice().sort((a, b) => Number(b.actionLevel === 'WARNING') - Number(a.actionLevel === 'WARNING'));
  const actualCounts = `등록한 복용약 ${report.dataAvailability.activeMedicationCount}종 · 영양제 ${report.dataAvailability.activeSupplementCount}종`;

  return <div className="v11-report">
    <section className="v11-hero" aria-label="리포트 개요">
      <span className="v11-eyebrow">약·영양제 리포트</span>
      <h1>먼저 확인할 것부터<br />정리했어요</h1>
      {report.profileLabel ? <p className="v11-meta">{report.profileLabel}</p> : null}
      <details className="v11-registered-products">
        <summary>{actualCounts}</summary>
        {supplements.length > 0 ? <p className="v11-product-ingredients">영양제 성분 · 등록한 하루량 기준</p> : null}
        <div className="v11-product-columns">
          {[{ label: '복용약', items: medications }, { label: '영양제', items: supplements }].map(({ label, items }) => <div className="v11-product-column" key={label}>
            <h3>{label} {items.length}종</h3>
            {items.length > 0 ? <ul aria-label={`등록한 ${label}`}>
              {items.map(item => <li key={item.itemId}>
                {decodeEntitiesOnce(item.productName)}
                {item.itemType === 'SUPPLEMENT' ? <p className="v11-product-ingredients">{decodeEntitiesOnce(item.ingredientSummary?.trim() || '성분·함량 확인 필요')}</p> : null}
                {item.itemType === 'SUPPLEMENT' ? <p className="v11-product-intake">사용자가 등록한 복용 정보 · {decodeEntitiesOnce(item.registeredIntakeInfo || '미등록')}</p> : null}
              </li>)}
            </ul> : <p className="v11-hint">등록된 제품 없음</p>}
          </div>)}
        </div>
      </details>
    </section>

    {report.reportStatus === 'PARTIAL' ? <p role="status" className="v11-status">일부 정보를 확인하지 못했어요. 확인 가능한 정보만 담았으며, 정보 부족은 안전하다는 뜻이 아니에요.</p> : null}

    <nav className="v11-anchor-chips" aria-label="리포트 바로가기">
      <a href="#v11-interactions">함께 확인</a>
      {cards.overlaps.length > 0 ? <a href="#v11-overlaps">영양제 중복</a> : null}
      {cards.lifestyle.length > 0 ? <a href="#v11-lifestyle">생활습관</a> : null}
      {nutrientTotals.length > 0 ? <a href="#v11-nutrients">영양소</a> : null}
      {cards.medications.length > 0 ? <a href="#v11-medications">약 정보</a> : null}
    </nav>

    <section id="v11-interactions" className="v11-card v11-interaction-card" aria-labelledby="v11-interactions-title">
      <h2 id="v11-interactions-title">함께 확인할 주의사항</h2>
      {sortedInteractions.length === 0 ? <p className="v11-hint">확인된 조합 근거가 충분하지 않아 표시할 주의사항이 없어요. 안전하다는 뜻은 아니며, 새 제품을 추가하거나 복용을 바꾸기 전에는 전문가에게 확인하세요.</p> : null}
      <ActionGroupedCards cards={sortedInteractions} contextKey={card => JSON.stringify([card.evidenceLevel, card.actionLevel])} renderCard={(card, showAction) => <article className={`v11-pair ${card.actionLevel === 'WARNING' ? 'v11-urgent' : ''}`} key={card.id}>
        <span className="v11-tag">{interactionLabel(card.evidenceLevel, card.actionLevel)}</span>
        <h3>{decodeEntitiesOnce(card.title)}</h3><CollapsibleText text={card.summary} forceOpen={card.actionLevel === 'WARNING'} />{showAction && card.action ? <p className="v11-action">{decodeEntitiesOnce(card.action)}</p> : null}
      </article>} />
    </section>

    {cards.overlaps.length > 0 ? <section id="v11-overlaps" className="v11-card" aria-labelledby="v11-overlaps-title">
      <h2 id="v11-overlaps-title">영양제끼리 확인할 점</h2>
      <ActionGroupedCards cards={cards.overlaps} contextKey={() => ''} renderCard={(card, showAction, index) => <article className="v11-pair" key={`${card.nutrientName}-${index}`}>
        <span className="v11-tag">성분 중복</span><h3>{decodeEntitiesOnce(card.title)}</h3><CollapsibleText text={card.summary} />{showAction && card.action ? <p className="v11-action">{decodeEntitiesOnce(card.action)}</p> : null}
      </article>} />
    </section> : null}

    {cards.lifestyle.length > 0 ? <section id="v11-lifestyle" className="v11-card" aria-labelledby="v11-lifestyle-title">
      <h2 id="v11-lifestyle-title">생활습관 가이드</h2>
      <ActionGroupedCards cards={cards.lifestyle} contextKey={card => card.category ?? ''} renderCard={(card, showAction) => <article className="v11-pair" key={card.id}>
        {card.category ? <span className="v11-tag">{card.category}</span> : null}<h3>{decodeEntitiesOnce(card.title)}</h3><CollapsibleText text={card.summary} />{showAction && card.action ? <p className="v11-action">{decodeEntitiesOnce(card.action)}</p> : null}
      </article>} />
    </section> : null}

    {nutrientTotals.length > 0 ? <section id="v11-nutrients" className="v11-card" aria-labelledby="v11-nutrients-title">
      <h2 id="v11-nutrients-title">영양제 성분 합계</h2>
      <ul className="v11-hint v11-nutrient-notes">
        {report.basisNote ? <>
          <li>{report.basisNote}</li>
          <li>직접 입력한 영양제와 의약품의 성분은 합산에 포함되지 않아요.</li>
        </> : <>
          <li>검색된 영양제의 성분만 합산된 결과예요.</li>
          <li>직접 입력한 영양제는 성분 합산에 포함되지 않아요.</li>
          <li>음식과 의약품을 통한 섭취량은 포함되지 않아요.</li>
        </>}
      </ul>
      <div className="v11-nutrient-grid">{nutrientTotals.map((item, index) => <NutrientBar key={`${item.nutrientName}-${index}`} item={item} />)}</div>
      <p className="v11-hint">영양제 합계 기준이며 식사는 제외됩니다. 상한은 섭취 목표가 아닙니다.</p>
    </section> : null}

    {cards.medications.length > 0 ? <section id="v11-medications" className="v11-card" aria-labelledby="v11-medications-title">
      <h2 id="v11-medications-title">약 정보</h2>
      {cards.medications.map(card => {
        const registeredIntake = registeredByMedicationId.get(card.itemId)?.trim();
        const includesRegisteredIntake = card.details.some(detail => /등록.*복용|복용.*등록/.test(detail.label));
        return <article className="v11-medicine" key={card.itemId}>
          <h3>{card.productName}</h3>
          {card.identityNotice ? <p className="v11-hint">{decodeEntitiesOnce(card.identityNotice)}</p> : null}
          <dl>
            <div><dt>효능</dt><dd>{decodeEntitiesOnce(card.efficacy.text)}</dd></div>
          </dl>
          <details>
            <summary>약 정보 더 보기</summary>
            <dl>
              <div><dt>주의</dt><dd>{decodeEntitiesOnce(card.caution.text)}</dd></div>
              <div><dt>금기</dt><dd>{decodeEntitiesOnce(card.contraindication.text)}</dd></div>
            </dl>
            {registeredIntake && !includesRegisteredIntake ? <div className="v11-extra"><strong>사용자가 등록한 복용 정보</strong><p>{registeredIntake}</p></div> : null}
            {card.details.map((detail, index) => {
              const isRegisteredDetail = /등록.*복용|복용.*등록/.test(detail.label);
              return <div className="v11-extra" key={`${detail.label}-${index}`}><strong>{isRegisteredDetail ? '사용자가 등록한 복용 정보' : detail.label}</strong><p>{decodeEntitiesOnce(detail.text)}</p></div>;
            })}
          </details>
        </article>;
      })}
    </section> : null}

    {report.unverifiedItems.length > 0 ? <section className="v11-card v11-source-card"><details>
      <summary>확인하지 못한 정보</summary>
      <div className="v11-details-body">{report.unverifiedItems.map((item, index) => <p key={`${item.title}-${index}`}><strong>{item.title}</strong> · {item.message} {item.nextStep}</p>)}</div>
    </details></section> : null}

    {cards.sources.length > 0 ? <section className="v11-card v11-source-card"><details>
      <summary>비교 기준과 출처</summary>
      <ul className="v11-source-list">{cards.sources.map(source => {
        const href = safeLink(source.url);
        return <li key={source.id}>{href ? <a href={href} target="_blank" rel="noopener noreferrer">{source.title}</a> : <span>{source.title}</span>}{source.organization ? ` · ${source.organization}` : ''} · {evidenceLabels[source.evidenceLevel] ?? '근거 수준 미확인'}</li>;
      })}</ul>
    </details></section> : null}

    <p className="v11-footer">이 보고서는 참고용이며 진단이나 처방을 대신하지 않아요. 제품 설명서와 의료진의 지시를 우선하세요.</p>
  </div>;
}
