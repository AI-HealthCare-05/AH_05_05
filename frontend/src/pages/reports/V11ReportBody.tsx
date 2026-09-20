import { useId, useLayoutEffect, useRef, useState, type ReactElement } from 'react';
import type { CardSource, IntakeReport, LifestyleCard, NutrientTotal } from '@/entities/intake-report/types';
import { NutrientTotals, type NutrientTotalDisplay } from '@/entities/supplement/ui/NutrientTotals';
import { DrawnChevron } from '@/shared/ui/DrawnArrow';
import { safeLink } from './reportViewPrimitives';
import './V11ReportBody.css';

const reportValueFormat = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 2 });

function decodeEntitiesOnce(text: string): string {
  if (typeof document === 'undefined' || !text.includes('&')) return text;
  const decoder = document.createElement('textarea');
  return text.replace(/&(?:#[0-9]+|#[xX][0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]+);/g, token => {
    // Only an entity token, never markup or the whole source string, reaches the parser.
    decoder.innerHTML = token;
    return decoder.value;
  });
}

const BODY_PREVIEW_LIMIT = 200;
const SENTENCE_BOUNDARY_RE = /(?<=[.!?。])(?!\.|(?<=\d\.)(?=\d))\s*/;

// Whitespace-only normalization for dedup keys on text that is already decoded.
function normalizedKey(text: string): string {
  return text.replace(/\s+/g, ' ').trim();
}

function containsGuidanceKey(longer: string, shorter: string): boolean {
  if (!longer.includes(shorter)) return false;
  const escaped = shorter.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`(?<![0-9A-Za-z가-힣])${escaped}(?![0-9A-Za-z가-힣])`, 'u').test(longer);
}

const guidanceWordRe = /[0-9A-Za-z가-힣]+/g;
const guidanceParticleSuffixes = ['이라면', '이라도', '라면', '다면', '하면', '하세요', '하십시오', '해야', '하기', '하는', '할', '하고', '에는', '에서', '으로', '에게', '와', '과', '은', '는', '이', '가', '을', '를', '에', '도', '만', '의', '로', '요'];
const guidanceStopWords = new Set(['있는', '있으면', '있다면', '있', '경우', '때문', '위해', '대해', '대한', '때', '시', '섭취', '복용', '필요', '상담', '전문가', '의사', '약사', '주의', '확인', '하세요', '합니다', '있습니다', '나타날', '나타나면', '수', '것', '및', '또는', '그리고']);
const guidanceNegationRe = /(?:않|없|금지|중단|피하|주의)/u;
const guidanceNumberRe = /\d+(?:[.,]\d+)?\s*(?:mg|g|ml|정|회|일|시간|%|밀리그램|그램)?/giu;
const guidanceActionSignalRe = /(?:상담|확인|중단|피하|복용하|섭취하|주의하|하세요|하십시오)/u;

function guidanceTokens(text: string): Set<string> {
  const tokens = new Set<string>();
  for (const rawToken of text.toLocaleLowerCase().match(guidanceWordRe) ?? []) {
    let token = rawToken;
    for (const suffix of guidanceParticleSuffixes) {
      if (token.endsWith(suffix) && token.length - suffix.length >= 1) {
        token = token.slice(0, -suffix.length);
        break;
      }
    }
    if (!guidanceStopWords.has(token) && token) tokens.add(token);
  }
  return tokens;
}

