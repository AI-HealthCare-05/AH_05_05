import { LegalDocumentPage, LegalList, LegalSection } from './LegalDocumentPage';

/**
 * 개인정보 보호법 제30조와 개인정보보호위원회 작성지침을 바탕으로 한 서비스 안내 초안.
 * 실제 배포 전 수탁자, 국외 이전, 법정 보유기간과 파기 절차가 운영 환경과 일치하는지
 * 개인정보 보호 담당자 및 법률 전문가의 검토를 거쳐야 합니다.
 */
export function PrivacyPage() {
  return (
    <LegalDocumentPage
      title="개인정보 처리 안내"
      description="RxVita는 서비스 제공에 필요한 범위에서 개인정보를 처리하고 안전하게 보호하기 위해 노력합니다."
    >
      <LegalSection title="1. 개인정보 보호책임자">
        <dl className="grid grid-cols-[6rem_1fr] gap-x-3 gap-y-1">
          <dt>성명</dt>
          <dd className="text-foreground">김은미</dd>
          <dt>소속</dt>
          <dd className="text-foreground">Data Protection&Privacy</dd>
          <dt>문의 이메일</dt>
          <dd>
            <a className="font-semibold text-primary underline" href="mailto:blesseunmi@gmail.com">
              blesseunmi@gmail.com
            </a>
          </dd>
        </dl>
      </LegalSection>

      <LegalSection title="2. 처리 목적">
        <LegalList>
          <li>회원 가입, 본인 식별, 로그인 및 계정 관리</li>
          <li>처방약·영양제 등록, 복용 일정 및 알림 제공</li>
          <li>약봉투 OCR 처리와 이용자 최종 확인값 저장</li>
          <li>등록된 복약 정보를 참고하는 AI 챗봇 답변 제공</li>
          <li>서비스 안정성 확보, 오류 분석 및 부정 이용 방지</li>
          <li>문의 대응과 중요 서비스 안내</li>
        </LegalList>
      </LegalSection>

      <LegalSection title="3. 처리하는 개인정보 항목">
        <LegalList>
          <li>회원정보: 이메일, 암호화된 비밀번호, 이름, 암호화된 전화번호, 생년월일, 성별</li>
          <li>복약정보: 처방약, 영양제, 복용 시간·기록, 진료 및 추후 방문 정보</li>
          <li>OCR 정보: 업로드한 약봉투 이미지, 추출 결과, 이용자가 수정·확정한 값</li>
          <li>AI 이용정보: 채팅 질문과 답변, 참조자료, 대화 별점</li>
          <li>알림정보: 알림 설정, 예약·발송 이력, Web Push 구독 및 기기 정보</li>
        </LegalList>
        <p className="mt-2">
          건강과 진료에 관한 정보는 민감정보에 해당할 수 있으며, 서비스는 별도 동의를 받은
          목적과 범위 안에서 처리합니다.
        </p>
      </LegalSection>

      <LegalSection title="4. 보유 및 이용 기간">
        <div className="overflow-x-auto rounded-xl border border-border">
          <table aria-label="개인정보 보유기간" className="w-full min-w-[27rem] text-left text-xs">
            <thead className="bg-muted/60 text-foreground">
              <tr>
                <th className="px-3 py-2 font-semibold">처리 항목</th>
                <th className="px-3 py-2 font-semibold">보유 기준</th>
                <th className="px-3 py-2 font-semibold">파기 시점</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              <tr>
                <td className="px-3 py-2">회원·계정정보</td>
                <td className="px-3 py-2">회원 탈퇴 시까지</td>
                <td className="px-3 py-2">탈퇴 처리 후 지체 없이</td>
              </tr>
              <tr>
                <td className="px-3 py-2">복약·진료정보 및 OCR 확정정보</td>
                <td className="px-3 py-2">이용자가 삭제하거나 회원 탈퇴할 때까지</td>
                <td className="px-3 py-2">삭제 요청 또는 탈퇴 처리 후 지체 없이</td>
              </tr>
              <tr>
                <td className="px-3 py-2">AI 채팅 질문·답변 및 별점</td>
                <td className="px-3 py-2">대화 삭제 또는 회원 탈퇴 시까지</td>
                <td className="px-3 py-2">삭제 요청 또는 탈퇴 처리 후 지체 없이</td>
              </tr>
              <tr>
                <td className="px-3 py-2">알림 설정 및 Web Push 구독정보</td>
                <td className="px-3 py-2">구독 해지 또는 회원 탈퇴 시까지</td>
                <td className="px-3 py-2">구독 해지 또는 탈퇴 처리 후 지체 없이</td>
              </tr>
              <tr>
                <td className="px-3 py-2">접속·오류·발송 기록</td>
                <td className="px-3 py-2">처리 목적 달성 또는 관계 법령상 보존기간까지</td>
                <td className="px-3 py-2">보존기간 종료 후 지체 없이</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="mt-2">
          관계 법령에 보존 의무가 있거나 분쟁·부정 이용 대응을 위해 보존이 필요한 경우에는
          해당 근거, 항목 및 기간에 한해 다른 개인정보와 분리하여 보관한 후 파기합니다.
        </p>
      </LegalSection>

      <LegalSection title="5. 외부 서비스 이용 및 처리위탁">
        <p>
          서비스는 기능 제공을 위해 설정된 범위에서 OCR, AI 모델, 이메일 및 Web Push
          사업자의 시스템을 이용할 수 있습니다. 이 경우 필요한 최소 정보만 전달하고 계약과
          접근통제 등을 통해 안전하게 처리하도록 관리합니다. 실제 수탁자, 국외 이전 여부와
          세부 처리 조건은 운영 환경에 맞게 별도로 고지하고 필요한 동의를 받습니다.
        </p>
      </LegalSection>

      <LegalSection title="6. AI 데이터 처리">
        <LegalList>
          <li>
            AI 챗봇 답변을 생성하기 위해 이용자의 질문과 답변, 등록한 처방약·영양제 및 복약
            관련 정보, 이용자가 확정한 OCR 정보와 필요한 참고자료를 처리할 수 있습니다.
          </li>
          <li>
            AI에 전달하는 정보는 답변 생성과 안전성 확인에 필요한 범위로 제한하며, 외부 AI
            서비스가 사용되는 경우 제5조의 처리위탁 및 국외 이전 고지에 따릅니다.
          </li>
          <li>
            챗봇 화면에는 AI가 생성한 답변임을 알리고, 답변은 의료인의 진단·처방·치료를
            대체하지 않는 참고정보로 제공합니다.
          </li>
          <li>
            AI 답변은 이용자에게 법적 효과 또는 중대한 영향을 미치는 자동화된 결정에 사용하지
            않습니다.
          </li>
          <li>
            이용자는 서비스의 대화 관리 기능을 통해 대화를 목록에서 제외할 수 있으며, AI
            대화정보의 열람·삭제 및 처리정지는 개인정보 보호책임자에게 요청할 수 있습니다.
          </li>
        </LegalList>
      </LegalSection>

      <LegalSection title="7. 개인정보의 파기">
        <p>
          보유기간이 끝나거나 처리 목적이 달성된 개인정보는 복구하기 어렵도록 지체 없이
          파기합니다. 전자 파일은 안전한 삭제 방법으로 삭제하고, 출력물은 분쇄 또는 소각하는
          방법으로 파기합니다.
        </p>
      </LegalSection>

      <LegalSection title="8. 이용자의 권리와 행사 방법">
        <p>
          이용자는 자신의 개인정보에 대해 열람, 정정, 삭제, 처리정지 및 동의 철회를 요청할
          수 있습니다. 서비스의 계정·설정 기능을 이용하거나 개인정보 보호 담당자 이메일로
          요청할 수 있으며, 운영자는 본인 확인 후 관계 법령에 따라 처리합니다.
        </p>
      </LegalSection>

      <LegalSection title="9. 안전성 확보 조치">
        <LegalList>
          <li>비밀번호의 단방향 암호화 및 전화번호 등 중요 정보 암호화</li>
          <li>접근권한 최소화와 인증정보 관리</li>
          <li>전송구간 보호, 접속기록 관리 및 보안 점검</li>
          <li>개인정보 처리 시스템과 백업 데이터 보호</li>
        </LegalList>
      </LegalSection>

      <LegalSection title="10. 자동 수집 장치와 알림정보">
        <p>
          로그인 유지와 서비스 제공을 위해 브라우저 저장소 또는 쿠키를 사용할 수 있습니다.
          이용자는 브라우저 설정에서 저장소와 알림 권한을 삭제하거나 거부할 수 있으나 일부
          기능 이용이 제한될 수 있습니다.
        </p>
      </LegalSection>

      <LegalSection title="11. 처리방침 변경">
        <p>
          본 안내가 변경되는 경우 적용일과 변경 내용을 서비스에서 알립니다. 중요한 변경으로
          추가 동의가 필요한 경우에는 별도의 동의를 받습니다.
        </p>
      </LegalSection>
    </LegalDocumentPage>
  );
}
