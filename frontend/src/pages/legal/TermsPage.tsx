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

      <LegalSection title="4. 이용자의 의무">
        <LegalList>
          <li>이용자는 정확한 본인 정보를 등록하고 계정 정보를 안전하게 관리해야 합니다.</li>
          <li>타인의 개인정보나 진료기록을 등록해서는 안 됩니다.</li>
          <li>서비스를 불법적인 목적 또는 다른 이용자의 이용을 방해하는 방식으로 사용해서는 안 됩니다.</li>
        </LegalList>
      </LegalSection>

      <LegalSection title="5. 서비스 변경 및 중단">
        <p>
          운영자는 점검, 장애, 외부 서비스 변경 또는 불가피한 운영상 사유로 서비스의 전부
          또는 일부를 변경하거나 일시 중단할 수 있습니다. 중요한 변경은 가능한 범위에서
          사전에 안내합니다.
        </p>
      </LegalSection>

      <LegalSection title="6. 책임의 제한">
        <p>
          서비스와 AI 답변은 복약관리를 돕기 위한 참고사항입니다. 운영자는 법률이 허용하는
          범위에서 이를 의료적·법적 판단의 유일한 근거로 사용하여 발생한 손해에 책임을 지지
          않습니다. 다만 운영자의 고의 또는 중대한 과실이나 관계 법령상 배제할 수 없는
          책임에는 이 제한이 적용되지 않습니다.
        </p>
      </LegalSection>

      <LegalSection title="7. 약관의 변경 및 문의">
        <p>
          운영자는 관련 법령이나 서비스 변경에 따라 약관을 개정할 수 있으며, 적용일과 주요
          내용을 서비스에서 안내합니다. 약관 문의는{' '}
          <a className="font-semibold text-primary underline" href="mailto:blesseunmi@gmail.com">
            blesseunmi@gmail.com
          </a>
          으로 접수할 수 있습니다.
        </p>
      </LegalSection>
    </LegalDocumentPage>
  );
}