function nearDuplicateGuidance(left: string, right: string): boolean {
  const leftTokens = guidanceTokens(left);
  const rightTokens = guidanceTokens(right);
  if (Math.min(leftTokens.size, rightTokens.size) < 2) return false;
  if (![...leftTokens].every(token => rightTokens.has(token)) && ![...rightTokens].every(token => leftTokens.has(token))) return false;
  const leftNegations = new Set([...left.matchAll(new RegExp(guidanceNegationRe.source, 'gu'))].map(match => match[0]));
  const rightNegations = new Set([...right.matchAll(new RegExp(guidanceNegationRe.source, 'gu'))].map(match => match[0]));
  if (leftNegations.size !== rightNegations.size || [...leftNegations].some(negation => !rightNegations.has(negation))) return false;
  const leftNumbers = new Set([...left.matchAll(guidanceNumberRe)].map(match => match[0].toLocaleLowerCase()));
  const rightNumbers = new Set([...right.matchAll(guidanceNumberRe)].map(match => match[0].toLocaleLowerCase()));
  if (leftNumbers.size !== rightNumbers.size || [...leftNumbers].some(number => !rightNumbers.has(number))) return false;
  return true;
}

function mergeGuidanceBody(entries: { text: string; isAction: boolean }[]): string[] {
  const merged: string[] = [];
  const keys: string[] = [];
  for (const entry of entries) {
    const text = entry.text.trim();
    const key = normalizedKey(text).toLocaleLowerCase();
    if (!key) continue;
    const duplicateIndex = keys.findIndex((existingKey, index) => key === existingKey || containsGuidanceKey(existingKey, key) || containsGuidanceKey(key, existingKey) || nearDuplicateGuidance(merged[index], text));
    if (duplicateIndex < 0) {
      merged.push(text);
      keys.push(key);
      continue;
    }
    const existing = merged[duplicateIndex];
    const existingTokens = guidanceTokens(existing);
    const newTokens = guidanceTokens(text);
    const actionIsClearer = entry.isAction && guidanceActionSignalRe.test(text) && !guidanceActionSignalRe.test(existing);
    if ([...existingTokens].every(token => newTokens.has(token)) && (actionIsClearer || (entry.isAction && newTokens.size === existingTokens.size) || text.length >= existing.length)) {
      merged[duplicateIndex] = text;
      keys[duplicateIndex] = key;
    }
  }
  return merged;
}

// A paragraph break and a line break are both sentence boundaries, so a body with no
// closing punctuation still yields a bounded preview. Mirrors _guidance_sentences.
function guidanceSentences(paragraphs: string[]): string[] {
  return paragraphs.flatMap(paragraph => (paragraph ?? '').split(/\r?\n/))
    .flatMap(line => line.split(SENTENCE_BOUNDARY_RE))
    .map(sentence => sentence.trim())
    .filter(Boolean);
}

// Only ever cuts between sentences, matching the server's summarize_guidance_body.
// When the first sentence alone exceeds the limit, it is kept whole rather than cut mid-sentence.
function summarizeGuidanceBody(paragraphs: string[], limit: number = BODY_PREVIEW_LIMIT): string | null {
  const sentences = guidanceSentences(paragraphs);
  const joined = sentences.join(' ');
  if (joined.length <= limit) return null;
  let preview = '';
  for (const sentence of sentences) {
    const candidate = preview ? `${preview} ${sentence}`.trim() : sentence;
    if (candidate.length > limit && preview) break;
    preview = candidate;
    if (preview.length >= limit) break;
  }
  return preview || joined;
}

// Groups evidence by (title, organization, link) so a source cited for several
// distinct quotes shows its heading and link once, with each quote as its own bullet.
function groupEvidenceBySource(evidence: CardSource[]): { title: string; organization: string | null; href: string | undefined; quotes: string[] }[] {
  const groups: { title: string; organization: string | null; href: string | undefined; quotes: string[] }[] = [];
  const indexes = new Map<string, number>();
  for (const source of evidence) {
    const quote = source.quote?.trim();
    if (!quote) continue;
    const title = source.title ?? '';
    const organization = source.organization?.trim() || null;
    const href = safeLink(source.url);
    const key = JSON.stringify([title, organization ?? '', href ?? '']);
    const existing = indexes.get(key);
    if (existing === undefined) {
      indexes.set(key, groups.length);
      groups.push({ title, organization, href, quotes: [quote] });
    } else if (!groups[existing].quotes.includes(quote)) {
      groups[existing].quotes.push(quote);
    }
  }
  return groups;
}

