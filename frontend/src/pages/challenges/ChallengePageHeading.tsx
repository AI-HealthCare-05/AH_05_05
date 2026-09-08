import { ArrowLeft } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router';

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

  return (
    <header className="flex items-center gap-3">
      <button
        type="button"
        aria-label="뒤로 가기"
        onClick={goBack}
        className="flex size-11 shrink-0 items-center justify-center rounded-pill text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
      >
        <ArrowLeft aria-hidden className="size-5" />
      </button>
      <h1 className="text-[22px] font-bold leading-6 text-foreground">챌린지</h1>
    </header>
  );
}
