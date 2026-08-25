import { useState } from 'react';
import { UserRound } from 'lucide-react';
import {
  BottomTabbar,
  Button,
  Card,
  CheckboxField,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  Header,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  StatusBadge,
  Switch,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  type TabKey,
} from '@/shared/ui';

/**
 * 컴포넌트 확인용 갤러리 화면입니다. 라우트 "/dev/gallery"에 연결되어 있습니다.
 * `pnpm dev` 후 모든 컴포넌트가 디자인 토큰 색으로 잘 나오는지 눈으로 확인하는 용도입니다.
 */
export function DevGallery() {
  const [tab, setTab] = useState<TabKey>('home');
  const [agree, setAgree] = useState(true);
  const [optIn, setOptIn] = useState(false);
  const [confirmLowConfidence, setConfirmLowConfidence] = useState(false);
  const [medAlarm, setMedAlarm] = useState(true);
  const [authTab, setAuthTab] = useState('login');

  return (
    <div className="min-h-dvh bg-background py-8">
      <div className="mx-auto flex w-full max-w-app flex-col overflow-hidden rounded-card border border-border bg-background shadow-card">
        <Header title="컴포넌트 확인" right={<UserRound aria-hidden className="size-5" />} />

        <main className="flex flex-1 flex-col gap-2.5 px-page-x py-4">
          <p className="text-sm text-muted-foreground">
            디자인 토큰이 적용된 상태인지 확인하는 화면입니다.
          </p>

          <Card tone="info" title="오늘의 복약" onClick={() => alert('복약 안내로 이동')}>
            08:00 · 셀레콕시브 200mg
            <br />
            20:00 · 셀레콕시브 200mg · 리바록사반 10mg
            <br />
            필요 시 · 아세트아미노펜 650mg
          </Card>

          <Card title="다음 일정" onClick={() => alert('일정 화면으로 이동')}>
            D-2 · 8월 13일 14:00 · 재활 · 재활센터 1층
            <br />
            D-7 · 8월 18일 10:30 · 진료 · 정형외과 본관 2층
          </Card>

          <Card
            title="우측 인공슬관절 전치환술"
            titleRight={<StatusBadge type="active" />}
          >
            활성 08.10–08.24 · 퇴원 후 1일째
          </Card>

          <Card tone="warning" title="즉시 연락할 증상">
            열 38℃ 이상 · 수술 부위 붉어짐·고름 · 종아리가 붓고 아픔 · 갑작스러운 호흡곤란
            <br />이 중 하나라도 있으면 즉시 병원에 연락하세요.
          </Card>

          <div className="flex flex-wrap gap-2 py-1">
            <StatusBadge type="new" />
            <StatusBadge type="stopped" />
            <StatusBadge type="dose" />
            <StatusBadge type="frequency" />
            <StatusBadge type="review" />
            <StatusBadge type="done" />
          </div>

          <Input label="이메일" placeholder="patient@example.com" />
          <Input
            label="비밀번호"
            type="password"
            placeholder="영문·숫자 포함 8자 이상"
            error="비밀번호가 일치하지 않습니다."
          />

          {/* CheckboxField — shadcn Checkbox + 라벨/설명/(필수·선택) 표기 래퍼 */}
          <Card title="개인정보 처리 동의">
            <div className="flex flex-col">
              {/* 1) label만 */}
              <CheckboxField checked={agree} onCheckedChange={setAgree} label="동의합니다" required />
              {/* 2) label + description */}
              <CheckboxField
                checked={optIn}
                onCheckedChange={setOptIn}
                label="AI 이용에 동의합니다"
                description="업로드한 문서는 복약·생활관리 안내를 만드는 데만 사용되고, 다른 목적으로 공유되지 않아요."
                required
              />
              {/* 3) 선택 항목 */}
              <CheckboxField
                checked={confirmLowConfidence}
                onCheckedChange={setConfirmLowConfidence}
                label="알림 수신에 동의합니다"
                required={false}
              />
            </div>
          </Card>

          {/* shadcn/ui Switch — label/description 행은 화면에서 직접 구성합니다. */}
          <div className="flex min-h-touch items-center justify-between gap-3 rounded-card border border-border bg-card px-3.5 py-2.5">
            <div className="min-w-0">
              <label htmlFor="med-alarm" className="block text-sm font-bold text-foreground">
                복약 알림
              </label>
              <p className="text-sm text-muted-foreground">설정한 복용 시각에 알려드려요.</p>
            </div>
            <Switch id="med-alarm" checked={medAlarm} onCheckedChange={setMedAlarm} />
          </div>

          {/* shadcn/ui Tabs — 로그인/회원가입 탭 전환(REQ-USER-002)에서 쓸 예정 */}
          <Tabs value={authTab} onValueChange={setAuthTab}>
            <TabsList>
              <TabsTrigger value="login">로그인</TabsTrigger>
              <TabsTrigger value="signup">회원가입</TabsTrigger>
            </TabsList>
            <TabsContent value="login" className="pt-2 text-sm text-muted-foreground">
              로그인 탭 내용 자리입니다.
            </TabsContent>
            <TabsContent value="signup" className="pt-2 text-sm text-muted-foreground">
              회원가입 탭 내용 자리입니다.
            </TabsContent>
          </Tabs>

          {/* shadcn/ui Select */}
          <Select defaultValue="rehab">
            <SelectTrigger>
              <SelectValue placeholder="일정 종류 선택" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="rehab">재활</SelectItem>
              <SelectItem value="checkup">진료</SelectItem>
              <SelectItem value="test">검사</SelectItem>
            </SelectContent>
          </Select>

          {/* shadcn/ui Dialog */}
          <Dialog>
            <DialogTrigger asChild>
              <Button variant="secondary">낮은 신뢰도 항목 확인 모달 열기</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>확인이 필요해요</DialogTitle>
                <DialogDescription>
                  일부 항목은 인식 결과가 정확하지 않을 수 있어요. 내용을 확인하고 저장해주세요.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button>확인했어요</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          <div className="flex flex-col gap-2 pt-2">
            <Button onClick={() => alert('primary')}>저장하기</Button>
            <Button variant="secondary" onClick={() => alert('secondary')}>
              다시 촬영 · 재업로드
            </Button>
            <Button disabled>필수 항목을 확인해주세요</Button>
          </div>
        </main>

        <BottomTabbar active={tab} onChange={setTab} />
      </div>
    </div>
  );
}
