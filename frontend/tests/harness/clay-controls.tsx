import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Button } from '../../src/shared/ui/Button';
import { HomeSectionTabs } from '../../src/pages/home/HomePage';
import { TimeSlotNavigator } from '../../src/pages/home/TimeSlotNavigator';
import '../../src/app/styles/index.css';

function SlotInput({ slot }: { slot: string }) {
  const [value, setValue] = useState('');
  return <input aria-label={`${slot} 메모`} value={value} onChange={event => setValue(event.target.value)} className="w-full rounded-input border p-3" />;
}

function Harness() {
  const [active, setActive] = useState<'medication' | 'supplement'>('medication');
  const [count, setCount] = useState(0);
  return <main className="mx-auto flex max-w-app flex-col gap-5 p-5">
    <h1 className="text-xl font-bold">공통 컨트롤 검증</h1>
    <div role="group" aria-label="저장 작업" className="grid grid-cols-2 gap-3">
      <Button variant="secondary" onClick={() => setCount(count - 1)}>취소</Button>
      <Button onClick={() => setCount(count + 1)}>저장</Button>
    </div>
    <div role="group" aria-label="비활성 작업" className="grid grid-cols-2 gap-3">
      <Button variant="secondary" disabled onClick={() => setCount(999)}>취소 불가</Button>
      <Button disabled onClick={() => setCount(999)}>저장 불가</Button>
    </div>
    <div role="group" aria-label="선택형 control" className="grid grid-cols-2 gap-2">
      <button type="button" aria-pressed="true" className="min-h-touch rounded-input bg-primary px-4 text-card">
        선택됨
      </button>
      <button type="button" aria-pressed="false" className="min-h-touch rounded-input bg-card px-4 text-muted-foreground">
        선택 안 됨
      </button>
    </div>
    <Button variant="danger">삭제</Button>
    <output aria-label="작업 횟수">{count}</output>
    <HomeSectionTabs activeTab={active} onChange={setActive} />
    <p>선택: {active}</p>
    <TimeSlotNavigator items={[{slot:'morning'},{slot:'lunch'},{slot:'evening'},{slot:'bedtime'}]} initialSlot="morning" label="복약">
      {item => <SlotInput slot={item.slot} />}
    </TimeSlotNavigator>
    <TimeSlotNavigator items={[{slot:'morning'},{slot:'evening'}]} initialSlot="morning" label="영양제">
      {item => <p>{item.slot} 영양제</p>}
    </TimeSlotNavigator>
  </main>;
}
createRoot(document.getElementById('root')!).render(<Harness />);