function RagEvidence({ sourceIds, sources }: { sourceIds: string[]; sources: CardSource[] }) {
  const evidence = sources.filter(source => sourceIds.includes(source.id) && source.quote && source.chunkId);
  const groups = groupEvidenceBySource(evidence);
  if (!groups.length) return null;
  return <details className="v11-rag-evidence">
    <summary>근거 확인</summary>
    {groups.map((group, index) => <div key={index}>
      {group.href ? <a href={group.href} target="_blank" rel="noopener noreferrer">{group.title}</a> : <span>{group.title}</span>}
      {group.organization ? <span> · {group.organization}</span> : null}
      <ul className="v11-rag-evidence-quotes">{group.quotes.map((quote, quoteIndex) => <li key={quoteIndex}><blockquote>{quote}</blockquote></li>)}</ul>
    </div>)}
  </details>;
}

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

const ingredientDisclaimer = '정확한 제품은 미확정이며, 확인된 성분 공통 안내입니다.';

function GuidanceDescription({ descriptions }: { descriptions: string[] }) {
  const [expanded, setExpanded] = useState(false);
  const textId = useId();
  const preview = summarizeGuidanceBody(descriptions);
  if (preview === null) return <>{descriptions.map((description, index) => <p key={index}>{description}</p>)}</>;
  // The preview is a prefix of the full body, so it is replaced by - never stacked on
  // top of - the full text once expanded. The full text itself is never abridged.
  return <>
    {expanded ? null : <p>{preview}</p>}
    <div id={textId} hidden={!expanded}>{descriptions.map((description, index) => <p key={index}>{description}</p>)}</div>
    <button type="button" className={expanded ? 'v11-collapse-label' : 'v11-expand-label'} aria-expanded={expanded} aria-controls={textId} onClick={() => setExpanded(value => !value)}>
      {expanded ? '접기' : '자세히 펼쳐보기'}<span aria-hidden="true">{expanded ? '▴' : '▾'}</span>
    </button>
  </>;
}

function ProductGuidance({ label, cards, sources }: { label: string; cards: LifestyleCard[]; sources: CardSource[] }) {
  const summaries = cards.map(card => decodeEntitiesOnce(card.summary).trim());
  const hasDisclaimer = summaries.some(summary => summary.startsWith(ingredientDisclaimer));
  const strippedSummaries = summaries.map(summary => summary.startsWith(ingredientDisclaimer)
    ? summary.slice(ingredientDisclaimer.length).trim() : summary);
  const body = mergeGuidanceBody([
    ...cards.flatMap((card, index) => [
      { text: strippedSummaries[index], isAction: false },
      { text: decodeEntitiesOnce(card.action ?? '').replace(/\s+/g, ' ').trim(), isAction: true },
    ]),
  ]);
  const categories = [...new Set(cards.map(card => card.category).filter(Boolean))];
  return <article className="v11-guidance-product" aria-label={decodeEntitiesOnce(label)}>
    <h3 className="v11-guidance-product-title">{decodeEntitiesOnce(label)}</h3>
    <div className="v11-guidance-categories">{categories.map(category => <span className="v11-tag" key={category}>{decodeEntitiesOnce(category)}</span>)}</div>
    <div className="v11-guidance-description">
      {hasDisclaimer ? <p>{ingredientDisclaimer}</p> : null}
      <GuidanceDescription descriptions={body} />
    </div>
    <RagEvidence sourceIds={[...new Set(cards.flatMap(card => card.sourceIds))]} sources={sources} />
  </article>;
}

function nutrientNumber(value: string | null | undefined): number | null {
  if (value == null || value.trim() === '') return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}

