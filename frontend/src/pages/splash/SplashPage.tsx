import { useEffect } from 'react';
import { useNavigate } from 'react-router';

const SPLASH_DURATION_MS = 1_200;
const SPLASH_SEEN_KEY = 'poke:splash-seen';

export function SplashPage() {
  const navigate = useNavigate();

  useEffect(() => {
    if (window.sessionStorage.getItem(SPLASH_SEEN_KEY) === 'true') {
      navigate('/home', { replace: true });
      return;
    }

    const timer = window.setTimeout(() => {
      window.sessionStorage.setItem(SPLASH_SEEN_KEY, 'true');
      navigate('/home', { replace: true });
    }, SPLASH_DURATION_MS);
    return () => window.clearTimeout(timer);
  }, [navigate]);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-app flex-col items-center overflow-hidden bg-card px-page-x pt-28 text-center">
      <p className="text-tagline text-brand">약봉투 한 장이면 충분해요</p>
      <img
        src="/images/rxvita-logo-960.png"
        alt="RxVita"
        className="mt-2 w-56"
        width={960}
        height={248}
      />

      <svg
        aria-hidden
        viewBox="0 0 335 300"
        className="mt-auto w-full text-border"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      >
        <path d="M8 270H327M40 270v32m246-32v32M62 199c-24 12-34 32-34 62 18-7 30-22 34-43m0 52v-83" />
        <path d="M96 134h112v136H96zM96 134l56-35 56 35" />
        <path d="M120 179h64M120 207h64M120 235h35" />
        <path d="M252 197h50l-5 73h-40zM247 236h61M278 96h42v72h-42zM299 96v72M278 132h42" />
        <circle cx="80" cy="61" r="27" />
        <path d="M80 42v20l13 9" />
        <circle cx="166" cy="251" r="10" className="fill-primary stroke-primary" />
        <ellipse cx="190" cy="273" rx="16" ry="8" />
        <ellipse cx="220" cy="273" rx="16" ry="8" />
      </svg>
    </main>
  );
}
