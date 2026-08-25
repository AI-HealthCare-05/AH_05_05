import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router';
import { useSession } from '@/app/SessionContext';
import { createAccount, type Gender } from '@/entities/account';
import { login } from '@/entities/auth';
import { prepareMedicationStateForNewAccount } from '@/entities/medication';
import { ApiError } from '@/shared/api/client';
import { USE_MOCK } from '@/shared/config/env';
import {
  MIN_BIRTH_DATE,
  formatDateInputValue,
  validateBirthDate,
} from '@/shared/lib/birthDate';
import { Button, CheckboxField, GenderRadioGroup, Header, Input } from '@/shared/ui';

type AuthMode = 'login' | 'signup';

export function AuthPage() {
  const navigate = useNavigate();
  const { signIn } = useSession();
  const [mode, setMode] = useState<AuthMode>('login');
  const [recordTerms, setRecordTerms] = useState(false);
  const [aiTerms, setAiTerms] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [birthDate, setBirthDate] = useState('');
  const [gender, setGender] = useState<Gender | ''>('');
  const [birthDateError, setBirthDateError] = useState<string | null>(null);
  const [passwordConfirmError, setPasswordConfirmError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const today = formatDateInputValue(new Date());

  async function complete(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitError(null);

    if (mode === 'signup') {
      if (!recordTerms || !aiTerms || !gender) return;
      const nextBirthDateError = validateBirthDate(birthDate);
      const nextPasswordConfirmError =
        password === passwordConfirm ? null : '비밀번호가 일치하지 않아요.';
      setBirthDateError(nextBirthDateError);
      setPasswordConfirmError(nextPasswordConfirmError);
      if (nextBirthDateError || nextPasswordConfirmError) return;

      if (!USE_MOCK) {
        setSubmitError(
          '실서버 회원가입에는 이름과 전화번호가 필요해 아직 이 화면에서 처리할 수 없어요. 로그인해 주세요.',
        );
        return;
      }
    }

    setSubmitting(true);
    try {
      if (mode === 'signup') {
        await createAccount({ email, password, birthDate, gender: gender as Gender });
        prepareMedicationStateForNewAccount();
      } else {
        await login({ email, password });
      }
      signIn();
      navigate('/home', { replace: true });
    } catch (error: unknown) {
      const fallback =
        mode === 'login'
          ? '로그인하지 못했어요. 다시 시도해주세요.'
          : '회원가입하지 못했어요. 다시 시도해주세요.';
      setSubmitError(
        error instanceof ApiError || error instanceof Error ? error.message : fallback,
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="로그인 · 회원가입" onBack={() => navigate(-1)} />
      <main className="flex flex-1 flex-col px-page-x py-6">
        <div
          className="grid grid-cols-2 rounded-input bg-muted-bg p-1"
          role="group"
          aria-label="인증 방식"
        >
          {(['login', 'signup'] as const).map((item) => {
            const selected = item === mode;
            return (
              <button
                key={item}
                type="button"
                aria-pressed={selected}
                className={`min-h-touch rounded-input text-sm font-bold ${
                  selected ? 'bg-card text-foreground shadow-card' : 'text-muted-foreground'
                }`}
                onClick={() => {
                  setMode(item);
                  setSubmitError(null);
                }}
              >
                {item === 'login' ? '로그인' : '회원가입'}
              </button>
            );
          })}
        </div>

        <div className="mt-8">
          <h1 className="text-2xl font-bold text-foreground">
            {mode === 'login' ? '다시 만나서 반가워요' : '내 복약 기록을 안전하게 보관해요'}
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {mode === 'login'
              ? '로그인하면 저장한 복용약과 영양제를 이어서 볼 수 있어요.'
              : '필수 동의는 각각 내용을 확인하고 선택해 주세요.'}
          </p>
        </div>

        <form className="mt-6 flex flex-1 flex-col gap-4" onSubmit={complete}>
          <Input
            label="이메일"
            type="email"
            inputMode="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
          <Input
            label="비밀번호"
            type="password"
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />

          {mode === 'signup' && (
            <>
              <Input
                label="비밀번호 확인"
                type="password"
                autoComplete="new-password"
                value={passwordConfirm}
                error={passwordConfirmError ?? undefined}
                onChange={(event) => {
                  setPasswordConfirm(event.target.value);
                  setPasswordConfirmError(null);
                }}
                required
              />
              <Input
                label="생년월일"
                type="date"
                min={MIN_BIRTH_DATE}
                max={today}
                value={birthDate}
                error={birthDateError ?? undefined}
                onChange={(event) => {
                  setBirthDate(event.target.value);
                  setBirthDateError(null);
                }}
                required
              />
              <GenderRadioGroup value={gender} onChange={setGender} />
              <fieldset className="mt-2 flex flex-col gap-3">
                <legend className="mb-2 text-base font-bold text-foreground">필수 동의</legend>
                <CheckboxField
                  id="record-terms"
                  checked={recordTerms}
                  onCheckedChange={(checked) => setRecordTerms(checked === true)}
                  label="진료기록 수집 및 이용에 동의해요 (필수)"
                />
                <CheckboxField
                  id="ai-terms"
                  checked={aiTerms}
                  onCheckedChange={(checked) => setAiTerms(checked === true)}
                  label="AI 서비스 이용에 동의해요 (필수)"
                />
              </fieldset>
            </>
          )}

          {submitError && (
            <p role="alert" className="text-sm text-danger-strong">
              {submitError}
            </p>
          )}
          <Button
            type="submit"
            className="mt-auto"
            disabled={submitting || (mode === 'signup' && (!recordTerms || !aiTerms))}
          >
            {submitting
              ? mode === 'login'
                ? '로그인 중...'
                : '가입 중...'
              : mode === 'login'
                ? '로그인'
                : '회원가입 완료'}
          </Button>
        </form>
      </main>
    </div>
  );
}