function reportNutrientTotal(item: NutrientTotal, index: number): NutrientTotalDisplay {
  const amount = nutrientNumber(item.amount);
  const unit = item.unit?.trim() ?? '';
  const reference = unit && (item.referenceKind === 'RNI' || item.referenceKind === 'AI')
    ? nutrientNumber(item.referenceValue) || null : null;
  const suppliedUpper = unit ? nutrientNumber(item.upperLimitValue) || null : null;
  const upper = suppliedUpper !== null && (reference === null || suppliedUpper >= reference) ? suppliedUpper : null;
  const note = amount === null
    ? '함량 또는 복용량을 확인할 수 없어 합계와 막대를 표시하지 않았어요.'
    : reference === null && upper === null
      ? '비교 기준 없음 · 확인된 합계만 표시했어요.'
      : upper === null ? item.upperLimitNote || '상한 기준을 확인할 수 없어요.' : undefined;
  return {
    nutrientId: `report-${index}`,
    name: decodeEntitiesOnce(item.nutrientName),
    amount,
    unit,
    rni: item.referenceKind === 'RNI' ? reference : null,
    ai: item.referenceKind === 'AI' ? reference : null,
    ul: upper,
    exceeded: amount !== null && upper !== null && amount > upper,
    sourceNames: [...new Set(item.includedProductNames.map(name => decodeEntitiesOnce(name).trim()).filter(Boolean))],
    note,
  };
}

function interactionLabel(evidenceLevel: string, actionLevel: 'WARNING' | 'CHECK' | 'INFORMATION') {
  if (evidenceLevel === 'PUBLIC_GUIDE') return '공개 안내 · 개인 조합 확인 필요';
  if (actionLevel === 'WARNING') return '중요 주의';
  if (actionLevel === 'CHECK') return '복용 전 상담';
  return '확인할 점';
}

function isRegisteredIntakeDetail(label: string): boolean {
  return /(?:등록.*(?:복용|계획)|(?:복용|계획).*등록)/.test(label);
}

