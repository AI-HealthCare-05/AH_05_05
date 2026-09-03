import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from 'react-router';
import { AuthPage } from '@/pages/auth';
import { ChatPage } from '@/pages/chat';
import { DocumentUploadPage } from '@/pages/document-upload';
import { MedicationAlarmTimesPage, MedicationSchedulePage } from '@/pages/medication-schedule';
import { MedicationsPage } from '@/pages/medications';
import {
  FollowUpVisitsPage,
  MyPage,
  MyProfilePage,
} from '@/pages/my';
import { OcrReviewPage } from '@/pages/ocr-review';
import { HomePage } from '@/pages/home';
import { PrivacyPage, TermsPage } from '@/pages/legal';
import { SplashPage } from '@/pages/splash';
import {
  SupplementProductPage,
  SupplementsPage,
  type NutrientStandardProfile,
} from '@/pages/supplements';
import { mockSupplementsWithThreeExceeded } from '@/entities/supplement';
import type { AccountProfile, UpdateAccountProfilePayload } from '@/entities/account';
import type { ChatMessage, ChatSessionSummary, SendChatResult } from '@/entities/chat';
import {
  mockMedicationOverview,
  mockMedicationOverviews,
  mockMedicationScheduleWithAutoAssigned,
  type DoseRecord,
  type MedicationOverview,
  type SaveDoseTakenPayload,
} from '@/entities/medication';
import { registerPushNotifications } from '@/shared/push/register';
import { DevGallery } from './DevGallery';
import { ChatSessionProvider } from './ChatSessionContext';
import { useSession } from './SessionContext';

const THREE_EXCEEDED_SUPPLEMENTS = mockSupplementsWithThreeExceeded();
const EXISTING_CHAT_HISTORY: ChatMessage[] = [
  { role: 'user', text: '이전에 물어본 질문이에요.', sources: [] },
  {
    role: 'assistant',
    text: '이전에 받은 답변이에요.',
    sources: [{ scope: 'official', title: 'e약은요', organization: '식품의약품안전처' }],
  },
];
const DEV_NUTRIENT_PROFILE: NutrientStandardProfile = {
  birthDate: '2000-08-25',
  gender: 'male',
  maskedName: '김*훈',
};
const MISSING_NUTRIENT_PROFILE: NutrientStandardProfile = {
  birthDate: null,
  gender: null,
  maskedName: '김*훈',
};
const AUTO_ASSIGNED_MEDICATION_SCHEDULE = mockMedicationScheduleWithAutoAssigned();
const ACTIVE_MEDICATION_OVERVIEW = mockMedicationOverview();
const MULTIPLE_MEDICATION_OVERVIEWS = mockMedicationOverviews();
const MANY_MEDICATION_OVERVIEWS: MedicationOverview[] = Array.from({ length: 41 }, (_, index) => {
  const startDate = new Date(2026, 7, 24);
  startDate.setDate(startDate.getDate() - index);
  const date = [
    startDate.getFullYear(),
    String(startDate.getMonth() + 1).padStart(2, '0'),
    String(startDate.getDate()).padStart(2, '0'),
  ].join('-');
  return {
    ...ACTIVE_MEDICATION_OVERVIEW,
    recordId: 1_000 + index,
    start: { ...ACTIVE_MEDICATION_OVERVIEW.start, date },
    endDate: date,
    daysRemaining: 0,
    isFinished: true,
    medications: ACTIVE_MEDICATION_OVERVIEW.medications.map((medication) => ({
      ...medication,
      medicationId: medication.medicationId + index * 100,
    })),
  };
});
const EMPTY_MEDICATION_OVERVIEW: MedicationOverview = {
  ...ACTIVE_MEDICATION_OVERVIEW,
  medications: [],
};
const ENDED_MEDICATION_OVERVIEW: MedicationOverview = {
  ...ACTIVE_MEDICATION_OVERVIEW,
  daysRemaining: 0,
  isFinished: true,
};
const ONE_MEDICATION_OVERVIEW: MedicationOverview = {
  ...ACTIVE_MEDICATION_OVERVIEW,
  endDate: '2026-08-28',
  medications: [
    {
      ...ACTIVE_MEDICATION_OVERVIEW.medications[0],
      slots: ['morning'],
    },
  ],
};
const FOURTEEN_DAY_MEDICATION_OVERVIEW: MedicationOverview = {
  ...ACTIVE_MEDICATION_OVERVIEW,
  endDate: '2026-09-04',
  daysRemaining: 11,
  medications: ACTIVE_MEDICATION_OVERVIEW.medications.map((medication) => ({
    ...medication,
    days: 14,
  })),
};
const CROSS_YEAR_MEDICATION_OVERVIEW: MedicationOverview = {
  ...ACTIVE_MEDICATION_OVERVIEW,
  recordId: 36,
  start: { date: '2026-12-28', slot: 'morning' },
  endDate: '2027-01-03',
  daysRemaining: 7,
  isFinished: false,
};

