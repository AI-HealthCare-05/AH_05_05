type GenderValue = 'male' | 'female';

interface GenderRadioGroupProps {
  value: GenderValue | '';
  onChange: (value: GenderValue) => void;
}

const OPTIONS: Array<{ value: GenderValue; label: string }> = [
  { value: 'male', label: '남성' },
  { value: 'female', label: '여성' },
];

export function GenderRadioGroup({ value, onChange }: GenderRadioGroupProps) {
  return (
    <fieldset className="flex flex-col gap-1.5">
      <legend className="text-sm font-bold text-foreground">성별</legend>
      <div className="grid grid-cols-2 gap-2">
        {OPTIONS.map((option) => {
          const selected = value === option.value;
          return (
            <label
              key={option.value}
              className={`flex min-h-touch cursor-pointer items-center justify-center gap-2 rounded-input border text-base font-bold ${
                selected
                  ? 'border-primary bg-primary-bg text-primary-strong'
                  : 'border-input bg-card text-muted-foreground'
              }`}
            >
              <input
                type="radio"
                name="gender"
                value={option.value}
                checked={selected}
                required
                className="size-5 accent-primary"
                onChange={() => onChange(option.value)}
              />
              {option.label}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
