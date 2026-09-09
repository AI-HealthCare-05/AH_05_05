import { useLocation, useNavigate } from 'react-router';
import { Header } from '@/shared/ui';

export function ChallengePageHeading() {
  const navigate = useNavigate();
  const location = useLocation();

  function goBack() {
    const index = window.history.state?.idx;
    if (typeof index === 'number' && index > 0) {
      navigate(-1);
      return;
    }
    navigate(location.pathname.startsWith('/dev/') ? '/dev/home-challenges' : '/home', { replace: true });
  }

  return <Header title="챌린지" onBack={goBack} />;
}
