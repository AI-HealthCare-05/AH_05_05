import { Sparkles } from 'lucide-react';
import { DrawnArrow } from '@/shared/ui/DrawnArrow';
import { useNavigate } from 'react-router';

import { Button } from '@/shared/ui/Button';

export function OfficialChallengeComingSoonPage({ feature }: { feature: 'tailored' | 'personal' }) {
  const navigate = useNavigate();
  const label = feature === 'tailored' ? '맞춤 챌린지' : '나만의 챌린지';
  return (
    <main className="flex flex-col gap-4 px-page-x py-5">
      <header className="flex items-center gap-3">
        <button type="button" aria-label="뒤로 가기" onClick={() => navigate('/challenges/browse')} className="flex size-11 shrink-0 items-center justify-center rounded-pill"><DrawnArrow direction="left" className="size-5" /></button>
        <p className="text-caption font-bold text-primary">{label}</p>
      </header>
      <section className="flex min-h-64 flex-col items-center justify-center gap-3 rounded-card bg-card p-5 text-center shadow-card">
        <Sparkles aria-hidden className="size-11 text-primary" />
        <h1 className="text-[22px] font-bold text-foreground">준비 중이에요</h1>
        <p className="text-sm leading-6 text-muted-foreground">내 기록을 안전하게 연결한 뒤 #315에서 제공할 예정이에요.</p>
        <Button variant="secondary" onClick={() => navigate('/challenges/browse')}>공식 챌린지 둘러보기</Button>
      </section>
    </main>
  );
}
