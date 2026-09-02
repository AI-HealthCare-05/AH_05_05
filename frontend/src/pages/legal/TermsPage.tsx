import { LegalDocumentPage, LegalList, LegalSection } from './LegalDocumentPage';

export function TermsPage() {
  return (
    <LegalDocumentPage
      title="이용약관"
      description="본 약관은 알엑스비타(이하 ‘운영자’)가 제공하는 RxVita 서비스의 이용 조건과 운영자 및 이용자의 권리·의무를 정합니다."
    >
      <LegalSection title="1. 서비스의 목적">
        <p>
          RxVita는 이용자가 처방약과 영양제를 등록하고 복용 일정, 알림 및 관련 정보를
          관리할 수 있도록 돕는 건강정보 관리 서비스입니다.
        </p>
      </LegalSection>

      <LegalSection title="2. 제공하는 기능">
        <LegalList>
          <li>약봉투 OCR을 통한 처방약 정보 등록 및 확인</li>
          <li>처방약·영양제 목록, 복용 일정 및 알림 관리</li>
          <li>등록한 처방약과 영양제 정보를 참고하는 AI 챗봇</li>
          <li>의약품·영양성분 및 공공 참고자료 조회</li>
        </LegalList>
      </LegalSection>

      <LegalSection title="3. AI 챗봇과 의료정보에 관한 중요 안내">
        <LegalList>
          <li>
            AI 챗봇의 답변은 이용자가 등록한 처방약과 영양제 정보 및 서비스가 제공하는
            참고자료를 기반으로 생성됩니다.
          </li>
          <li>
            AI 답변에는 부정확하거나 최신 상황과 다른 내용이 포함될 수 있으며, 의료인의
            진단·처방·치료를 대체하지 않습니다.
          </li>
          <li>
            이용자는 약의 복용 시작·중단·용량 변경을 AI 답변만으로 결정해서는 안 되며,
            의사 또는 약사와 상담해야 합니다.
          </li>
          <li>
            호흡곤란, 의식 저하, 심한 알레르기 반응 등 응급상황에서는 서비스를 이용하지
            말고 즉시 119 또는 가까운 응급의료기관에 연락해야 합니다.
          </li>
        </LegalList>
      </LegalSection>

      <LegalSection title="4. 회원가입, 계정 및 탈퇴">
        <LegalList>
          <li>
            이용계약은 이용자가 필수 안내와 동의사항을 확인하고 가입하면 성립합니다.
          </li>
          <li>
            이용자는 본인의 정확한 정보를 등록하고 비밀번호 등 계정정보가 타인에게 노출되지
            않도록 관리해야 합니다.
          </li>
          <li>
            이용자는 서비스에서 제공하는 탈퇴 기능을 통해 언제든지 이용계약을 해지할 수
            있습니다. 탈퇴 후 정보 처리는 개인정보 처리 안내에 따릅니다.
          </li>
        </LegalList>
      </LegalSection>

      <LegalSection title="5. 이용자의 의무">
        <LegalList>
          <li>이용자는 정확한 본인 정보를 등록하고 계정 정보를 안전하게 관리해야 합니다.</li>
          <li>타인의 개인정보나 진료기록을 등록해서는 안 됩니다.</li>
          <li>서비스를 불법적인 목적 또는 다른 이용자의 이용을 방해하는 방식으로 사용해서는 안 됩니다.</li>
        </LegalList>
      </LegalSection>

      <LegalSection title="6. 이용 제한 및 계정 정지">
        <p>
          운영자는 이용자가 관계 법령이나 본 약관을 위반하거나, 타인의 정보를 도용하거나,
          서비스의 정상적인 운영을 방해한 경우 사전 안내 후 이용을 제한하거나 계정을 정지할 수
          있습니다. 긴급한 보안 위험이나 피해 확산을 막아야 하는 경우에는 먼저 조치한 후 그
          사유를 안내할 수 있습니다. 이용자는 문의처를 통해 이의를 제기할 수 있습니다.
        </p>
      </LegalSection>

      <LegalSection title="7. 복약 및 일정 알림">
        <p>
          알림은 복약과 일정을 보조하기 위한 기능입니다. 기기 설정, 브라우저 권한, 네트워크
          장애, 운영체제 정책 또는 외부 Push 서비스의 사정으로 알림이 지연되거나 전달되지 않을
          수 있습니다. 이용자는 서비스 알림만을 복약 여부나 진료 일정 판단의 유일한 수단으로
          사용해서는 안 됩니다.
        </p>
      </LegalSection>

      <LegalSection title="8. 서비스 변경, 중단 및 종료">
        <p>
          운영자는 점검, 장애, 외부 서비스 변경 또는 불가피한 운영상 사유로 서비스의 전부
          또는 일부를 변경하거나 일시 중단할 수 있습니다. 중요한 변경은 가능한 범위에서
          사전에 안내합니다. 서비스를 종료하는 경우 종료일과 이용자 정보의 처리 방법을
          안내하며, 보유 정보는 개인정보 처리 안내와 관계 법령에 따라 처리합니다.
        </p>
      </LegalSection>

      <LegalSection title="9. 이용자 입력정보와 지식재산권">
        <LegalList>
          <li>
            이용자는 자신이 입력하거나 업로드한 정보에 필요한 권한을 보유해야 하며, 타인의
            개인정보·저작권 등 권리를 침해해서는 안 됩니다.
          </li>
          <li>
            서비스의 화면, 소프트웨어, 상표 및 운영자가 작성한 콘텐츠에 관한 권리는 운영자 또는
            정당한 권리자에게 있습니다.
          </li>
          <li>
            서비스가 제공하는 의약품·영양성분 등 공공 참고자료의 권리와 이용조건은 해당 자료의
            제공기관 및 출처 정책을 따릅니다.
          </li>
        </LegalList>
      </LegalSection>

      <LegalSection title="10. 책임의 제한">
        <p>
          서비스와 AI 답변은 복약관리를 돕기 위한 참고사항입니다. 운영자는 법률이 허용하는
          범위에서 이를 의료적·법적 판단의 유일한 근거로 사용하여 발생한 손해에 책임을 지지
          않습니다. 다만 운영자의 고의 또는 중대한 과실이나 관계 법령상 배제할 수 없는
          책임에는 이 제한이 적용되지 않습니다.
        </p>
      </LegalSection>

      <LegalSection title="11. 약관의 변경 및 공지">
        <p>
          운영자는 관련 법령이나 서비스 변경에 따라 약관을 개정할 수 있으며, 적용일과 주요
          내용을 서비스에서 사전에 안내합니다. 이용자에게 불리한 중요한 변경으로 별도 동의가
          필요한 경우에는 관계 법령에 따라 동의를 받습니다.
        </p>
      </LegalSection>

      <LegalSection title="12. 문의">
        <p>
          약관 및 서비스 이용에 관한 문의는{' '}
          <a className="font-semibold text-primary underline" href="mailto:blesseunmi@gmail.com">
            blesseunmi@gmail.com
          </a>
          으로 접수할 수 있습니다.
        </p>
      </LegalSection>
    </LegalDocumentPage>
  );
}