const loadEmptyMedicationOverview = async () => EMPTY_MEDICATION_OVERVIEW;
const loadEndedMedicationOverview = async () => ENDED_MEDICATION_OVERVIEW;
const loadActiveMedicationOverview = async () => ACTIVE_MEDICATION_OVERVIEW;
const loadOneMedicationOverview = async () => ONE_MEDICATION_OVERVIEW;
const loadFourteenDayMedicationOverview = async () => FOURTEEN_DAY_MEDICATION_OVERVIEW;
const loadMultipleMedicationOverviews = async () => MULTIPLE_MEDICATION_OVERVIEWS;
const loadManyMedicationOverviews = async () => MANY_MEDICATION_OVERVIEWS;
const loadCrossYearMedicationOverviews = async () => [CROSS_YEAR_MEDICATION_OVERVIEW];
const failMedicationOverview = async (): Promise<MedicationOverview> => {
  throw new Error('잠시 후 다시 시도해주세요.');
};
const failDoseRecordSave = async (_payload: SaveDoseTakenPayload): Promise<DoseRecord> => {
  throw new Error('기록하지 못했어요. 다시 시도해주세요.');
};
const failProfileSave = async (
  _payload: UpdateAccountProfilePayload,
): Promise<AccountProfile> => {
  throw new Error('잠시 후 다시 시도해주세요.');
};
const failMedicationScheduleSave = async (): Promise<never> => {
  throw new Error('잠시 후 다시 시도해주세요.');
};
const loadExistingChatHistory = async () => EXISTING_CHAT_HISTORY;
const failChatHistory = async (): Promise<ChatMessage[]> => {
  throw new Error('잠시 후 다시 시도해주세요.');
};
const failChatSessionList = async (): Promise<ChatSessionSummary[]> => {
  throw new Error('잠시 후 다시 시도해주세요.');
};
const failChatSessionDelete = async (_sessionIds: readonly number[]): Promise<void> => {
  throw new Error('잠시 후 다시 시도해주세요.');
};
const sendChatWithoutStoredHistory = async (): Promise<SendChatResult> => ({
  conversationId: 9901,
  messageId: 9902,
  answer: '실제 전송 API에서 받은 답변이에요.',
  sources: [],
});
const failChatSessionHistory = async (_sessionId: number): Promise<ChatMessage[]> => {
  throw new Error('대화 이력 API가 아직 준비되지 않았어요.');
};

function RequireAuthentication() {
  const { authenticated, principalKey } = useSession();
  const location = useLocation();
  return authenticated && principalKey ? (
    <Outlet />
  ) : (
    <Navigate
      to="/login"
      replace
      state={{ from: `${location.pathname}${location.search}${location.hash}` }}
    />
  );
}

/**
 * react-router v7, declarative mode (<BrowserRouter>/<Routes>/<Route>).
 *
 * 실제 화면(REQ 페이지)이 만들어지는 대로 pages/* 를 이 파일에 등록하세요.
 * 로그인 없이 화면을 바로 열어보는 개발용 라우트는 "/dev/*" 아래에 추가합니다.
 */
