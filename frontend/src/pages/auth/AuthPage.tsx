import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Eye, EyeOff } from 'lucide-react';
import { Link, useLocation, useNavigate } from 'react-router';
import { useSession } from '@/app/SessionContext';
import { createAccount, type Gender } from '@/entities/account';
import { login } from '@/entities/auth';
import { prepareMedicationStateForNewAccount } from '@/entities/medication';
import { ApiError } from '@/shared/api/client';
import {
  MIN_BIRTH_DATE,
  formatDateInputValue,
  validateBirthDate,
} from '@/shared/lib/birthDate';
import { EMAIL_INPUT_PATTERN, EMAIL_MAX_LENGTH, sanitizeEmailInput } from '@/shared/lib/email';
import { NAME_MAX_LENGTH, sanitizeNameInput, validateName } from '@/shared/lib/name';
import { PASSWORD_MAX_LENGTH } from '@/shared/lib/password';
import {
  PHONE_NUMBER_MAX_LENGTH,
  formatPhoneNumberInput,
  validatePhoneNumber,
} from '@/shared/lib/phoneNumber';
import { Button, CheckboxField, GenderRadioGroup, Header, Input } from '@/shared/ui';

type AuthMode = 'login' | 'signup';
type SignupStep = 1 | 2 | 3 | 4;

const VERIFICATION_CODE_LENGTH = 6;

/** 서버가 오류 본문을 못 줄 때만 씁니다. 평소에는 서버 message 를 그대로 띄웁니다. */
const LOGIN_FALLBACK_ERROR = '로그인하지 못했어요. 잠시 후 다시 시도해주세요.';

const STEP_COPY: Record<SignupStep, { title: string; description?: string }> = {
  1: { title: '이메일을 알려주세요', description: '인증 메일을 보내드릴 주소예요.' },
  2: { title: '메일함을 확인해주세요' },
  3: { title: '비밀번호를 정해주세요', description: '로그인할 때 쓸 비밀번호예요.' },
  4: { title: '마지막이에요' },
};

