import { BrowserRouter, Route, Routes } from 'react-router';
import { AuthPage } from '@/pages/auth';
import { ChatPage } from '@/pages/chat';
import { DocumentConfirmPage } from '@/pages/document-confirm';
import { DocumentUploadPage } from '@/pages/document-upload';
import { MedicationSchedulePage } from '@/pages/medication-schedule';
import { OcrReviewPage } from '@/pages/ocr-review';
import { HomePage } from '@/pages/home';
import { SplashPage } from '@/pages/splash';
import { SupplementsPage } from '@/pages/supplements';
import { DevGallery } from './DevGallery';

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
        <Route path="/dev/gallery" element={<DevGallery />} />
        <Route path="/dev/document-upload" element={<DocumentUploadPage />} />
        <Route path="/dev/document-confirm" element={<DocumentConfirmPage />} />
        <Route path="/dev/ocr-review" element={<OcrReviewPage />} />
        <Route path="/dev/medication-schedule" element={<MedicationSchedulePage />} />
        <Route path="/dev/chat" element={<ChatPage />} />
        <Route path="/dev/supplements" element={<SupplementsPage />} />
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
