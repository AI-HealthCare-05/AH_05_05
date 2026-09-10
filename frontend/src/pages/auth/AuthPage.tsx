import { useEffect, useLayoutEffect, useRef, useState, type ClipboardEvent, type FormEvent } from 'react';
import { Eye, EyeOff } from 'lucide-react';
import { Link, useLocation, useNavigate } from 'react-router';
import { useSession } from '@/app/SessionContext';
import { createAccount, type Gender } from '@/entities/account';
import { login, requestPasswordReset } from '@/entities/auth';
import { requestEmailVerification, verifyEmailCode } from '@/entities/email-verification';
import { prepareMedicationStateForNewAccount } from '@/entities/medication';
import { PrivacyPage, TermsPage } from '@/pages/legal';
import { ApiError } from '@/shared/api/client';
import {
  MIN_BIRTH_DATE,
  UNDER_FOURTEEN_MESSAGE,
  formatDateInputValue,
  validateBirthDate,
} from '@/shared/lib/birthDate';
import { EMAIL_INPUT_PATTERN, EMAIL_MAX_LENGTH, sanitizeEmailInput } from '@/shared/lib/email';
import { NAME_MAX_LENGTH, sanitizeNameInput, validateName } from '@/shared/lib/name';
import {
  PASSWORD_MAX_LENGTH,
  sanitizePasswordInput,
  validatePassword,
} from '@/shared/lib/password';
import {
  PHONE_NUMBER_MAX_LENGTH,
  formatPhoneNumberInput,
  validatePhoneNumber,
} from '@/shared/lib/phoneNumber';
import {
  Button,
  CheckboxField,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  GenderRadioGroup,
  Header,
  Input,
} from '@/shared/ui';

type AuthMode = 'login' | 'signup';
type SignupStep = 1 | 2 | 3 | 4;

const VERIFICATION_CODE_LENGTH = 6;
const UNDER_FOURTEEN_SIGNUP_UNAVAILABLE_MESSAGE =
  '만 14세 미만은 보호자 동의 절차가 아직 준비되지 않아 가입할 수 없어요.';
const AGE_TERMS_UNAVAILABLE_MESSAGE = '만14세 이상 가입이 가능합니다.';

/** 서버가 오류 본문을 못 줄 때만 씁니다. 평소에는 서버 message 를 그대로 띄웁니다. */
const LOGIN_FALLBACK_ERROR = '로그인하지 못했어요. 잠시 후 다시 시도해주세요.';

const STEP_COPY: Record<SignupStep, { title: string; description?: string }> = {
  1: { title: '이메일을 알려주세요', description: '인증 메일을 보내드릴 주소예요.' },
  2: { title: '메일함을 확인해주세요' },
  3: {
    title: '비밀번호를 정해주세요',
    description: '로그인할 때 쓸 비밀번호예요. 한글은 쓸 수 없어요.',
  },
  4: { title: '마지막이에요' },
};

