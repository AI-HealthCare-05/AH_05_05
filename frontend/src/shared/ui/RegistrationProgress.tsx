interface RegistrationProgressProps {
  step: 1 | 2 | 3 | 4 | 5;
}

export function RegistrationProgress({ step }: RegistrationProgressProps) {
  return (
    <div
      aria-label="복약 등록 단계"
      className="flex items-center gap-3"
      data-registration-step={step}
      role="status"
    >
      <span className="w-12 shrink-0 text-xs font-bold text-muted-foreground tnum">
        {step} / 5
      </span>
      <div className="grid flex-1 grid-cols-5 gap-2" aria-hidden="true">
        {Array.from({ length: 5 }, (_, index) => (
          <span
            key={index}
            className={`h-1 rounded-pill ${index < step ? 'bg-primary' : 'bg-border'}`}
          />
        ))}
      </div>
    </div>
  );
}
