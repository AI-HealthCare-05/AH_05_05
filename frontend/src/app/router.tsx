import { BrowserRouter, Route, Routes } from 'react-router';
import { AuthPage } from '@/pages/auth';
import { ChatPage } from '@/pages/chat';
import { DocumentUploadPage } from '@/pages/document-upload';
import { MedicationSchedulePage } from '@/pages/medication-schedule';
import { MedicationsPage } from '@/pages/medications';
import { MyPage } from '@/pages/my';
import { OcrReviewPage } from '@/pages/ocr-review';
import { HomePage } from '@/pages/home';
import { SplashPage } from '@/pages/splash';
import { SupplementsPage } from '@/pages/supplements';
import { mockSupplementsWithThreeExceeded } from '@/entities/supplement';
import { mockMedicationScheduleWithAutoAssigned } from '@/entities/medication';
import { DevGallery } from './DevGallery';

const THREE_EXCEEDED_SUPPLEMENTS = mockSupplementsWithThreeExceeded();
const AUTO_ASSIGNED_MEDICATION_SCHEDULE = mockMedicationScheduleWithAutoAssigned();

/**
 * react-router v7, declarative mode (<BrowserRouter>/<Routes>/<Route>).
 *
 * 실제 화면(REQ 페이지)이 만들어지는 대로 pages/* 를 이 파일에 등록하세요.
 * 로그인 없이 화면을 바로 열어보는 개발용 라우트는 "/dev/*" 아래에 추가합니다.
 */
export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<SplashPage />} />
        <Route path="/home" element={<HomePage />} />
        <Route path="/login" element={<AuthPage />} />
        <Route path="/supplements" element={<SupplementsPage />} />
        <Route path="/document-upload" element={<DocumentUploadPage />} />
        <Route path="/ocr-review" element={<OcrReviewPage />} />
        <Route path="/medication-schedule" element={<MedicationSchedulePage />} />
        <Route path="/medications" element={<MedicationsPage />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/my" element={<MyPage />} />
        <Route path="/dev/gallery" element={<DevGallery />} />
        <Route path="/dev/document-upload" element={<DocumentUploadPage />} />
        <Route path="/dev/ocr-review" element={<OcrReviewPage />} />
        <Route path="/dev/medication-schedule" element={<MedicationSchedulePage />} />
        <Route
          path="/dev/medication-schedule-auto-assigned"
          element={
            <MedicationSchedulePage scheduleOverride={AUTO_ASSIGNED_MEDICATION_SCHEDULE} />
          }
        />
        <Route path="/dev/medications" element={<MedicationsPage />} />
        <Route path="/dev/chat" element={<ChatPage />} />
        <Route path="/dev/my-guest" element={<MyPage authenticatedOverride={false} />} />
        <Route path="/dev/my-authenticated" element={<MyPage authenticatedOverride />} />
        <Route path="/dev/supplements" element={<SupplementsPage />} />
        <Route
          path="/dev/supplements-three-exceeded"
          element={<SupplementsPage supplementsOverride={THREE_EXCEEDED_SUPPLEMENTS} />}
        />
        <Route path="/dev/home-empty" element={<HomePage authenticatedOverride />} />
        <Route
          path="/dev/home-active"
          element={<HomePage authenticatedOverride medicationState="active" />}
        />
        <Route
          path="/dev/home-ended"
          element={<HomePage authenticatedOverride medicationState="ended" />}
        />
      </Routes>
    </BrowserRouter>
  );
}
