import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import * as UI from '@/shared/ui';
import { ChatFeedbackSheet } from '@/pages/chat/ChatFeedbackSheet';
import '@/app/styles/index.css';

const loadReasons = async () => [{ detailCode: 'P01', detailName: '설명이 이해하기 쉬워요', sortOrder: 1 }];
function Fixture() {
  const [expanded, setExpanded] = useState(false);
  const [revision, setRevision] = useState(0);
  const [open, setOpen] = useState(false);
  const [backs, setBacks] = useState(0);
  const [saves, setSaves] = useState(0);
  const [ends, setEnds] = useState(0);
  return <main className="mx-auto max-w-app">
    <UI.Header title="화살표 확인" onBack={() => setBacks(value => value + 1)} />
    <section className="flex flex-col gap-5 p-5">
      <button type="button" aria-expanded={expanded} onClick={() => setExpanded(value => !value)}>
        펼치기 <UI.DrawnChevron expanded={expanded} className="inline size-5" />
      </button>
      <button type="button" onClick={() => setRevision(value => value + 1)}>내용 갱신 {revision}</button>
      <button type="button" onClick={() => setOpen(true)}>평가 열기</button>
      <UI.Select defaultValue="morning">
        <UI.SelectTrigger aria-label="시간대"><UI.SelectValue /></UI.SelectTrigger>
        <UI.SelectContent><UI.SelectItem value="morning">아침</UI.SelectItem><UI.SelectItem value="evening">저녁</UI.SelectItem></UI.SelectContent>
      </UI.Select>
      <output aria-label="부수 효과">뒤로 {backs}, 저장 {saves}, 종료 {ends}</output>
    </section>
    <ChatFeedbackSheet open={open} sessionId={101} onOpenChange={setOpen} onFinish={() => {}}
      onEnd={async () => { setEnds(value => value + 1); }} reasonLoader={loadReasons}
      feedbackSaver={async (_id, payload) => { setSaves(value => value + 1); return { sessionId: 101, ...payload }; }} />
  </main>;
}
createRoot(document.getElementById('root')!).render(<Fixture />);