export function V11ReportBody({ report }: { report: IntakeReport }) {
  const cards = report.cards;
  if (!cards) return null;
  const medications = report.currentStack.filter(item => item.itemType === 'MEDICATION');
  const supplements = report.currentStack.filter(item => item.itemType === 'SUPPLEMENT');
  const availableMedicines = cards.medications.filter(card => card.hasInformation !== false);
  // Chunk IDs and quotes remain available to individual guidance; only deduplicate the overview.
  const seenSources = new Set<string>();
  const uniqueSources = cards.sources.filter(source => {
    const key = JSON.stringify([source.title, source.organization ?? '', source.url ?? '']);
    if (seenSources.has(key)) return false;
    seenSources.add(key);
    return true;
  });
  const nutrientTotals = report.nutrientTotals.filter(item => (nutrientNumber(item.amount) ?? 0) > 0);
  const sortedInteractions = cards.interactions.slice().sort((a, b) => Number(b.actionLevel === 'WARNING') - Number(a.actionLevel === 'WARNING'));
  const actualCounts = `등록한 복용약 ${report.dataAvailability.activeMedicationCount}종 · 영양제 ${report.dataAvailability.activeSupplementCount}종`;
  const guidanceGroups = new Map<string, { label: string; cards: typeof cards.lifestyle }>();
  for (const card of cards.lifestyle) {
    const ids = [...new Set(card.relatedItemIds)].sort((a, b) => a - b);
    const matchingTypes = new Set(report.currentStack.filter(item => ids.includes(item.itemId)).map(item => item.itemType));
    const explicitType = /^(?:food-drink|driving):\d+$/.test(card.id) ? 'MEDICATION'
      : card.id.startsWith('timing:') ? 'SUPPLEMENT'
      : ids.length === 1 ? /^rag:[^:]+:(medication|supplement):/i.exec(card.id)?.[1]?.toUpperCase() : undefined;
    const type = explicitType ?? (ids.length === 1 && matchingTypes.size === 1 ? [...matchingTypes][0] : undefined);
    const key = JSON.stringify([type ?? '', ids]);
    const items = report.currentStack.filter(item => ids.includes(item.itemId) && (!type || item.itemType === type));
    const ambiguous = !type && ids.some(id => report.currentStack.filter(item => item.itemId === id).length !== 1);
    const label = ambiguous ? '공통 안내' : [...new Set(items.map(item => item.productName))].join(' · ') || '공통 안내';
    const group = guidanceGroups.get(key);
    if (group) group.cards.push(card);
    else guidanceGroups.set(key, { label, cards: [card] });
  }

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
      {availableMedicines.length > 0 ? <a href="#v11-medications">약 정보</a> : null}
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
      <h2 id="v11-lifestyle-title">약·영양제별 주의사항 및 가이드</h2>
      {[...guidanceGroups].map(([key, group]) => <ProductGuidance key={key} label={group.label} cards={group.cards} sources={cards.sources} />)}
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
      <NutrientTotals totals={nutrientTotals.map(reportNutrientTotal)} valueFormat={reportValueFormat} />
      <p className="v11-hint">영양제 합계 기준이며 식사는 제외됩니다. 상한은 섭취 목표가 아닙니다.</p>
    </section> : null}

    {availableMedicines.length > 0 ? <section id="v11-medications" className="v11-card" aria-labelledby="v11-medications-title">
      <h2 id="v11-medications-title">약 정보</h2>
      {availableMedicines.map(card => {
        return <article className="v11-medicine" key={card.itemId}>
          <details className="v11-medicine-disclosure">
            <summary className="v11-medicine-summary">
              <h3>{decodeEntitiesOnce(card.productName)}</h3>
              <span className="v11-medicine-toggle">
                <span className="v11-medicine-open-label">상세 보기</span>
                <span className="v11-medicine-close-label">접기</span>
                <DrawnChevron className="v11-medicine-chevron" />
              </span>
            </summary>
            {card.identityNotice ? <p className="v11-hint">{decodeEntitiesOnce(card.identityNotice)}</p> : null}
            <dl>
              <div><dt>효능</dt><dd>{decodeEntitiesOnce(card.efficacy.text)}</dd></div>
              <div><dt>주의</dt><dd>{decodeEntitiesOnce(card.caution.text)}</dd></div>
              <div><dt>금기</dt><dd>{decodeEntitiesOnce(card.contraindication.text)}</dd></div>
            </dl>
            {card.details.filter(detail => !isRegisteredIntakeDetail(detail.label)).map((detail, index) =>
              <div className="v11-extra" key={`${detail.label}-${index}`}><strong>{detail.label}</strong><p>{decodeEntitiesOnce(detail.text)}</p></div>
            )}
          </details>
        </article>;
      })}
    </section> : null}

    {report.unverifiedItems.length > 0 ? <section className="v11-card v11-source-card"><details>
      <summary>확인하지 못한 정보</summary>
      <div className="v11-details-body">{report.unverifiedItems.map((item, index) => <p key={`${item.title}-${index}`}><strong>{item.title}</strong> · {item.message} {item.nextStep}</p>)}</div>
    </details></section> : null}

    {uniqueSources.length > 0 ? <section className="v11-card v11-source-card"><details>
      <summary>참고 자료 및 출처</summary>
      <ul className="v11-source-list">{uniqueSources.map(source => {
        const href = safeLink(source.url);
        return <li key={source.id}>{href ? <a href={href} target="_blank" rel="noopener noreferrer">{source.title}</a> : <span>{source.title}</span>}{source.organization ? ` · ${source.organization}` : ''}</li>;
      })}</ul>
    </details></section> : null}

    <p className="v11-footer">이 보고서는 참고용이며 진단이나 처방을 대신하지 않아요. 제품 설명서와 의료진의 지시를 우선하세요.</p>
  </div>;
}
