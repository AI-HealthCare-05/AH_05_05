import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Button } from '../../src/shared/ui/Button';
import { Card } from '../../src/shared/ui/Card';
import { Checkbox } from '../../src/shared/ui/checkbox';
import { Dialog, DialogTrigger, DialogContent, DialogTitle, DialogDescription } from '../../src/shared/ui/dialog';
import { Switch } from '../../src/shared/ui/switch';
import '../../src/app/styles/index.css';
function Harness() {
 const [pending,setPending]=useState(false);
 const [programmaticOpen,setProgrammaticOpen]=useState(false);
 return <main className="mx-auto flex max-w-app flex-col gap-4 p-5">
 <h1>UI 검증 전용 · 실제 저장 없음</h1>
 <Button fullWidth={false} loading={pending} onClick={()=>setPending(true)}>저장</Button>
 <Button variant="secondary" onClick={()=>setPending(false)}>테스트 요청 종료</Button>
 <Button variant="danger" fullWidth={false}>삭제</Button>
 <Card title="표면 깊이">밝은 윗면과 부드러운 아랫면을 검증합니다.</Card>
 <Card title="눌리는 표면" onClick={()=>undefined}>카드의 짧은 눌림을 검증합니다.</Card>
 <label className="flex min-h-touch items-center gap-3"><Checkbox />동의</label>
 <label className="flex min-h-touch items-center gap-3"><Switch />알림</label>
 {(['dialog','sheet'] as const).map(variant=><Dialog key={variant}><DialogTrigger asChild><Button variant="secondary">{variant==='dialog'?'확인창 열기':'시트 열기'}</Button></DialogTrigger><DialogContent variant={variant}><DialogTitle>{variant==='dialog'?'확인창':'시트'}</DialogTitle><DialogDescription>기존 포커스와 닫기 동작을 확인합니다.</DialogDescription><input aria-label="메모" /><Button>확인</Button></DialogContent></Dialog>)}
 <Button variant="secondary" onClick={()=>setProgrammaticOpen(true)}>알림 시간 설정 열기</Button>
 <Dialog open={programmaticOpen} onOpenChange={setProgrammaticOpen}><DialogContent variant="sheet"><DialogTitle>알림 시간 설정</DialogTitle><DialogDescription>트리거 없이 제어되는 실제 시트 패턴입니다.</DialogDescription><input aria-label="알림 메모" /><Button onClick={()=>setProgrammaticOpen(false)}>확인</Button></DialogContent></Dialog>
 </main>;
}
createRoot(document.getElementById('root')!).render(<Harness/>);
