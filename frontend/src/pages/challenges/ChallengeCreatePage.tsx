import { useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';
import { useChallengeMock, type ChallengeFrequency } from '@/features/challenges';
import { Button, Input } from '@/shared/ui';

type FrequencyMode = ChallengeFrequency['type'];

function numberInRange(raw: string, min: number, max: number, fallback: number) {
  const parsed = Number(raw);
  return raw.trim() && Number.isFinite(parsed)
    ? Math.min(max, Math.max(min, Math.round(parsed)))
    : fallback;
}

function addDays(dateText: string, days: number) {
  const date = new Date(`${dateText}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function koreanDate(dateText: string) {
  const [, month, day] = dateText.split('-').map(Number);
  return `${month}월 ${day}일`;
}

export function ChallengeCreatePage() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { createPersonal, demoToday } = useChallengeMock();
  const base = pathname.startsWith('/dev/') ? '/dev/challenges' : '/challenges';
  const [title, setTitle] = useState('');
  const [taskLabel, setTaskLabel] = useState('');
  const [startDate, setStartDate] = useState(demoToday);
  const [frequencyMode, setFrequencyMode] = useState<FrequencyMode>('daily');
  const [durationDays, setDurationDays] = useState(7);
  const [showCustomDays, setShowCustomDays] = useState(false);
  const [customDaysInput, setCustomDaysInput] = useState('7');
  const [targetDaysInput, setTargetDaysInput] = useState('3');
  const [durationWeeks, setDurationWeeks] = useState(4);
  const [showCustomWeeks, setShowCustomWeeks] = useState(false);
  const [customWeeksInput, setCustomWeeksInput] = useState('4');
  const [submitted, setSubmitted] = useState(false);

  const titleError = submitted && !title.trim() ? '목표 이름을 입력해주세요.' : undefined;
  const taskError = submitted && !taskLabel.trim() ? '달성항목을 입력해주세요.' : undefined;
  const effectiveDays = showCustomDays
    ? numberInRange(customDaysInput, 1, 365, durationDays)
    : durationDays;
  const targetDaysPerWeek = numberInRange(targetDaysInput, 1, 7, 3);
  const effectiveWeeks = showCustomWeeks
    ? numberInRange(customWeeksInput, 1, 52, durationWeeks)
    : durationWeeks;
  const totalDays = frequencyMode === 'daily' ? effectiveDays : effectiveWeeks * 7;
  const endDate = startDate ? addDays(startDate, totalDays - 1) : '';

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    setSubmitted(true);
    if (!title.trim() || !taskLabel.trim()) return;

    const frequency: ChallengeFrequency =
      frequencyMode === 'daily'
        ? { type: 'daily', durationDays: effectiveDays }
        : { type: 'weekly', targetDaysPerWeek, durationWeeks: effectiveWeeks };
    const participationId = createPersonal({
      title: title.trim(),
      description: taskLabel.trim(),
      taskLabel: taskLabel.trim(),
      frequency,
      startDate,
    });
    navigate(`${base}/participations/${participationId}`);
  };

  return (
    <main className="min-h-full px-5 py-5">
    <form onSubmit={handleSubmit} className="flex min-h-full flex-col gap-4">
      <div className="space-y-1">
        <h1 className="text-[22px] font-bold leading-8 text-foreground">나만의 챌린지 만들기</h1>
        <p className="text-sm text-muted-foreground">내가 할 수 있는 작은 목표부터</p>
      </div>

      <Input
        label="목표 이름"
        value={title}
        onChange={(event) => setTitle(event.target.value)}
        placeholder="예: 나를 위한 걷기"
        error={titleError}
      />
      <Input
        label="달성항목"
        value={taskLabel}
        onChange={(event) => setTaskLabel(event.target.value)}
        placeholder="예: 하루 30분 걷기"
        error={taskError}
      />
      <Input
        label="시작 날짜"
        type="date"
        value={startDate}
        min={demoToday}
        onChange={(event) => setStartDate(event.target.value)}
        required
        hint="선택한 날부터 챌린지가 시작돼요."
      />

      <fieldset className="flex flex-col gap-2">
        <legend className="mb-2 text-sm font-bold text-foreground">얼마나 자주 할까요?</legend>
        <div className="grid grid-cols-2 gap-2">
          <Button
            variant={frequencyMode === 'daily' ? 'primary' : 'secondary'}
            onClick={() => setFrequencyMode('daily')}
          >
            매일
          </Button>
          <Button
            variant={frequencyMode === 'weekly' ? 'primary' : 'secondary'}
            onClick={() => setFrequencyMode('weekly')}
          >
            주 몇 회
          </Button>
        </div>
      </fieldset>

      {frequencyMode === 'daily' ? (
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-2 text-sm font-bold text-foreground">얼마 동안 할까요?</legend>
          <div className="grid grid-cols-4 gap-2">
            {[7, 14, 30].map((days) => (
              <Button
                key={days}
                variant={!showCustomDays && durationDays === days ? 'primary' : 'secondary'}
                onClick={() => {
                  setDurationDays(days);
                  setShowCustomDays(false);
                }}
              >
                {days}일
              </Button>
            ))}
            <Button
              variant={showCustomDays ? 'primary' : 'secondary'}
              onClick={() => setShowCustomDays(true)}
              className="px-2"
            >
              직접 입력
            </Button>
          </div>
          {showCustomDays && (
            <Input
              label="수행 일 수"
              type="number"
              min={1}
              max={365}
              value={customDaysInput}
              onChange={(event) => setCustomDaysInput(event.target.value)}
              onBlur={() => setCustomDaysInput(String(effectiveDays))}
              inputMode="numeric"
            />
          )}
        </fieldset>
      ) : (
        <fieldset className="flex flex-col gap-3">
          <legend className="text-sm font-bold text-foreground">주간 목표</legend>
          <div className="flex items-end gap-2">
            <Button
              variant="secondary"
              fullWidth={false}
              aria-label="일주일 목표 횟수 줄이기"
              onClick={() => setTargetDaysInput(String(Math.max(1, targetDaysPerWeek - 1)))}
              className="w-12"
            >
              −
            </Button>
            <Input
              label="일주일 목표 횟수"
              type="number"
              min={1}
              max={7}
              value={targetDaysInput}
              onChange={(event) => setTargetDaysInput(event.target.value)}
              onBlur={() => setTargetDaysInput(String(targetDaysPerWeek))}
              inputMode="numeric"
              className="flex-1"
            />
            <Button
              variant="secondary"
              fullWidth={false}
              aria-label="일주일 목표 횟수 늘리기"
              onClick={() => setTargetDaysInput(String(Math.min(7, targetDaysPerWeek + 1)))}
              className="w-12"
            >
              ＋
            </Button>
          </div>
          <div className="grid grid-cols-4 gap-2">
            {[1, 2, 4].map((weeks) => (
              <Button
                key={weeks}
                variant={!showCustomWeeks && durationWeeks === weeks ? 'primary' : 'secondary'}
                onClick={() => {
                  setDurationWeeks(weeks);
                  setShowCustomWeeks(false);
                }}
              >
                {weeks}주
              </Button>
            ))}
            <Button
              variant={showCustomWeeks ? 'primary' : 'secondary'}
              onClick={() => setShowCustomWeeks(true)}
              className="px-2"
            >
              직접 입력
            </Button>
          </div>
          {showCustomWeeks && (
            <Input
              label="수행 주 수"
              type="number"
              min={1}
              max={52}
              value={customWeeksInput}
              onChange={(event) => setCustomWeeksInput(event.target.value)}
              onBlur={() => setCustomWeeksInput(String(effectiveWeeks))}
              inputMode="numeric"
            />
          )}
          <p className="text-xs text-muted-foreground">매주 서로 다른 {targetDaysPerWeek}일 인증</p>
          <p className="text-xs text-muted-foreground">하루 최대 1회 · 초과 인증은 이월되지 않아요.</p>
        </fieldset>
      )}

      {startDate && endDate && (
        <p className="text-xs text-muted-foreground">
          {koreanDate(startDate)}부터 {koreanDate(endDate)}까지 진행해요. {frequencyMode === 'weekly' ? `${effectiveWeeks}주 동안 진행해요.` : ''}
        </p>
      )}

      <div className="mt-auto flex flex-col gap-2 pt-4">
        <Button type="submit">챌린지 만들기</Button>
        <Link to={`${base}/tailored`} className="min-h-touch py-3 text-center text-sm font-bold text-primary">
          맞춤 챌린지로 돌아가기
        </Link>
      </div>
    </form>
    </main>
  );
}