export function AuthPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { signIn } = useSession();
  const emailInputRef = useRef<HTMLInputElement>(null);
  const [mode, setMode] = useState<AuthMode>('login');
  const [signupStep, setSignupStep] = useState<SignupStep>(1);
  const [verificationCode, setVerificationCode] = useState('');
  const [verificationSeconds, setVerificationSeconds] = useState(5 * 60);
  const [recordTerms, setRecordTerms] = useState(false);
  const [aiTerms, setAiTerms] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showPasswordConfirm, setShowPasswordConfirm] = useState(false);
  const [name, setName] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [birthDate, setBirthDate] = useState('');
  const [gender, setGender] = useState<Gender | ''>('');
  const [emailError, setEmailError] = useState<string | null>(null);
  const [birthDateError, setBirthDateError] = useState<string | null>(null);
  const [passwordConfirmError, setPasswordConfirmError] = useState<string | null>(null);
  const [nameError, setNameError] = useState<string | null>(null);
  const [phoneNumberError, setPhoneNumberError] = useState<string | null>(null);
  const [loginError, setLoginError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const today = formatDateInputValue(new Date());

  useEffect(() => {
    if (mode === 'signup' && signupStep === 1) {
      emailInputRef.current?.setCustomValidity(emailError ?? '');
    }
  }, [emailError, mode, signupStep]);

  useEffect(() => {
    if (mode !== 'signup' || signupStep !== 2) return;
    setVerificationSeconds(5 * 60);
    const timer = window.setInterval(() => {
      setVerificationSeconds((seconds) => Math.max(0, seconds - 1));
    }, 1_000);
    return () => window.clearInterval(timer);
  }, [mode, signupStep]);

  /** 탭을 옮길 때는 가입 흐름을 새로 시작합니다. 같은 탭을 다시 누르는 경우는 보존합니다. */
  function resetAuthForm() {
    setSignupStep(1);
    setVerificationCode('');
    setEmail('');
    setPassword('');
    setPasswordConfirm('');
    setShowPassword(false);
    setShowPasswordConfirm(false);
    setName('');
    setPhoneNumber('');
    setBirthDate('');
    setGender('');
    setRecordTerms(false);
    setAiTerms(false);
    setEmailError(null);
    setBirthDateError(null);
    setPasswordConfirmError(null);
    setNameError(null);
    setPhoneNumberError(null);
    setLoginError(null);
    emailInputRef.current?.setCustomValidity('');
  }

  function applyEmailInput(input: HTMLInputElement) {
    const typed = input.value;
    const sanitized = sanitizeEmailInput(typed);
    if (sanitized !== typed) input.value = sanitized;
    setEmailError(sanitized === typed ? null : '이메일은 영문, 숫자와 기호만 입력할 수 있어요.');
    setEmail(sanitized);
  }

  function applyNameInput(input: HTMLInputElement) {
    const typed = input.value;
    const normalized = typed.normalize('NFC');
    const sanitized = sanitizeNameInput(typed);
    if (sanitized !== typed) input.value = sanitized;
    setName(sanitized);
    setNameError(
      sanitized === normalized ? null : '이름에는 숫자, 공백, 특수문자를 쓸 수 없어요.',
    );
  }

  function goBack() {
    if (mode === 'signup' && signupStep > 1) {
      setSignupStep((step) => (step - 1) as SignupStep);
      setLoginError(null);
      return;
    }
    navigate(-1);
  }

  async function complete(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoginError(null);
    emailInputRef.current?.setCustomValidity('');

    if (mode === 'login') {
      setSaving(true);
      try {
        // 토큰은 login() 안에서 메모리에만 심습니다. 새로고침하면 사라집니다(유저플로우 v4).
        await login({ email: email.trim(), password });
      } catch (error) {
        // 서버 문구를 그대로 씁니다. 계정 없음·비밀번호 불일치·정지·탈퇴가 모두 같은
        // 400 응답이라 여기서 갈라볼 것이 없습니다(#196).
        setLoginError(error instanceof ApiError ? error.message : LOGIN_FALLBACK_ERROR);
        return;
      } finally {
        setSaving(false);
      }

      signIn(email);
      const requestedPath = (location.state as { from?: unknown } | null)?.from;
      const destination =
        typeof requestedPath === 'string' &&
        requestedPath.startsWith('/') &&
        !requestedPath.startsWith('//') &&
        requestedPath !== '/login'
          ? requestedPath
          : '/home';
      navigate(destination, { replace: true });
      return;
    }

    if (signupStep === 1) {
      setSignupStep(2);
      return;
    }

    if (signupStep === 2) {
      if (!/^\d{6}$/.test(verificationCode)) return;
      setSignupStep(3);
      return;
    }

    if (signupStep === 3) {
      const nextPasswordConfirmError =
        password === passwordConfirm ? null : '비밀번호가 일치하지 않아요.';
      setPasswordConfirmError(nextPasswordConfirmError);
      if (nextPasswordConfirmError) return;
      setSignupStep(4);
      return;
    }

    if (!recordTerms || !aiTerms || !gender) return;
    const nextBirthDateError = validateBirthDate(birthDate);
    const nextNameError = validateName(name);
    const nextPhoneNumberError = validatePhoneNumber(phoneNumber);
    setBirthDateError(nextBirthDateError);
    setNameError(nextNameError);
    setPhoneNumberError(nextPhoneNumberError);
    if (nextBirthDateError || nextNameError || nextPhoneNumberError) return;

    setSaving(true);
    try {
      await createAccount({
        email: email.trim(),
        password,
        name: name.trim(),
        phoneNumber,
        birthDate,
        gender,
      });
      prepareMedicationStateForNewAccount();
      // 회원가입 응답에는 액세스 토큰이 없으므로 같은 자격증명으로 로그인까지 완료합니다.
      await login({ email: email.trim(), password });
    } catch (error) {
      if (error instanceof ApiError && error.field === 'email') {
        // 이메일은 가입 식별자라 가입 완료 뒤에도 바꿀 수 없습니다. 수정이 필요하면
        // 첫 단계로 돌아가 같은 주소를 유지한 채 서버 오류를 보여줍니다.
        setEmailError(
          error.code === 'EMAIL_ALREADY_EXISTS' ? error.message : '이메일 주소를 확인해주세요',
        );
        setSignupStep(1);
      } else {
        setLoginError(error instanceof ApiError ? error.message : LOGIN_FALLBACK_ERROR);
      }
      return;
    } finally {
      setSaving(false);
    }

    signIn(email);
    navigate('/home', { replace: true });
  }

  const signupStepCopy = STEP_COPY[signupStep];

  return (
    <div
      className={`mx-auto flex min-h-dvh w-full max-w-app flex-col ${
        mode === 'login' ? 'bg-card' : 'bg-background'
      }`}
    >
      <Header title="로그인 · 회원가입" onBack={goBack} />
      <main
        className={`flex flex-1 flex-col px-page-x ${
          mode === 'login' ? 'pt-5' : 'pb-10 pt-5'
        }`}
      >
        <div
          className="grid h-12 grid-cols-2 rounded-input bg-muted-bg p-1"
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
                className={`rounded-input text-sm font-bold ${
                  mode === 'login'
                    ? `relative -my-1 h-12 min-h-touch ${
                        selected ? 'text-primary' : 'text-muted-foreground'
                      }`
                    : `min-h-touch ${
                        selected ? 'bg-card text-foreground shadow-card' : 'text-muted-foreground'
                      }`
                }`}
                onClick={() => {
                  if (item === mode) return;
                  setMode(item);
                  resetAuthForm();
                }}
              >
                {mode === 'login' ? (
                  <span
                    className={`pointer-events-none absolute inset-x-0 top-1 flex h-10 items-center justify-center rounded-[10px] ${
                      selected ? 'bg-card shadow-card' : 'bg-transparent'
                    }`}
                  >
                    {item === 'login' ? '로그인' : '회원가입'}
                  </span>
                ) : (
                  item === 'login' ? '로그인' : '회원가입'
                )}
              </button>
            );
          })}
        </div>

        {mode === 'login' ? (
          <>
            <div className="mt-8">
              <h1 className="text-2xl font-bold leading-8 text-foreground">다시 만나서 반가워요</h1>
              <p className="mt-2 text-caption text-muted-foreground">
                로그인하면 저장한 복용약과 영양제를 이어서 볼 수 있어요.
              </p>
            </div>

            <form className="mt-5 flex flex-1 flex-col gap-4" onSubmit={complete}>
              <Input
                label="이메일"
                inputRef={emailInputRef}
                // type="email" 이 아닙니다. 브라우저가 한글 도메인을 퓨니코드로 바꾸지 않게 합니다.
                type="text"
                inputMode="email"
                placeholder="name@example.com"
                pattern={EMAIL_INPUT_PATTERN}
                autoComplete="email"
                autoCapitalize="none"
                spellCheck={false}
                value={email}
                maxLength={EMAIL_MAX_LENGTH}
                error={emailError ?? undefined}
                onChange={(event) => {
                  event.currentTarget.setCustomValidity('');
                  if ((event.nativeEvent as InputEvent).isComposing) {
                    setEmail(event.currentTarget.value);
                    return;
                  }
                  applyEmailInput(event.currentTarget);
                }}
                onCompositionEnd={(event) => applyEmailInput(event.currentTarget)}
                required
              />
              <Input
                label="비밀번호"
                type="password"
                autoComplete="current-password"
                placeholder="••••••••"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                error={loginError ?? undefined}
                required
              />
              <p className="text-caption text-muted-foreground">입력한 정보는 안전하게 보호해요.</p>
              <p className="mt-auto text-center text-caption text-muted-foreground">
                비밀번호를 잊으셨나요? 재설정
              </p>
              <Button type="submit" className="text-base" disabled={saving}>
                로그인
              </Button>
            </form>
          </>
        ) : (
          <>
            <div
              className="mt-4"
              role="progressbar"
              aria-label="회원가입 진행 단계"
              aria-valuemin={1}
              aria-valuemax={4}
              aria-valuenow={signupStep}
            >
              <div className="flex gap-[9px]" aria-hidden="true">
                {[1, 2, 3, 4].map((step) => (
                  <span
                    key={step}
                    className={`h-1 flex-1 rounded-pill ${
                      step <= signupStep ? 'bg-primary' : 'bg-border'
                    }`}
                  />
                ))}
              </div>
              <p className="mt-2 text-xs font-medium text-tertiary-foreground">
                {signupStep} / 4 단계
              </p>
            </div>

            <div className="mt-4">
              <h2 className="text-2xl font-bold leading-7 text-foreground">
                {signupStepCopy.title}
              </h2>
              {signupStepCopy.description && (
                <p className="mt-2 text-caption text-muted-foreground">
                  {signupStepCopy.description}
                </p>
              )}
              {signupStep === 2 && (
                <p className="mt-2 text-caption text-muted-foreground">
                  {email} 으로 6자리 코드를 보냈어요.
                </p>
              )}
            </div>

            <form className="mt-6 flex flex-1 flex-col gap-4" onSubmit={complete}>
              {signupStep === 1 && (
                <>
                  <Input
                    label="이메일"
                    inputRef={emailInputRef}
                    type="text"
                    inputMode="email"
                    placeholder="name@example.com"
                    pattern={EMAIL_INPUT_PATTERN}
                    autoComplete="email"
                    autoCapitalize="none"
                    spellCheck={false}
                    value={email}
                    maxLength={EMAIL_MAX_LENGTH}
                    error={emailError ?? undefined}
                    hint="이 주소로 인증코드를 보내드려요."
                    onChange={(event) => {
                      event.currentTarget.setCustomValidity('');
                      if ((event.nativeEvent as InputEvent).isComposing) {
                        setEmail(event.currentTarget.value);
                        return;
                      }
                      applyEmailInput(event.currentTarget);
                    }}
                    onCompositionEnd={(event) => applyEmailInput(event.currentTarget)}
                    required
                  />
                  <Button type="submit" className="mt-auto" disabled={saving || !email.trim()}>
                    인증코드 받기
                  </Button>
                </>
              )}

              {signupStep === 2 && (
                <>
                  <Input
                    label="인증코드"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    pattern="[0-9]{6}"
                    maxLength={VERIFICATION_CODE_LENGTH}
                    value={verificationCode}
                    trailingAction={
                      <span aria-label="남은 시간" className="px-2 text-caption text-primary">
                        {String(Math.floor(verificationSeconds / 60)).padStart(2, '0')}:
                        {String(verificationSeconds % 60).padStart(2, '0')}
                      </span>
                    }
                    onChange={(event) =>
                      setVerificationCode(
                        event.target.value.replace(/\D/g, '').slice(0, VERIFICATION_CODE_LENGTH),
                      )
                    }
                    hint="메일이 안 왔나요? 다시 보내기"
                    required
                  />
                  <Button
                    type="submit"
                    className="mt-auto"
                    disabled={saving || verificationCode.length !== VERIFICATION_CODE_LENGTH}
                  >
                    확인
                  </Button>
                </>
              )}

              {signupStep === 3 && (
                <>
                  <Input
                    label="비밀번호"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="new-password"
                    maxLength={PASSWORD_MAX_LENGTH}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    trailingAction={
                      <button
                        type="button"
                        aria-label={showPassword ? '비밀번호 숨기기' : '비밀번호 보기'}
                        className="flex size-touch items-center justify-center rounded-full text-muted-foreground hover:bg-muted-bg hover:text-foreground"
                        onClick={() => setShowPassword((visible) => !visible)}
                      >
                        {showPassword ? (
                          <EyeOff className="size-5" aria-hidden="true" />
                        ) : (
                          <Eye className="size-5" aria-hidden="true" />
                        )}
                      </button>
                    }
                    required
                  />
                  <Input
                    label="비밀번호 확인"
                    type={showPasswordConfirm ? 'text' : 'password'}
                    autoComplete="new-password"
                    maxLength={PASSWORD_MAX_LENGTH}
                    value={passwordConfirm}
                    error={passwordConfirmError ?? undefined}
                    onChange={(event) => {
                      setPasswordConfirm(event.target.value);
                      setPasswordConfirmError(null);
                    }}
                    trailingAction={
                      <button
                        type="button"
                        aria-label={
                          showPasswordConfirm ? '비밀번호 확인 숨기기' : '비밀번호 확인 보기'
                        }
                        className="flex size-touch items-center justify-center rounded-full text-muted-foreground hover:bg-muted-bg hover:text-foreground"
                        onClick={() => setShowPasswordConfirm((visible) => !visible)}
                      >
                        {showPasswordConfirm ? (
                          <EyeOff className="size-5" aria-hidden="true" />
                        ) : (
                          <Eye className="size-5" aria-hidden="true" />
                        )}
                      </button>
                    }
                    required
                  />
                  <Button
                    type="submit"
                    className="mt-auto"
                    disabled={saving || !password || !passwordConfirm}
                  >
                    다음
                  </Button>
                </>
              )}

              {signupStep === 4 && (
                <>
                  <Input
                    label="이름"
                    autoComplete="name"
                    value={name}
                    maxLength={NAME_MAX_LENGTH}
                    error={nameError ?? undefined}
                    onChange={(event) => {
                      if ((event.nativeEvent as InputEvent).isComposing) {
                        setName(event.currentTarget.value);
                        return;
                      }
                      applyNameInput(event.currentTarget);
                    }}
                    onCompositionEnd={(event) => applyNameInput(event.currentTarget)}
                    required
                  />
                  <Input
                    label="전화번호"
                    type="tel"
                    inputMode="tel"
                    autoComplete="tel"
                    value={phoneNumber}
                    maxLength={PHONE_NUMBER_MAX_LENGTH}
                    error={phoneNumberError ?? undefined}
                    onChange={(event) => {
                      setPhoneNumber(formatPhoneNumberInput(event.target.value));
                      setPhoneNumberError(null);
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
                      onCheckedChange={setRecordTerms}
                      label="진료기록 수집 및 이용에 동의해요"
                      required
                    />
                    <CheckboxField
                      id="ai-terms"
                      checked={aiTerms}
                      onCheckedChange={setAiTerms}
                      label="AI 서비스 이용에 동의해요"
                      required
                    />
                  </fieldset>
                  {loginError && (
                    <p role="alert" aria-live="assertive" className="text-sm text-danger-strong">
                      {loginError}
                    </p>
                  )}
                  <Button
                    type="submit"
                    className="mt-auto"
                    disabled={saving || !recordTerms || !aiTerms || !gender}
                  >
                    회원가입 완료
                  </Button>
                </>
              )}
            </form>
          </>
        )}
      </main>
      {mode === 'login' && (
        <footer className="flex h-15 min-h-15 shrink-0 items-start justify-center gap-2 px-page-x pt-4 text-xs text-muted-foreground">
          <Link to="/terms" className="flex min-h-touch hover:text-foreground">
            이용약관
          </Link>
          <span aria-hidden="true">|</span>
          <Link to="/privacy" className="flex min-h-touch hover:text-foreground">
            개인정보 처리 안내
          </Link>
        </footer>
      )}
    </div>
  );
}