export function AppRouter() {
  return (
    <BrowserRouter>
      <ChatSessionProvider>
        <Routes>
        <Route path="/" element={<SplashPage />} />
        <Route path="/home" element={<HomePage />} />
        <Route path="/login" element={<AuthPage />} />
        <Route path="/terms" element={<TermsPage />} />
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route element={<RequireAuthentication />}>
          <Route path="/supplements" element={<SupplementsPage />} />
          <Route path="/supplements/product/:productId" element={<SupplementProductPage />} />
          <Route path="/document-upload" element={<DocumentUploadPage />} />
          <Route path="/ocr-review" element={<OcrReviewPage />} />
          <Route path="/medication-schedule" element={<MedicationSchedulePage />} />
          <Route path="/medication-alarm-times" element={<MedicationAlarmTimesPage />} />
          <Route path="/medications" element={<MedicationsPage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/my" element={<MyPage />} />
          <Route path="/my/profile" element={<MyProfilePage />} />
          <Route path="/my/visits" element={<FollowUpVisitsPage />} />
        </Route>
        <Route path="/dev/gallery" element={<DevGallery />} />
        <Route path="/dev/document-upload" element={<DocumentUploadPage />} />
        <Route path="/dev/ocr-review" element={<OcrReviewPage />} />
        <Route
          path="/dev/medication-schedule"
          element={
            <MedicationSchedulePage defaultRecordId={12} />
          }
        />
        <Route
          path="/dev/medication-schedule-save-error"
          element={
            <MedicationSchedulePage
              defaultRecordId={12}
              scheduleSaver={failMedicationScheduleSave}
            />
          }
        />
        <Route
          path="/dev/medication-schedule-no-vapid"
          element={
            <MedicationSchedulePage
              defaultRecordId={12}
              pushRegistrar={() => registerPushNotifications('')}
            />
          }
        />
        <Route path="/dev/medication-alarm-times" element={<MedicationAlarmTimesPage />} />
        <Route
          path="/dev/medication-schedule-auto-assigned"
          element={
            <MedicationSchedulePage scheduleOverride={AUTO_ASSIGNED_MEDICATION_SCHEDULE} />
          }
        />
        <Route path="/dev/medications" element={<MedicationsPage />} />
        <Route
          path="/dev/medications-many"
          element={<MedicationsPage overviewsLoader={loadManyMedicationOverviews} />}
        />
        <Route
          path="/dev/medications-cross-year"
          element={<MedicationsPage overviewsLoader={loadCrossYearMedicationOverviews} />}
        />
        <Route path="/dev/chat" element={<ChatPage />} />
        <Route
          path="/dev/chat-history"
          element={<ChatPage historyLoader={loadExistingChatHistory} />}
        />
        <Route
          path="/dev/chat-history-error"
          element={<ChatPage historyLoader={failChatHistory} />}
        />
        <Route
          path="/dev/chat-session-list-error"
          element={<ChatPage sessionListLoader={failChatSessionList} />}
        />
        <Route
          path="/dev/chat-delete-error"
          element={<ChatPage sessionDeleter={failChatSessionDelete} />}
        />
        <Route
          path="/dev/chat-send-without-history"
          element={
            <ChatPage
              sessionListLoader={failChatSessionList}
              sessionHistoryLoader={failChatSessionHistory}
              chatSender={sendChatWithoutStoredHistory}
            />
          }
        />
        <Route path="/dev/my-guest" element={<MyPage authenticatedOverride={false} />} />
        <Route
          path="/dev/my-authenticated"
          element={<MyPage authenticatedOverride />}
        />
        <Route path="/dev/my-profile" element={<MyProfilePage />} />
        <Route path="/dev/my-visits" element={<FollowUpVisitsPage />} />
        <Route
          path="/dev/my-profile-save-error"
          element={<MyProfilePage profileSaver={failProfileSave} />}
        />
        <Route
          path="/dev/supplements"
          element={<SupplementsPage profileOverride={DEV_NUTRIENT_PROFILE} />}
        />
        <Route
          path="/dev/supplements/product/:productId"
          element={<SupplementProductPage />}
        />
        <Route
          path="/dev/supplements-profile-missing"
          element={<SupplementsPage profileOverride={MISSING_NUTRIENT_PROFILE} />}
        />
        <Route
          path="/dev/supplements-three-exceeded"
          element={
            <SupplementsPage
              supplementsOverride={THREE_EXCEEDED_SUPPLEMENTS}
              profileOverride={DEV_NUTRIENT_PROFILE}
            />
          }
        />
        <Route
          path="/dev/home-empty"
          element={<HomePage authenticatedOverride medicationState="empty" />}
        />
        <Route
          path="/dev/home-active"
          element={
            <HomePage
              authenticatedOverride
              medicationState="active"
              medicationOverviewLoader={loadActiveMedicationOverview}
            />
          }
        />
        <Route
          path="/dev/home-multiple-episodes"
          element={
            <HomePage
              authenticatedOverride
              medicationOverviewsLoader={loadMultipleMedicationOverviews}
            />
          }
        />
        <Route
          path="/dev/home-one-medication"
          element={
            <HomePage
              authenticatedOverride
              medicationOverviewLoader={loadOneMedicationOverview}
            />
          }
        />
        <Route
          path="/dev/home-14-days"
          element={
            <HomePage
              authenticatedOverride
              medicationOverviewLoader={loadFourteenDayMedicationOverview}
            />
          }
        />
        <Route
          path="/dev/home-dose-save-error"
          element={
            <HomePage
              authenticatedOverride
              medicationState="active"
              medicationOverviewLoader={loadActiveMedicationOverview}
              doseRecordSaver={failDoseRecordSave}
            />
          }
        />
        <Route
          path="/dev/home-ended"
          element={<HomePage authenticatedOverride medicationState="ended" />}
        />
        <Route
          path="/dev/home-data-empty"
          element={
            <HomePage
              authenticatedOverride
              medicationOverviewLoader={loadEmptyMedicationOverview}
            />
          }
        />
        <Route
          path="/dev/home-data-ended"
          element={
            <HomePage
              authenticatedOverride
              medicationOverviewLoader={loadEndedMedicationOverview}
            />
          }
        />
        <Route
          path="/dev/home-load-error"
          element={
            <HomePage authenticatedOverride medicationOverviewLoader={failMedicationOverview} />
          }
        />
        </Routes>
      </ChatSessionProvider>
    </BrowserRouter>
  );
}
