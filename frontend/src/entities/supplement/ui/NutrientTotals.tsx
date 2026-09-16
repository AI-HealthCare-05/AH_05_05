import { Card } from '@/shared/ui/Card';
import { DrawnChevron } from '@/shared/ui/DrawnArrow';
import { evaluateNutrientStandard } from '../standard';
import { compareNutrientTotals } from '../summary';
import type { NutrientTotal } from '../types';
import './NutrientTotals.css';

const numberFormat = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 2 });

export type NutrientTotalDisplay = Omit<NutrientTotal, 'amount'> & {
  amount: number | null;
  note?: string;
};

/** Shared supplement/report presentation; callers supply their own snapshot totals. */
export function NutrientTotals({ totals, showStandards = true, valueFormat = numberFormat }: {
  totals: NutrientTotalDisplay[];
  showStandards?: boolean;
  valueFormat?: Intl.NumberFormat;
}) {
  const ordered = totals.slice().sort((left, right) => {
    if (left.amount === null) return right.amount === null ? 0 : 1;
    if (right.amount === null) return -1;
    return compareNutrientTotals({ ...left, amount: left.amount }, { ...right, amount: right.amount });
  });
  const exceeded = showStandards ? ordered.filter(total => total.exceeded) : [];
  const neutral = showStandards ? ordered.filter(total => !total.exceeded) : ordered;

  return <div className="nutrient-totals flex min-w-0 flex-col gap-3">
    {exceeded.map(total => <NutrientTotalCard key={total.nutrientId} total={total} showStandards={showStandards} valueFormat={valueFormat} />)}
    {neutral.length > 0 ? <Card className="gap-0 overflow-hidden p-0">
      {neutral.map(total => <NutrientTotalCard key={total.nutrientId} total={total} showStandards={showStandards} valueFormat={valueFormat} grouped />)}
    </Card> : null}
  </div>;
}

function NutrientTotalCard({
  total,
  showStandards,
  grouped = false,
  valueFormat,
}: {
  total: NutrientTotalDisplay;
  showStandards: boolean;
  grouped?: boolean;
  valueFormat: Intl.NumberFormat;
}) {
  const knownTotal = total.amount === null ? null : { ...total, amount: total.amount };
  const evaluation = knownTotal ? evaluateNutrientStandard(knownTotal) : null;
  const isOverUpperLimit = showStandards && evaluation?.status === 'over-upper-limit';
  const statusLabel = showStandards && knownTotal && evaluation ? standardStatusLabel(knownTotal, evaluation) : null;
  const hasStatus = statusLabel !== null;

  const content = (
    <div className="flex flex-col gap-2">
      <div className="flex flex-col gap-0">
        <div data-testid="nutrient-total-header" className="relative mx-1 min-h-7">
          <div
            data-testid="nutrient-total-summary"
            className={`nutrient-total-summary flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1 ${
              hasStatus ? 'max-w-[60%]' : 'max-w-full'
            }`}
          >
            <h3 className="[overflow-wrap:anywhere] text-lg font-bold text-foreground">
              {total.name}
            </h3>
            <strong
              className={`text-lg font-bold tnum ${
                isOverUpperLimit ? 'text-danger-strong' : 'text-foreground'
              }`}
            >
              {total.amount === null ? '미확인' : valueFormat.format(total.amount)}
            </strong>
            <span className="text-unit text-muted-foreground">{total.unit}</span>
          </div>
          {statusLabel !== null && knownTotal && evaluation && (
            <StandardStatus total={knownTotal} evaluation={evaluation} label={statusLabel} />
          )}
        </div>

        {showStandards && knownTotal && evaluation && (evaluation.base !== null || total.ul !== null) && (
          <NutrientRangeBar total={knownTotal} valueFormat={valueFormat} />
        )}
      </div>

      {total.note ? <p className="text-xs text-muted-foreground [overflow-wrap:anywhere]">{total.note}</p> : null}
      <details className="group text-sm text-muted-foreground">
        <summary className="flex min-h-touch cursor-pointer list-none items-center justify-between gap-3 rounded-control py-1 font-bold text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
          <span>성분 포함 제품 {total.sourceNames.length}개</span>
          <DrawnChevron
            aria-hidden
            direction="down"
            className="size-5 shrink-0 text-disabled-foreground transition-transform group-open:rotate-180"
          />
        </summary>
        <ul className="flex flex-col gap-1 border-t border-border pt-2">
          {total.sourceNames.map((sourceName) => (
            <li key={sourceName} className="[overflow-wrap:anywhere]">
              {sourceName}
            </li>
          ))}
        </ul>
      </details>
    </div>
  );

  if (grouped) {
    return (
      <article
        aria-label={`${total.name} 성분 합계`}
        className="flex flex-col gap-4 border-t border-border p-4 first:border-t-0"
      >
        {content}
      </article>
    );
  }

  return (
    <article aria-label={`${total.name} 성분 합계`}>
      <Card className="gap-4 p-4">
        {content}
      </Card>
    </article>
  );
}

function standardStatusLabel(
  total: NutrientTotal,
  evaluation: ReturnType<typeof evaluateNutrientStandard>,
): string | null {
  const baseLabel = evaluation.baseKind === 'ai' ? '충분섭취량' : '권장량';
  if (evaluation.status === 'over-upper-limit') {
    return '상한 초과';
  }
  if (evaluation.status === 'below-base' && evaluation.percentOfBase !== null) {
    return `${baseLabel}의 ${numberFormat.format(evaluation.percentOfBase)}%예요`;
  }
  if (evaluation.status === 'recommended') {
    return (
      total.ul === null && evaluation.percentOfBase !== null
        ? `${baseLabel}의 ${numberFormat.format(evaluation.percentOfBase)}%예요`
        : '권장 범위예요'
    );
  }
  return null;
}

