import { BrowserRouter, Route, Routes } from 'react-router';
import { ChatPage } from '@/pages/chat';
import { DocumentConfirmPage } from '@/pages/document-confirm';
import { DocumentUploadPage } from '@/pages/document-upload';
import { MedicationSchedulePage } from '@/pages/medication-schedule';
import { OcrReviewPage } from '@/pages/ocr-review';
import { DevGallery } from './DevGallery';

/**
 * "/" 는 실제 진입 분기(user.status_code → pending: 문서 등록 흐름 / active: 홈)가
 * 들어갈 자리입니다. 이 로직은 요구사항정의서 기준으로 별도 작업에서 구현하며,
 * 지금은 추측해서 만들지 않고 자리만 비워둡니다.
 */
function RootEntryPlaceholder() {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-background px-page-x text-center">
      <p className="text-sm text-muted-foreground">
        앱 진입 분기(user.status_code 기준) 자리입니다. 아직 구현 전입니다.
        <br />
        화면 확인은 /dev/* 라우트를 이용하세요.
      </p>
    </div>
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
      <Routes>
        <Route path="/" element={<RootEntryPlaceholder />} />
        <Route path="/dev/gallery" element={<DevGallery />} />
        <Route path="/dev/document-upload" element={<DocumentUploadPage />} />
        <Route path="/dev/document-confirm" element={<DocumentConfirmPage />} />
        <Route path="/dev/ocr-review" element={<OcrReviewPage />} />
        <Route path="/dev/medication-schedule" element={<MedicationSchedulePage />} />
        <Route path="/dev/chat" element={<ChatPage />} />
      </Routes>
    </BrowserRouter>
  );
}
