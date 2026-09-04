import { useRef, useState, type FormEvent } from 'react';
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
import {
  Button,
  CheckboxField,
  GenderRadioGroup,
  Header,
  Input,
} from '@/shared/ui';

type AuthMode = 'login' | 'signup';

/** 서버가 오류 본문을 못 줄 때만 씁니다. 평소에는 서버 message 를 그대로 띄웁니다. */
const LOGIN_FALLBACK_ERROR = '로그인하지 못했어요. 잠시 후 다시 시도해주세요.';

export function AuthPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { signIn } = useSession();
  const emailInputRef = useRef<HTMLInputElement>(null);
  const [mode, setMode] = useState<AuthMode>('login');
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

  /**
   * 탭을 옮길 때 폼을 새로 시작합니다.
   *
   * 예전에는 오류 문구 두 개만 지워서, 로그인 칸에 쳐둔 이메일·비밀번호가 회원가입 폼에
   * 그대로 따라왔습니다. 필수 동의도 이전 세션의 흔적으로 켜져 있으면 안 됩니다.
   *
   * 이메일 칸은 applyEmailInput 이 DOM 값을 직접 쓰지만(IME 때문), state 를 비우면
   * React 가 리렌더하면서 DOM 도 따라 비워지므로 여기서 따로 손댈 것은 없습니다.
   */
  function resetAuthForm() {
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

  /**
   * 이메일 칸에서 쓸 수 없는 문자를 지웁니다.
   *
   * setEmail 만으로는 부족합니다. 정리한 값이 직전 state 와 같으면 리렌더가 일어나지 않아
   * IME 가 DOM 에 넣어둔 조합 문자가 화면에 그대로 남습니다. 그래서 값을 직접 되돌립니다.
   * 되돌리는 문자열에 앞 글자가 모두 들어 있으므로 지워지는 건 한글뿐입니다.
   *
   * 단, 조합이 끝난 뒤에만 불러야 합니다. 조합 도중에 값을 건드리면 IME 버퍼와 충돌해
   * 앞서 입력해 둔 영문까지 함께 날아갑니다.
   */
  function applyEmailInput(input: HTMLInputElement) {
    const typed = input.value;
    const sanitized = sanitizeEmailInput(typed);
    if (sanitized !== typed) input.value = sanitized;
    // 조용히 지우면 왜 안 찍히는지 모른다. 지운 게 있을 때만 이유를 알린다.
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
      sanitized === normalized
        ? null
        : '이름에는 숫자, 공백, 특수문자를 사용할 수 없습니다.',
    );
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
      const nextNameError = validateName(name);
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
        await createAccount({ email, password, name: name.trim(), phoneNumber, birthDate, gender });
        prepareMedicationStateForNewAccount();
        // 회원가입 응답에는 액세스 토큰이 없으므로 같은 자격증명으로 로그인까지 완료합니다.
        await login({ email: email.trim(), password });
      } catch (error) {
        if (error instanceof ApiError && error.field === 'email') {
          // 중복과 형식 오류를 갈라 씁니다. 예전에는 둘 다 「확인해주세요」라 나와서,
          // 주소가 멀쩡한데도 계속 고치라는 말로 읽혔습니다.
          //
          // 중복일 때는 **서버 문구를 그대로** 씁니다. 활성 계정인지 탈퇴 계정인지
          // 구분되지 않게 뭉갠 문구라 프론트가 따로 만들면 그 의도가 깨집니다(#196).
          // 형식 오류(422)는 서버가 영문 pydantic 메시지를 주므로 자체 문구를 씁니다.
          emailInputRef.current?.setCustomValidity(
            error.code === 'EMAIL_ALREADY_EXISTS' ? error.message : '이메일 주소를 확인해주세요',
          );
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
        // 서버 문구를 그대로 씁니다. 계정 없음·비밀번호 불일치·정지·탈퇴가 모두 같은
        // 400 응답이라 여기서 갈라볼 것이 없습니다(#196).
        // 프론트가 "이메일이 없습니다" 같은 문구를 만들면 가입 여부가 새어나갑니다.
        setLoginError(error instanceof ApiError ? error.message : LOGIN_FALLBACK_ERROR);
        return;
      } finally {
        setSaving(false);
      }
    }
    signIn(email);
    const requestedPath = (location.state as { from?: unknown } | null)?.from;
    const destination =
      mode === 'login' &&
      typeof requestedPath === 'string' &&
      requestedPath.startsWith('/') &&
      !requestedPath.startsWith('//') &&
      requestedPath !== '/login'
        ? requestedPath
        : '/home';
    navigate(destination, { replace: true });
  }

  return (
    <div
      className={`mx-auto flex min-h-dvh w-full max-w-app flex-col ${
        mode === 'login' ? 'bg-card' : 'bg-background'
      }`}
    >
      <Header title="로그인 · 회원가입" onBack={() => navigate(-1)} />
      <main
        className={`flex flex-1 flex-col px-page-x ${mode === 'login' ? 'pt-5' : 'py-6'}`}
      >
        <div
          className={`grid grid-cols-2 rounded-input bg-muted-bg p-1 ${
            mode === 'login' ? 'h-12' : ''
          }`}
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
                  // 같은 탭을 다시 눌렀을 때는 지우지 않습니다. 이 가드가 없으면
                  // 회원가입 폼을 다 채운 사람이 「회원가입」을 한 번 더 누르는 순간
                  // 전부 날아갑니다.
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

        <div className="mt-8">
          <h1
            className={`${mode === 'signup' ? 'text-xl' : 'text-2xl'} font-bold text-foreground ${
              mode === 'login' ? 'leading-8' : ''
            }`}
          >
            {mode === 'login' ? '다시 만나서 반가워요' : '내 복약 기록을 안전하게 보관해요'}
          </h1>
          <p
            className={`mt-2 ${mode === 'login' ? 'text-caption' : 'text-sm'} text-muted-foreground`}
          >
            {mode === 'login'
              ? '로그인하면 저장한 복용약과 영양제를 이어서 볼 수 있어요.'
              : '필수 동의는 각각 내용을 확인하고 선택해 주세요.'}
          </p>
        </div>

        <form
          className={`${mode === 'login' ? 'mt-5' : 'mt-6'} flex flex-1 flex-col gap-4`}
          onSubmit={complete}
        >
          <Input
            label="이메일"
            inputRef={emailInputRef}
            // type="email" 이 아닙니다. 크롬이 그 타입에서 도메인을 퓨니코드로 바꿔 값을 주는 탓에
            // 화면의 한글을 코드가 볼 수 없습니다. 자세한 이유는 EMAIL_INPUT_PATTERN 주석 참고.
            type="text"
            inputMode="email"
            placeholder="name@example.com"
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
              // 조합 중에는 들어온 값을 그대로 state 에 넣습니다. 정리는 조합이 끝난 뒤 합니다.
              // state 를 그대로 두면 React 가 controlled input 값을 되돌리는데, 그 복원이
              // IME 버퍼와 충돌해 앞서 입력해 둔 영문까지 지워버립니다.
              //
              // 플래그를 따로 들지 않고 이벤트의 isComposing 을 씁니다. 플래그를 쓰면
              // compositionend 를 한 번이라도 놓쳤을 때 칸이 영영 얼어붙습니다.
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
            type={mode === 'signup' && showPassword ? 'text' : 'password'}
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            placeholder={mode === 'login' ? '••••••••' : undefined}
            value={password}
            // 로그인에는 상한을 걸지 않습니다. 이 정책이 생기기 전에 더 긴 비밀번호로
            // 가입한 사람이 로그인 자체를 못 하게 됩니다.
            // 상한은 「새로 정하는 비밀번호」에만 겁니다.
            maxLength={mode === 'signup' ? PASSWORD_MAX_LENGTH : undefined}
            onChange={(event) => setPassword(event.target.value)}
            error={loginError ?? undefined}
            trailingAction={
              mode === 'signup' ? (
                <button
                  type="button"
                  aria-label={showPassword ? '비밀번호 숨기기' : '비밀번호 보기'}
                  className="flex size-10 items-center justify-center rounded-full text-muted-foreground hover:bg-muted-bg hover:text-foreground"
                  onClick={() => setShowPassword((visible) => !visible)}
                >
                  {showPassword ? (
                    <EyeOff className="size-5" aria-hidden="true" />
                  ) : (
                    <Eye className="size-5" aria-hidden="true" />
                  )}
                </button>
              ) : undefined
            }
            required
          />

          {mode === 'login' && (
            <p className="text-caption text-muted-foreground">입력한 정보는 안전하게 보호해요.</p>
          )}

          {mode === 'signup' && (
            <>
              <Input
                label="비밀번호 확인"
                type={showPasswordConfirm ? 'text' : 'password'}
                autoComplete="new-password"
                value={passwordConfirm}
                maxLength={PASSWORD_MAX_LENGTH}
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
                    className="flex size-10 items-center justify-center rounded-full text-muted-foreground hover:bg-muted-bg hover:text-foreground"
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

          {mode === 'login' && (
            <p className="mt-auto text-center text-caption text-muted-foreground">
              비밀번호를 잊으셨나요? 재설정
            </p>
          )}

          <Button
            type="submit"
            className={mode === 'login' ? 'text-base' : 'mt-auto'}
            disabled={saving || (mode === 'signup' && (!recordTerms || !aiTerms))}
          >
            {mode === 'login' ? '로그인' : '회원가입 완료'}
          </Button>
        </form>
      </main>
      <footer
        className={`flex shrink-0 justify-center gap-2 px-page-x text-xs text-muted-foreground ${
          mode === 'login'
            ? 'h-15 min-h-15 items-start pt-4'
            : 'min-h-touch items-center border-t border-border'
        }`}
      >
        <Link
          to="/terms"
          className={`hover:text-foreground ${
            mode === 'login' ? 'flex min-h-touch items-start' : ''
          }`}
        >
          이용약관
        </Link>
        <span aria-hidden="true">|</span>
        <Link
          to="/privacy"
          className={`hover:text-foreground ${
            mode === 'login' ? 'flex min-h-touch items-start' : ''
          }`}
        >
          개인정보 처리 안내
        </Link>
      </footer>
    </div>
  );
}
