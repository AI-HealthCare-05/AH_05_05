import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router';
import { useSession } from '@/app/SessionContext';
import { login } from '@/entities/auth';
import { prepareMedicationStateForNewAccount } from '@/entities/medication';
import { ApiError } from '@/shared/api/client';
import { USE_MOCK } from '@/shared/config/env';
import { Button, CheckboxField, Header, Input } from '@/shared/ui';

type AuthMode = 'login' | 'signup';

export function AuthPage() {
  const navigate = useNavigate();
  const { signIn } = useSession();
  const [mode, setMode] = useState<AuthMode>('login');
  const [recordTerms, setRecordTerms] = useState(false);
  const [aiTerms, setAiTerms] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function complete(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (mode === 'signup' && (!recordTerms || !aiTerms)) return;
    setSubmitError(null);
    if (mode === 'signup') {
      if (!USE_MOCK) {
        setSubmitError('실서버 회원가입에는 이름과 전화번호가 필요해 아직 이 화면에서 처리할 수 없어요. 로그인해 주세요.');
        return;
      }
      prepareMedicationStateForNewAccount();
      signIn();
      navigate('/home', { replace: true });
      return;
    }
    setSubmitting(true);
    try {
      await login({ email, password });
      signIn();
      navigate('/home', { replace: true });
    } catch (error: unknown) {
      setSubmitError(error instanceof ApiError || error instanceof Error ? error.message : '로그인하지 못했어요. 다시 시도해주세요.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="로그인 · 회원가입" onBack={() => navigate(-1)} />
      <main className="flex flex-1 flex-col px-page-x py-6">
        <div className="grid grid-cols-2 rounded-input bg-muted-bg p-1" role="group" aria-label="인증 방식">
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
                onClick={() => setMode(item)}
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
          <Input label="이메일" type="email" inputMode="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          <Input
            label="비밀번호"
            type="password"
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />

          {mode === 'signup' && (
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
          )}

          {submitError && <p role="alert" className="text-sm text-danger-strong">{submitError}</p>}
          <Button
            type="submit"
            className="mt-auto"
            disabled={submitting || (mode === 'signup' && (!recordTerms || !aiTerms))}
          >
            {submitting ? '로그인 중...' : mode === 'login' ? '로그인' : '회원가입 완료'}
          </Button>
        </form>
      </main>
    </div>
  );
}
