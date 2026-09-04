import { useEffect, useState, type FormEvent } from 'react';
import { ChevronRight } from 'lucide-react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { useSession } from '@/app/SessionContext';
import {
  getMyProfile,
  updateMyProfile,
  type AccountProfile,
  type Gender,
  type UpdateAccountProfilePayload,
} from '@/entities/account';
import { TAB_ROUTES } from '@/shared/config/tabRoutes';
import {
  MIN_BIRTH_DATE,
  formatDateInputValue,
  validateBirthDate,
} from '@/shared/lib/birthDate';
import { NAME_MAX_LENGTH, validateName } from '@/shared/lib/name';
import {
  PHONE_NUMBER_MAX_LENGTH,
  formatPhoneNumberInput,
  validatePhoneNumber,
} from '@/shared/lib/phoneNumber';
import {
  BottomTabbar,
  Button,
  Card,
  ErrorDialog,
  GenderRadioGroup,
  Header,
  Input,
} from '@/shared/ui';
import { PasswordChangeSheet } from './PasswordChangeSheet';
import { WithdrawAccountDialog } from './WithdrawAccountDialog';

interface MyProfilePageProps {
  profileLoader?: () => Promise<AccountProfile>;
  profileSaver?: (payload: UpdateAccountProfilePayload) => Promise<AccountProfile>;
}

export function MyProfilePage({
  profileLoader = getMyProfile,
  profileSaver = updateMyProfile,
}: MyProfilePageProps) {
  const navigate = useNavigate();
  const { signOut } = useSession();
  const [profile, setProfile] = useState<AccountProfile | null>(null);
  const [name, setName] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [birthDate, setBirthDate] = useState('');
  const [gender, setGender] = useState<Gender | ''>('');
  const [birthDateError, setBirthDateError] = useState<string | null>(null);
  const [nameError, setNameError] = useState<string | null>(null);
  const [phoneNumberError, setPhoneNumberError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [passwordSheetOpen, setPasswordSheetOpen] = useState(false);
  const [withdrawDialogOpen, setWithdrawDialogOpen] = useState(false);
  const today = formatDateInputValue(new Date());

  useEffect(() => {
    let cancelled = false;
    profileLoader()
      .then((loadedProfile) => {
        if (cancelled) return;
        setProfile(loadedProfile);
        setName(loadedProfile.name);
        setPhoneNumber(formatPhoneNumberInput(loadedProfile.phoneNumber));
        setBirthDate(loadedProfile.birthDate);
        setGender(loadedProfile.gender);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : '기본정보를 불러오지 못했어요.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [profileLoader]);

  const changed = Boolean(
    profile &&
      gender &&
      (profile.name !== name.trim() ||
        formatPhoneNumberInput(profile.phoneNumber) !== phoneNumber ||
        profile.birthDate !== birthDate ||
        profile.gender !== gender),
  );

  async function save(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (!profile || !gender || !changed || saving) return;
    const nextBirthDateError = validateBirthDate(birthDate);
    const nextNameError = validateName(name);
    const nextPhoneNumberError = validatePhoneNumber(phoneNumber);
    setBirthDateError(nextBirthDateError);
    setNameError(nextNameError);
    setPhoneNumberError(nextPhoneNumberError);
    if (nextBirthDateError || nextNameError || nextPhoneNumberError) return;

    setSaving(true);
    setSaveError(null);
    try {
      const savedProfile = await profileSaver({ name: name.trim(), phoneNumber, birthDate, gender });
      setProfile(savedProfile);
      setName(savedProfile.name);
      setPhoneNumber(formatPhoneNumberInput(savedProfile.phoneNumber));
      setBirthDate(savedProfile.birthDate);
      setGender(savedProfile.gender);
      toast.success('기본정보를 저장했어요.');
    } catch (error: unknown) {
      setSaveError(error instanceof Error ? error.message : '기본정보를 저장하지 못했어요.');
    } finally {
      setSaving(false);
    }
  }

  function handleWithdrawn() {
    signOut();
    navigate('/', { replace: true });
    toast.success('탈퇴되었습니다. 그동안 이용해 주셔서 감사합니다.');
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header
        title={<span aria-label="기본정보 수정">기본정보</span>}
        onBack={() => navigate(-1)}
      />
      <main className="flex flex-1 flex-col overflow-y-auto px-page-x pb-3 pt-8">
        {loadError ? (
          <Card title="기본정보를 불러오지 못했어요">{loadError}</Card>
        ) : !profile ? (
          <div
            role="status"
            aria-label="기본정보 불러오는 중"
            className="min-h-44 animate-pulse rounded-card bg-muted-bg"
          />
        ) : (
          <>
            <h2 className="text-2xl font-bold text-foreground">내 정보</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              영양 성분 기준과 알림에 사용됩니다.
            </p>
            <form className="mt-8 flex flex-col gap-4" onSubmit={save}>
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
              <button
                type="button"
                className="flex min-h-control w-full items-center justify-between rounded-card border border-input bg-card px-4 text-left text-sm font-medium text-foreground transition-colors hover:bg-muted-bg"
                onClick={() => setPasswordSheetOpen(true)}
              >
                <span>비밀번호 변경</span>
                <ChevronRight aria-hidden className="size-5 text-muted-foreground" />
              </button>
              <Button
                type="submit"
                aria-label="저장"
                disabled={!changed || saving}
                className="mt-[68px]"
              >
                변경사항 저장
              </Button>
            </form>
            <button
              type="button"
              className="mt-2 min-h-touch w-full text-center text-sm font-medium text-danger-strong"
              onClick={() => setWithdrawDialogOpen(true)}
            >
              회원 탈퇴
            </button>
          </>
        )}
      </main>

      <BottomTabbar
        active="my"
        onChange={(key) => navigate(TAB_ROUTES[key])}
        className="border-t border-border"
      />

      <PasswordChangeSheet open={passwordSheetOpen} onOpenChange={setPasswordSheetOpen} />
      <WithdrawAccountDialog
        open={withdrawDialogOpen}
        onOpenChange={setWithdrawDialogOpen}
        onWithdrawn={handleWithdrawn}
      />
      <ErrorDialog
        open={saveError !== null}
        title="기본정보를 저장하지 못했어요"
        message={saveError ?? ''}
        onRetry={() => void save()}
      />
    </div>
  );
}
