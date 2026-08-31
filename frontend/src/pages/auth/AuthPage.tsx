import { useRef, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router';
import { useSession } from '@/app/SessionContext';
import { NAME_MAX_LENGTH, createAccount, type Gender } from '@/entities/account';
import { login } from '@/entities/auth';
import { prepareMedicationStateForNewAccount } from '@/entities/medication';
import { ApiError } from '@/shared/api/client';
import {
  MIN_BIRTH_DATE,
  formatDateInputValue,
  validateBirthDate,
} from '@/shared/lib/birthDate';
import { EMAIL_INPUT_PATTERN, EMAIL_MAX_LENGTH, sanitizeEmailInput } from '@/shared/lib/email';
import {
  PHONE_NUMBER_MAX_LENGTH,
  formatPhoneNumberInput,
  validatePhoneNumber,
} from '@/shared/lib/phoneNumber';
import { Button, CheckboxField, GenderRadioGroup, Header, Input } from '@/shared/ui';

type AuthMode = 'login' | 'signup';

/** 서버가 오류 본문을 못 줄 때만 씁니다. 평소에는 서버 message 를 그대로 띄웁니다. */
const LOGIN_FALLBACK_ERROR = '로그인하지 못했어요. 잠시 후 다시 시도해주세요.';

export function AuthPage() {
  const navigate = useNavigate();
  const { signIn } = useSession();
  const emailInputRef = useRef<HTMLInputElement>(null);
  const [mode, setMode] = useState<AuthMode>('login');
  const [recordTerms, setRecordTerms] = useState(false);
  const [aiTerms, setAiTerms] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
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

  /**
   * 이메일 칸에서 쓸 수 없는 문자를 지웁니다.
   *
   * setEmail 만으로는 부족합니다. 정리한 값이 직전 state 와 같으면 리렌더가 일어나지 않아,
   * 한글 IME 가 DOM 에 넣어둔 조합 문자가 화면에 그대로 남습니다. 반대로 리렌더가 일어나면
   * 조합 중인 버퍼를 덮어써서 앞서 입력한 글자까지 날아갑니다.
   * 그래서 DOM 값을 직접 되돌려 조합을 끊습니다. 되돌리는 값에 앞 글자가 모두 들어 있으므로
   * 지워지는 건 한글뿐입니다. 되돌린 뒤 커서는 끝으로 갑니다.
   */
  function applyEmailInput(input: HTMLInputElement) {
    const typed = input.value;
    const sanitized = sanitizeEmailInput(typed);
    if (sanitized !== typed) input.value = sanitized;
    // 조용히 지우면 왜 안 찍히는지 모른다. 지운 게 있을 때만 이유를 알린다.
    setEmailError(sanitized === typed ? null : '이메일은 영문, 숫자와 기호만 입력할 수 있어요.');
    setEmail(sanitized);
  }

  async function complete(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoginError(null);
    emailInputRef.current?.setCustomValidity('');

    if (mode === 'signup') {
      if (!recordTerms || !aiTerms || !gender) return;
      const nextBirthDateError = validateBirthDate(birthDate);
      const nextPasswordConfirmError =
        password === passwordConfirm ? null : '비밀번호가 일치하지 않아요.';
      const nextNameError = name.trim().length >= 2 ? null : '이름을 두 글자 이상 입력해 주세요.';
      const nextPhoneNumberError = validatePhoneNumber(phoneNumber);
      setBirthDateError(nextBirthDateError);
      setPasswordConfirmError(nextPasswordConfirmError);
      setNameError(nextNameError);
      setPhoneNumberError(nextPhoneNumberError);
      if (
        nextBirthDateError ||
        nextPasswordConfirmError ||
        nextNameError ||
        nextPhoneNumberError
      ) return;

      setSaving(true);
      try {
        await createAccount({ email, password, name, phoneNumber, birthDate, gender });
        prepareMedicationStateForNewAccount();
        // 회원가입 응답에는 액세스 토큰이 없으므로 같은 자격증명으로 로그인까지 완료합니다.
        await login({ email: email.trim(), password });
      } catch (error) {
        if (error instanceof ApiError && error.field === 'email') {
          emailInputRef.current?.setCustomValidity('이메일 주소를 확인해주세요');
          emailInputRef.current?.reportValidity();
        } else {
          setLoginError(error instanceof ApiError ? error.message : LOGIN_FALLBACK_ERROR);
        }
        return;
      } finally {
        setSaving(false);
      }
    } else {
      setSaving(true);
      try {
        // 토큰은 login() 안에서 메모리에만 심습니다. 새로고침하면 사라집니다(유저플로우 v4).
        await login({ email: email.trim(), password });
      } catch (error) {
        // 서버 문구를 그대로 씁니다. 400(자격증명)과 423(정지·탈퇴) 모두 마찬가지입니다.
        // 프론트가 "이메일이 없습니다" 같은 문구를 만들면 가입 여부가 새어나갑니다.
        setLoginError(error instanceof ApiError ? error.message : LOGIN_FALLBACK_ERROR);
        return;
      } finally {
        setSaving(false);
      }
    }
    signIn(email);
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
                onClick={() => {
                  setMode(item);
                  emailInputRef.current?.setCustomValidity('');
                  // 탭을 옮기면 지난 로그인 실패 문구를 지웁니다. 회원가입 폼에 남아 있으면 오해합니다.
                  setLoginError(null);
                  setEmailError(null);
                }}
              >
                {item === 'login' ? '로그인' : '회원가입'}
              </button>
            );
          })}
        </div>

        <div className="mt-8">
          <h1
            className={`${mode === 'signup' ? 'text-xl' : 'text-2xl'} font-bold text-foreground`}
          >
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
            inputRef={emailInputRef}
            // type="email" 이 아닙니다. 크롬이 그 타입에서 도메인을 퓨니코드로 바꿔 값을 주는 탓에
            // 화면의 한글을 코드가 볼 수 없습니다. 자세한 이유는 EMAIL_INPUT_PATTERN 주석 참고.
            type="text"
            inputMode="email"
            pattern={EMAIL_INPUT_PATTERN}
            autoComplete="email"
            // text 로 바뀌면서 모바일 자동 대문자·맞춤법 교정이 붙습니다. 이메일에는 방해가 됩니다.
            autoCapitalize="none"
            spellCheck={false}
            value={email}
            maxLength={EMAIL_MAX_LENGTH}
            error={emailError ?? undefined}
            onChange={(event) => {
              event.currentTarget.setCustomValidity('');
              applyEmailInput(event.currentTarget);
            }}
            // IME 는 조합이 끝나는 순간 값을 다시 밀어 넣습니다. onChange 만으로는
            // 그때 들어온 한글이 남을 수 있어 조합 종료 시점에 한 번 더 정리합니다.
            onCompositionEnd={(event) => applyEmailInput(event.currentTarget)}
            required
          />
          <Input
            label="비밀번호"
            type="password"
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            error={loginError ?? undefined}
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
                label="이름"
                autoComplete="name"
                value={name}
                maxLength={NAME_MAX_LENGTH}
                error={nameError ?? undefined}
                onChange={(event) => {
                  setName(event.target.value);
                  setNameError(null);
                }}
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

          <Button
            type="submit"
            className="mt-auto"
            disabled={saving || (mode === 'signup' && (!recordTerms || !aiTerms))}
          >
            {mode === 'login' ? '로그인' : '회원가입 완료'}
          </Button>
        </form>
      </main>
    </div>
  );
}
