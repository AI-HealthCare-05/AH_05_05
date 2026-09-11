import type { ReactElement } from 'react';
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
  if (forceOpen || decoded.length <= 160) return <p>{decoded}</p>;
  return <details className="v11-collapsible">
    <summary>
      <span className="v11-collapsible-preview">{decoded}</span>
      <span className="v11-expand-label">자세히 펼쳐보기<span aria-hidden="true">▾</span></span>
      <span className="v11-collapse-label">접기<span aria-hidden="true">▴</span></span>
    </summary>
    <p className="v11-collapsible-full">{decoded}</p>
  </details>;
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

function nutrientWidth(percent: number): number {
  if (!Number.isFinite(percent) || percent <= 0) return 0;
  if (percent <= 100) return percent * 0.75;
  return Math.min(100, 75 + (percent - 100) * (25 / 30));
}

function NutrientBar({ item }: { item: NutrientTotal }) {
  const percent = item.referencePercent === null || item.referencePercent === undefined ? Number.NaN : Number(item.referencePercent);
  const comparable = item.amount !== null && item.amount !== undefined && item.amount !== '' && item.referenceValue !== null && item.referenceValue !== undefined && item.referenceValue !== '' && Number.isFinite(percent);
  const amount = item.amount && item.unit ? `${item.amount}${item.unit}` : item.dailyTotal;
  const reference = item.referenceKind === 'RNI' ? '권장섭취량' : item.referenceKind === 'AI' ? '충분섭취량' : '비교 기준';
  return <article className="v11-nutrient">
    <div className="v11-row-head"><h3>{item.nutrientName} <span>{amount}</span></h3><strong>{comparable ? `${item.referencePercent}%` : '미확인'}</strong></div>
    {comparable ? <>
      <div className="v11-track" role="img" aria-label={`${item.nutrientName} ${item.referencePercent}%`}><span style={{ width: `${nutrientWidth(percent)}%` }} /></div>
      <div className="v11-scale" aria-hidden="true"><span>0%</span><span>100%</span><span>130%+</span></div>
      <p className="v11-reference">{reference} {item.referenceValue}{item.unit ?? ''} 기준 · 확인된 합계 {amount}</p>
    </> : <p className="v11-reference">비교 기준 또는 함량이 미확인이라 막대를 표시하지 않았어요.</p>}
    {item.unknownProductNames?.length ? item.unknownProductNames.length > 1
      ? <details><summary>확인 필요 제품 {item.unknownProductNames.length}종</summary><p className="v11-reference">{item.unknownProductNames.join(' · ')}</p></details>
      : <p className="v11-reference">확인 필요 제품 · {item.unknownProductNames[0]}</p> : null}
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
  const supplements = report.currentStack.filter(item => item.itemType === 'SUPPLEMENT');
  const registeredByMedicationId = new Map(report.currentStack.filter(item => item.itemType === 'MEDICATION').map(item => [item.itemId, item.registeredIntakeInfo]));
  const sortedInteractions = cards.interactions.slice().sort((a, b) => Number(b.actionLevel === 'WARNING') - Number(a.actionLevel === 'WARNING'));
  const actualCounts = `등록한 복용약 ${report.dataAvailability.activeMedicationCount}종 · 영양제 ${report.dataAvailability.activeSupplementCount}종`;

  return <div className="v11-report">
    <section className="v11-hero" aria-label="리포트 개요">
      <span className="v11-eyebrow">약·영양제 리포트</span>
      <h1>먼저 확인할 것부터<br />정리했어요</h1>
      {report.profileLabel ? <p className="v11-meta">{report.profileLabel}</p> : null}
      <p className="v11-meta">{actualCounts}</p>
      {report.basisNote ? <p className="v11-notice">{report.basisNote}</p> : null}
    </section>

    {report.reportStatus === 'PARTIAL' ? <p role="status" className="v11-status">일부 정보를 확인하지 못했어요. 확인 가능한 정보만 담았으며, 정보 부족은 안전하다는 뜻이 아니에요.</p> : null}

    <nav className="v11-anchor-chips" aria-label="리포트 바로가기">
      <a href="#v11-interactions">함께 확인</a>
      {cards.overlaps.length > 0 ? <a href="#v11-overlaps">영양제 중복</a> : null}
      {cards.lifestyle.length > 0 ? <a href="#v11-lifestyle">생활습관</a> : null}
      {report.nutrientTotals.length > 0 ? <a href="#v11-nutrients">영양소</a> : null}
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

    {report.nutrientTotals.length > 0 ? <section id="v11-nutrients" className="v11-card" aria-labelledby="v11-nutrients-title">
      <h2 id="v11-nutrients-title">영양소는 얼마나 겹칠까요?</h2>
      <p className="v11-hint">식단은 포함하지 않으며, 확인되지 않은 함량은 0으로 계산하지 않았어요.</p>
      {report.nutrientTotals.map((item, index) => <NutrientBar key={`${item.nutrientName}-${index}`} item={item} />)}
      <p className="v11-hint">100%는 권장·충분섭취량 비교 기준이며, 이 비율만으로 부족·과다를 판단하지 않아요.</p>
    </section> : null}

    {cards.medications.length > 0 ? <section id="v11-medications" className="v11-card" aria-labelledby="v11-medications-title">
      <h2 id="v11-medications-title">약 정보</h2>
      {cards.medications.map(card => {
        const registeredIntake = registeredByMedicationId.get(card.itemId)?.trim();
        const includesRegisteredIntake = card.details.some(detail => /등록.*복용|복용.*등록/.test(detail.label));
        return <article className="v11-medicine" key={card.itemId}>
          <h3>{card.productName}</h3>
          <dl>
            <div><dt>효능</dt><dd>{decodeEntitiesOnce(card.efficacy.text)}</dd></div>
            <div><dt>주의</dt><dd>{decodeEntitiesOnce(card.caution.text)}</dd></div>
            <div><dt>금기</dt><dd>{decodeEntitiesOnce(card.contraindication.text)}</dd></div>
          </dl>
          {(registeredIntake || card.details.length > 0) ? <details>
            <summary>약 정보 더 보기</summary>
            {registeredIntake && !includesRegisteredIntake ? <div className="v11-extra"><strong>사용자가 등록한 복용 정보</strong><p>{registeredIntake}</p></div> : null}
            {card.details.map((detail, index) => {
              const isRegisteredDetail = /등록.*복용|복용.*등록/.test(detail.label);
              return <div className="v11-extra" key={`${detail.label}-${index}`}><strong>{isRegisteredDetail ? '사용자가 등록한 복용 정보' : detail.label}</strong><p>{decodeEntitiesOnce(detail.text)}</p></div>;
            })}
          </details> : null}
        </article>;
      })}
    </section> : null}

    {supplements.length > 0 ? <section className="v11-card" aria-labelledby="v11-supplements-title">
      <h2 id="v11-supplements-title">등록한 영양제 {supplements.length}종</h2>
      <ul className="v11-supplements">{supplements.map(item => <li key={item.itemId}><h3>{item.productName}</h3><p>사용자가 등록한 복용 정보 · {item.registeredIntakeInfo || '미등록'}</p></li>)}</ul>
    </section> : null}

    {cards.originalTexts?.length ? <section id="v11-originals" className="v11-card"><details>
      <summary>정리 전 원문 보기</summary>
      <div className="v11-details-body">{cards.originalTexts.map(original => <p key={original.key}>
        <strong>{original.label}</strong><br />{decodeEntitiesOnce(original.text)}
      </p>)}</div>
    </details></section> : null}

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