export function AuthPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { signIn } = useSession();
  const emailInputRef = useRef<HTMLInputElement>(null);
  const contentRef = useRef<HTMLElement>(null);
  const [mode, setMode] = useState<AuthMode>('login');
  const [signupStep, setSignupStep] = useState<SignupStep>(1);
  const [verificationCode, setVerificationCode] = useState('');
  const [verificationId, setVerificationId] = useState<number | null>(null);
  const [verificationToken, setVerificationToken] = useState<string | null>(null);
  const [verificationSeconds, setVerificationSeconds] = useState(0);
  const [verificationExpiresAt, setVerificationExpiresAt] = useState<number | null>(null);
  const [verificationError, setVerificationError] = useState<string | null>(null);
  const [serviceTerms, setServiceTerms] = useState(false);
  const [personalInformationTerms, setPersonalInformationTerms] = useState(false);
  const [ageTerms, setAgeTerms] = useState(false);
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
  const [ageTermsError, setAgeTermsError] = useState<string | null>(null);
  const [passwordConfirmError, setPasswordConfirmError] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [nameError, setNameError] = useState<string | null>(null);
  const [phoneNumberError, setPhoneNumberError] = useState<string | null>(null);
  const [loginError, setLoginError] = useState<string | null>(null);
  const [passwordResetDialogOpen, setPasswordResetDialogOpen] = useState(false);
  const [passwordResetSending, setPasswordResetSending] = useState(false);
  const [passwordResetMessage, setPasswordResetMessage] = useState<string | null>(null);
  const [passwordResetError, setPasswordResetError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [showSignupTerms, setShowSignupTerms] = useState(false);
  const [showSignupPrivacy, setShowSignupPrivacy] = useState(false);
  const today = formatDateInputValue(new Date());

  // Animate existing nodes only on navigation, so typing and validation retain
  // the same DOM, caret and focus. Labels, controls and hints move as one field.
  useLayoutEffect(() => {
    const content = contentRef.current;
    if (!content) return;
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (reducedMotion.matches) return;
    const entrances = new Map<Element, Animation>();
    content.querySelectorAll('.auth-enter').forEach((element, index) => {
      if (element.contains(document.activeElement)) return;
      entrances.set(element, element.animate(
        [{ opacity: 0, transform: 'translateY(8px)' }, { opacity: 1, transform: 'translateY(0px)' }],
        { duration: 280, delay: index * 80, easing: 'cubic-bezier(0.22, 1, 0.36, 1)', fill: 'backwards' },
      ));
    });
    const cancelAll = () => entrances.forEach((animation) => animation.cancel());
    const revealFocusedGroup = (event: FocusEvent) => {
      if (!(event.target instanceof Element)) return;
      const group = event.target.closest('.auth-enter');
      if (group) entrances.get(group)?.cancel();
    };
    content.addEventListener('focusin', revealFocusedGroup);
    reducedMotion.addEventListener('change', cancelAll);
    return () => {
      cancelAll();
      content.removeEventListener('focusin', revealFocusedGroup);
      reducedMotion.removeEventListener('change', cancelAll);
    };
  }, [mode, signupStep]);

  useEffect(() => {
    if (mode === 'signup' && signupStep === 1) {
      emailInputRef.current?.setCustomValidity(emailError ?? '');
    }
  }, [emailError, mode, signupStep]);

  useEffect(() => {
    if (mode !== 'signup' || signupStep !== 2 || verificationExpiresAt === null) return;
    const updateRemainingSeconds = () => {
      setVerificationSeconds(
        Math.max(0, Math.ceil((verificationExpiresAt - Date.now()) / 1_000)),
      );
    };
    updateRemainingSeconds();
    const timer = window.setInterval(() => {
      updateRemainingSeconds();
    }, 250);
    return () => window.clearInterval(timer);
  }, [mode, signupStep, verificationExpiresAt]);

  /** 탭을 옮길 때는 가입 흐름을 새로 시작합니다. 같은 탭을 다시 누르는 경우는 보존합니다. */
  function resetAuthForm() {
    setSignupStep(1);
    setVerificationCode('');
    setVerificationId(null);
    setVerificationToken(null);
    setVerificationSeconds(0);
    setVerificationExpiresAt(null);
    setVerificationError(null);
    setEmail('');
    setPassword('');
    setPasswordConfirm('');
    setShowPassword(false);
    setShowPasswordConfirm(false);
    setName('');
    setPhoneNumber('');
    setBirthDate('');
    setGender('');
    setServiceTerms(false);
    setPersonalInformationTerms(false);
    setAgeTerms(false);
    setRecordTerms(false);
    setAiTerms(false);
    setEmailError(null);
    setBirthDateError(null);
    setAgeTermsError(null);
    setPasswordConfirmError(null);
    setPasswordError(null);
    setNameError(null);
    setPhoneNumberError(null);
    setLoginError(null);
    setShowSignupTerms(false);
    setShowSignupPrivacy(false);
    setPasswordResetDialogOpen(false);
    setPasswordResetSending(false);
    setPasswordResetMessage(null);
    setPasswordResetError(null);
    emailInputRef.current?.setCustomValidity('');
  }

  function applyEmailInput(input: HTMLInputElement) {
    const typed = input.value;
    const sanitized = sanitizeEmailInput(typed);
    if (sanitized !== typed) input.value = sanitized;
    setEmailError(sanitized === typed ? null : '이메일은 영문, 숫자와 기호만 입력할 수 있어요.');
    setEmail(sanitized);
    setPasswordResetMessage(null);
    setPasswordResetError(null);
    setVerificationId(null);
    setVerificationToken(null);
    setVerificationCode('');
    setVerificationSeconds(0);
    setVerificationExpiresAt(null);
    setVerificationError(null);
  }

  /**
   * 비밀번호 칸의 한글을 지웁니다. **조합이 끝난 뒤에만 부릅니다.**
   *
   * `applyEmailInput` 과 같은 형태다 — 정리한 값이 다르면 DOM 의 value 까지 직접 맞춘다.
   * 그러지 않으면 컨트롤드 value 와 DOM 이 어긋나 커서가 튄다.
   */
  function applyPasswordInput(input: HTMLInputElement) {
    const typed = input.value;
    const sanitized = sanitizePasswordInput(typed);
    if (sanitized !== typed) input.value = sanitized;
    setPassword(sanitized);
    setPasswordError(null);
  }

  function applyPasswordConfirmInput(input: HTMLInputElement) {
    const typed = input.value;
    const sanitized = sanitizePasswordInput(typed);
    if (sanitized !== typed) input.value = sanitized;
    setPasswordConfirm(sanitized);
    setPasswordConfirmError(null);
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

  function applyAgeTerms(checked: boolean) {
    if (!checked) {
      setAgeTerms(false);
      setAgeTermsError(null);
      return;
    }

    const validation = validateBirthDate(birthDate);
    if (validation) {
      setAgeTerms(false);
      if (validation === UNDER_FOURTEEN_MESSAGE) {
        setBirthDateError(null);
        setAgeTermsError(AGE_TERMS_UNAVAILABLE_MESSAGE);
      } else {
        setBirthDateError(validation);
        setAgeTermsError(null);
      }
      return;
    }

    setBirthDateError(null);
    setAgeTermsError(null);
    setAgeTerms(true);
  }

  function goBack() {
    if (mode === 'signup' && signupStep > 1) {
      if (signupStep === 2) {
        setVerificationId(null);
        setVerificationToken(null);
        setVerificationCode('');
        setVerificationSeconds(0);
        setVerificationExpiresAt(null);
        setVerificationError(null);
      }
      setSignupStep((step) => (step - 1) as SignupStep);
      setLoginError(null);
      return;
    }
    navigate(-1);
  }

  function openPasswordResetDialog() {
    if (!email.trim()) {
      setEmailError('이메일을 입력해주세요');
      emailInputRef.current?.focus();
      return;
    }
    setEmailError(null);
    setPasswordResetMessage(null);
    setPasswordResetError(null);
    setPasswordResetDialogOpen(true);
  }

  async function confirmPasswordReset() {
    if (passwordResetSending) return;
    setPasswordResetSending(true);
    setPasswordResetError(null);
    try {
      await requestPasswordReset(email.trim());
      setPasswordResetDialogOpen(false);
      setPasswordResetMessage('입력한 이메일로 임시비밀번호 발송을 요청했습니다.');
    } catch {
      setPasswordResetError('임시비밀번호를 발송하지 못했습니다. 잠시 후 다시 시도해주세요.');
    } finally {
      setPasswordResetSending(false);
    }
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
      setSaving(true);
      setEmailError(null);
      try {
        const result = await requestEmailVerification(email);
        setVerificationId(result.verificationId);
        setVerificationToken(null);
        setVerificationCode('');
        setVerificationError(null);
        setVerificationSeconds(result.expiresIn);
        setVerificationExpiresAt(Date.now() + result.expiresIn * 1_000);
        setSignupStep(2);
      } catch (error) {
        setEmailError(error instanceof ApiError ? error.message : LOGIN_FALLBACK_ERROR);
      } finally {
        setSaving(false);
      }
      return;
    }

    if (signupStep === 2) {
      if (!/^\d{6}$/.test(verificationCode) || verificationId === null || verificationSeconds === 0)
        return;
      setSaving(true);
      setVerificationError(null);
      try {
        const result = await verifyEmailCode(verificationId, verificationCode);
        setVerificationToken(result.verificationToken);
        setSignupStep(3);
      } catch (error) {
        setVerificationError(
          error instanceof ApiError ? error.message : '인증번호를 확인해주세요.',
        );
      } finally {
        setSaving(false);
      }
      return;
    }

    if (signupStep === 3) {
      const nextPasswordError = validatePassword(password);
      const nextPasswordConfirmError =
        password === passwordConfirm ? null : '비밀번호가 일치하지 않아요.';
      setPasswordError(nextPasswordError);
      setPasswordConfirmError(nextPasswordConfirmError);
      if (nextPasswordError || nextPasswordConfirmError) return;
      setSignupStep(4);
      return;
    }

    if (!requiredConsentsAccepted || !gender) return;
    if (!verificationToken) {
      setSignupStep(1);
      setEmailError('이메일 인증을 다시 진행해주세요.');
      return;
    }
    const birthDateValidation = validateBirthDate(birthDate);
    const nextBirthDateError =
      birthDateValidation === UNDER_FOURTEEN_MESSAGE
        ? UNDER_FOURTEEN_SIGNUP_UNAVAILABLE_MESSAGE
        : birthDateValidation;
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
        emailVerificationToken: verificationToken,
        isTermsAgreed: requiredConsentsAccepted,
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
  const requiredConsentsAccepted =
    serviceTerms && personalInformationTerms && ageTerms && recordTerms && aiTerms;

  if (showSignupTerms) {
    return <TermsPage onBack={() => setShowSignupTerms(false)} />;
  }

  if (showSignupPrivacy) {
    return <PrivacyPage onBack={() => setShowSignupPrivacy(false)} />;
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="로그인 · 회원가입" onBack={goBack} />
      <main
        ref={contentRef}
        className={`rx-reading-content flex flex-1 flex-col px-page-x ${
          mode === 'login' ? 'pt-5' : 'pb-10 pt-5'
        }`}
      >
        <div
          className="rx-segmented grid h-12 grid-cols-2 rounded-input bg-muted-bg p-1"
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
                  if (item === mode) return;
                  setMode(item);
                  resetAuthForm();
                }}
              >
                {item === 'login' ? '로그인' : '회원가입'}
              </button>
            );
          })}
        </div>

        {mode === 'login' ? (
          <>
            <div className="mt-4 h-7 shrink-0" aria-hidden="true" />
            <div className="mt-4">
              <h1 className="auth-enter text-2xl font-bold leading-8 text-foreground">다시 만나서 반가워요</h1>
              <p className="auth-enter mt-2 text-caption text-muted-foreground">
                로그인하면 저장한 복용약과 영양제를 이어서 볼 수 있어요.
              </p>
            </div>

            <form className="mt-5 flex flex-1 flex-col gap-4" onSubmit={complete}>
              <Input
                className="auth-enter"
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
                className="auth-enter"
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
              <div className="mt-auto text-center text-caption text-muted-foreground">
                <span>비밀번호를 잊으셨나요? </span>
                <button
                  type="button"
                  className="font-bold text-foreground underline-offset-2 hover:underline"
                  onClick={openPasswordResetDialog}
                >
                  재설정
                </button>
                {passwordResetMessage && (
                  <p className="mt-2 text-primary" role="status">
                    {passwordResetMessage}
                  </p>
                )}
              </div>
              <Button type="submit" className="text-base" disabled={saving}>
                로그인
              </Button>
            </form>

            <Dialog open={passwordResetDialogOpen} onOpenChange={setPasswordResetDialogOpen}>
              <DialogContent showCloseButton={false}>
                <DialogHeader>
                  <DialogTitle>비밀번호 재설정</DialogTitle>
                  <DialogDescription>
                    입력한 이메일로 임시비밀번호가 발송됩니다. 재설정 하시겠습니까?
                  </DialogDescription>
                </DialogHeader>
                {passwordResetError && (
                  <p className="text-sm text-danger-strong" role="alert">
                    {passwordResetError}
                  </p>
                )}
                <DialogFooter className="grid grid-cols-2 gap-2">
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={passwordResetSending}
                    onClick={() => setPasswordResetDialogOpen(false)}
                  >
                    취소
                  </Button>
                  <Button
                    type="button"
                    disabled={passwordResetSending}
                    onClick={confirmPasswordReset}
                  >
                    {passwordResetSending ? '발송 중...' : '확인'}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
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
              <h2 className="auth-enter text-2xl font-bold leading-7 text-foreground">
                {signupStepCopy.title}
              </h2>
              {signupStepCopy.description && (
                <p className="auth-enter mt-2 text-caption text-muted-foreground">
                  {signupStepCopy.description}
                </p>
              )}
              {signupStep === 2 && (
                <p className="auth-enter mt-2 text-caption text-muted-foreground">
                  {email} 으로 6자리 코드를 보냈어요.
                </p>
              )}
            </div>

            <form className="mt-6 flex flex-1 flex-col gap-4" onSubmit={complete}>
              {signupStep === 1 && (
                <>
                  <Input
                    className="auth-enter"
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
                    className="auth-enter"
                    label="인증코드"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    pattern="[0-9]{6}"
                    maxLength={VERIFICATION_CODE_LENGTH}
                    value={verificationCode}
                    error={verificationError ?? undefined}
                    disabled={verificationSeconds === 0 || saving}
                    trailingAction={
                      <span aria-label="남은 시간" className="px-2 text-caption text-primary">
                        {String(Math.floor(verificationSeconds / 60)).padStart(2, '0')}:
                        {String(verificationSeconds % 60).padStart(2, '0')}
                      </span>
                    }
                    onChange={(event) => {
                      setVerificationCode(
                        event.target.value.replace(/\D/g, '').slice(0, VERIFICATION_CODE_LENGTH),
                      );
                      setVerificationError(null);
                    }}
                    onPaste={(event: ClipboardEvent<HTMLInputElement>) => {
                      event.preventDefault();
                      setVerificationCode(
                        event.clipboardData
                          .getData('text')
                          .replace(/\D/g, '')
                          .slice(0, VERIFICATION_CODE_LENGTH),
                      );
                      setVerificationError(null);
                    }}
                    required
                  />
                  <div className="flex items-center gap-1 text-sm text-muted-foreground">
                    <span>메일이 안 왔나요?</span>
                    <button
                      type="button"
                      className="min-h-touch font-semibold text-primary disabled:cursor-not-allowed disabled:text-tertiary-foreground"
                      disabled={verificationSeconds > 0 || saving}
                      onClick={async () => {
                        setSaving(true);
                        try {
                          const result = await requestEmailVerification(email);
                          setVerificationId(result.verificationId);
                          setVerificationToken(null);
                          setVerificationCode('');
                          setVerificationError(null);
                          setVerificationSeconds(result.expiresIn);
                          setVerificationExpiresAt(Date.now() + result.expiresIn * 1_000);
                        } catch (error) {
                          setVerificationError(
                            error instanceof ApiError ? error.message : LOGIN_FALLBACK_ERROR,
                          );
                        } finally {
                          setSaving(false);
                        }
                      }}
                    >
                      다시 보내기
                    </button>
                  </div>
                  <Button
                    type="submit"
                    className="mt-auto"
                    disabled={
                      saving ||
                      verificationSeconds === 0 ||
                      verificationCode.length !== VERIFICATION_CODE_LENGTH
                    }
                  >
                    확인
                  </Button>
                </>
              )}

              {signupStep === 3 && (
                <>
                  <Input
                    className="auth-enter"
                    label="비밀번호"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="new-password"
                    maxLength={PASSWORD_MAX_LENGTH}
                    value={password}
                    error={passwordError ?? undefined}
                    onChange={(event) => {
                      // 조합 중에는 값을 건드리지 않습니다. 컨트롤드 input 의 value 를
                      // 조합 중에 바꾸면 IME 가 조합 범위를 잃고 **앞서 입력해 둔 값까지
                      // 지워버립니다**(#374 실측). 정리는 compositionEnd 에서 합니다.
                      if ((event.nativeEvent as InputEvent).isComposing) {
                        setPassword(event.currentTarget.value);
                        return;
                      }
                      applyPasswordInput(event.currentTarget);
                    }}
                    onCompositionEnd={(event) => applyPasswordInput(event.currentTarget)}
                    trailingAction={
                      <button
                        type="button"
                        aria-label={showPassword ? '비밀번호 숨기기' : '비밀번호 보기'}
                        className="flex size-touch items-center justify-center rounded-full text-muted-foreground hover:bg-muted-bg hover:text-foreground"
                        onClick={() => setShowPassword((visible) => !visible)}
                      >
                        {showPassword ? (
                          <Eye className="size-5" aria-hidden="true" />
                        ) : (
                          <EyeOff className="size-5" aria-hidden="true" />
                        )}
                      </button>
                    }
                    required
                  />
                  <Input
                    className="auth-enter"
                    label="비밀번호 확인"
                    type={showPasswordConfirm ? 'text' : 'password'}
                    autoComplete="new-password"
                    maxLength={PASSWORD_MAX_LENGTH}
                    value={passwordConfirm}
                    error={passwordConfirmError ?? undefined}
                    onChange={(event) => {
                      if ((event.nativeEvent as InputEvent).isComposing) {
                        setPasswordConfirm(event.currentTarget.value);
                        return;
                      }
                      applyPasswordConfirmInput(event.currentTarget);
                    }}
                    onCompositionEnd={(event) => applyPasswordConfirmInput(event.currentTarget)}
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
                          <Eye className="size-5" aria-hidden="true" />
                        ) : (
                          <EyeOff className="size-5" aria-hidden="true" />
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
                    className="auth-enter"
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
                    className="auth-enter"
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
                    className="auth-enter"
                    label="생년월일"
                    type="date"
                    min={MIN_BIRTH_DATE}
                    max={today}
                    value={birthDate}
                    error={birthDateError ?? undefined}
                    onChange={(event) => {
                      setBirthDate(event.target.value);
                      setBirthDateError(null);
                      setAgeTerms(false);
                      setAgeTermsError(null);
                    }}
                    required
                  />
                  <div className="auth-enter">
                    <GenderRadioGroup value={gender} onChange={setGender} />
                  </div>
                  <fieldset className="auth-enter mt-2 flex flex-col gap-3">
                    <legend className="mb-2 text-base font-bold text-foreground">필수 동의</legend>
                    <div>
                      <CheckboxField
                        id="service-terms"
                        checked={serviceTerms}
                        onCheckedChange={setServiceTerms}
                        label="서비스 이용약관에 동의해요"
                        required
                      />
                      <button
                        type="button"
                        className="ml-11 inline-flex min-h-touch items-center text-sm font-semibold text-primary underline-offset-4 hover:underline"
                        onClick={() => setShowSignupTerms(true)}
                      >
                        서비스 이용약관 보기
                      </button>
                    </div>
                    <div>
                      <CheckboxField
                        id="personal-information-terms"
                        checked={personalInformationTerms}
                        onCheckedChange={setPersonalInformationTerms}
                        label="개인정보 수집 및 이용에 동의해요"
                        required
                      />
                      <div className="ml-11 flex flex-wrap items-center gap-x-3">
                        <details className="text-sm text-muted-foreground">
                          <summary className="min-h-touch cursor-pointer py-3 font-semibold text-primary">
                            개인정보 수집·이용 내용 보기
                          </summary>
                          <dl className="mb-2 flex flex-col gap-2 rounded-input bg-muted-bg p-3 leading-5">
                            <div>
                              <dt className="font-semibold text-foreground">수집 항목</dt>
                              <dd>이메일, 비밀번호, 이름, 전화번호, 생년월일, 성별</dd>
                            </div>
                            <div>
                              <dt className="font-semibold text-foreground">이용 목적</dt>
                              <dd>회원 식별, 본인 확인, 고객 상담 및 서비스 제공</dd>
                            </div>
                            <div>
                              <dt className="font-semibold text-foreground">보유 기간</dt>
                              <dd>회원 탈퇴 시까지 또는 관련 법령에 따른 보관 기간</dd>
                            </div>
                          </dl>
                        </details>
                        <button
                          type="button"
                          onClick={() => setShowSignupPrivacy(true)}
                          className="inline-flex min-h-touch items-center text-sm font-semibold text-primary underline-offset-4 hover:underline"
                        >
                          개인정보 처리 안내 보기
                        </button>
                      </div>
                    </div>
                    <div>
                      <CheckboxField
                        id="age-terms"
                        checked={ageTerms}
                        onCheckedChange={applyAgeTerms}
                        label="만 14세 이상이에요"
                        description="만 14세 미만은 보호자 동의 절차가 준비된 뒤 가입할 수 있어요."
                        required
                      />
                      {ageTermsError && (
                        <p role="alert" className="ml-9 text-sm text-danger-strong">
                          {ageTermsError}
                        </p>
                      )}
                    </div>
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
                    disabled={
                      saving || !requiredConsentsAccepted || !gender
                    }
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