function StandardStatus({
  total,
  evaluation,
  label,
}: {
  total: NutrientTotal;
  evaluation: ReturnType<typeof evaluateNutrientStandard>;
  label: string;
}) {
  const upperLimitPosition = rangePositions(total, evaluation.base).upper;
  return (
    <p
      data-nutrient-status
      className={`absolute top-0 whitespace-nowrap text-right text-sm ${
        upperLimitPosition === null ? 'right-0' : '-translate-x-1/2'
      } ${evaluation.status === 'over-upper-limit' ? 'font-bold text-danger-strong' : 'text-muted-foreground'}`}
      style={upperLimitPosition === null ? undefined : { left: `${upperLimitPosition}%` }}
    >
      {label}
    </p>
  );
}

function NutrientRangeBar({ total, valueFormat }: { total: NutrientTotal; valueFormat: Intl.NumberFormat }) {
  const evaluation = evaluateNutrientStandard(total);
  if (total.ul === null && evaluation.base === null) return null;

  const positions = rangePositions(total, evaluation.base);
  const upperLimit = total.ul;
  const hasUpperLimit = upperLimit !== null;
  const labelsAreClose =
    positions.base !== null &&
    positions.upper !== null &&
    Math.abs(positions.upper - positions.base) < 20;
  const fillColor =
    evaluation.status === 'below-base'
      ? 'bg-warning'
      : evaluation.status === 'over-upper-limit'
        ? 'bg-danger'
        : 'bg-primary';
  const markerColor =
    evaluation.status === 'below-base'
      ? 'bg-warning-strong'
      : evaluation.status === 'over-upper-limit'
        ? 'bg-danger-strong'
        : 'bg-primary-strong';

  return (
    <div
      data-nutrient-range
      data-threshold-labels
      aria-hidden={hasUpperLimit ? undefined : true}
      className="relative mx-1 h-14"
    >
      {positions.base !== null && evaluation.base !== null && (
        <div
          data-threshold-label="base"
          className={`absolute top-0 grid h-14 grid-rows-[1rem_1.5rem_1rem] whitespace-nowrap text-xs text-muted-foreground ${
            labelsAreClose ? '-translate-x-full text-left' : '-translate-x-1/2 text-center'
          }`}
          style={{ left: `${clampThresholdLabel(positions.base)}%` }}
        >
          <span className="row-start-1">
            {evaluation.baseKind === 'ai' ? '충분' : '권장'}
          </span>
          <span className="row-start-3 tnum">{valueFormat.format(evaluation.base)}</span>
        </div>
      )}
      {positions.upper !== null && upperLimit !== null && (
        <div
          data-threshold-label="upper-limit"
          className={`absolute top-0 grid h-14 grid-rows-[1rem_1.5rem_1rem] whitespace-nowrap text-xs text-muted-foreground ${
            labelsAreClose ? 'text-right' : '-translate-x-1/2 text-center'
          }`}
          style={{ left: `${clampThresholdLabel(positions.upper)}%` }}
        >
          <span className="row-start-1">상한</span>
          <span className="row-start-3 tnum">{valueFormat.format(upperLimit)}</span>
        </div>
      )}
      <div
        role={hasUpperLimit ? 'meter' : undefined}
        aria-label={hasUpperLimit ? `${total.name} 섭취기준 위치` : undefined}
        aria-valuemin={hasUpperLimit ? 0 : undefined}
        aria-valuenow={upperLimit !== null ? Math.min(total.amount, upperLimit) : undefined}
        aria-valuemax={upperLimit ?? undefined}
        aria-valuetext={
          hasUpperLimit ? `${valueFormat.format(total.amount)}${total.unit}` : undefined
        }
        className="absolute inset-x-0 top-4 h-5"
      >
        <div
          data-range-track
          className="absolute inset-x-0 top-2 h-2 rounded-pill bg-muted-bg"
        >
          <div
            data-range-fill
            className={`h-full rounded-pill ${fillColor}`}
            style={{ width: `${positions.marker}%` }}
          />
        </div>
        {positions.base !== null && (
          <span
            data-threshold="base"
            aria-hidden
            className="absolute top-1 h-4 w-0.5 bg-muted-foreground"
            style={{ left: `${positions.base}%` }}
          />
        )}
        {positions.upper !== null && (
          <span
            data-threshold="upper-limit"
            aria-hidden
            className="absolute top-1 h-4 w-0.5 bg-muted-foreground"
            style={{ left: `${positions.upper}%` }}
          />
        )}
        <span
          data-range-marker
          aria-hidden
          className={`absolute top-1 size-4 -translate-x-1/2 rounded-pill border-2 border-card ${markerColor}`}
          style={{ left: `${positions.marker}%` }}
        />
      </div>
    </div>
  );
}

function clampThresholdLabel(position: number): number {
  return Math.max(8, Math.min(92, position));
}

function rangePositions(total: NutrientTotal, base: number | null) {
  if (total.ul === null) {
    if (base === null || base === 0) return { base: null, upper: null, marker: 0 };
    return {
      base: 70,
      upper: null,
      marker: Math.max(0, Math.min(100, (total.amount / base) * 70)),
    };
  }
  const upper = 88;
  const marker =
    total.amount > total.ul
      ? 100
      : Math.max(0, Math.min(upper, (total.amount / total.ul) * upper));
  const basePosition =
    base === null ? null : Math.max(4, Math.min(upper - 4, (base / total.ul) * upper));
  return { base: basePosition, upper, marker };
}
