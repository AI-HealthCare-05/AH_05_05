import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router';
import { useSession } from '@/app/SessionContext';
import { Button, CheckboxField, Header, Input } from '@/shared/ui';

type AuthMode = 'login' | 'signup';

export function AuthPage() {
  const navigate = useNavigate();
  const { signIn } = useSession();
  const [mode, setMode] = useState<AuthMode>('login');
  const [recordTerms, setRecordTerms] = useState(false);
  const [aiTerms, setAiTerms] = useState(false);

  function complete(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (mode === 'signup' && (!recordTerms || !aiTerms)) return;
    signIn();
    navigate('/home', { replace: true });
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
          <Input label="이메일" type="email" inputMode="email" autoComplete="email" required />
          <Input
            label="비밀번호"
            type="password"
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
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

          <Button
            type="submit"
            className="mt-auto"
            disabled={mode === 'signup' && (!recordTerms || !aiTerms)}
          >
            {mode === 'login' ? '로그인' : '회원가입 완료'}
          </Button>
        </form>
      </main>
    </div>
  );
}
