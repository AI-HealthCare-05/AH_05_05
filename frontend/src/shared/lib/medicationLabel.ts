const STRENGTH_PATTERN = /(?<![\d.])\d+(?:\.\d+)?(?:\s*\/\s*\d+(?:\.\d+)?)*\s*(?:마이크로그램|밀리그램|밀리리터|퍼센트|그램|mcg|[μµu]g|mg|m[lℓ]|g|%)(?![a-z])(?:\s*\/\s*(?:\d+(?:\.\d+)?\s*)?(?:마이크로그램|밀리그램|밀리리터|그램|mcg|[μµu]g|mg|m[lℓ]|g|정|캡슐|포)(?![a-z]))?/gi;

function strengthKey(text: string): string {
  const normalized = text.normalize('NFKC').toLowerCase()
    .replace(/\s+/g, '').replace(/[μµ]/g, 'u')
    .replace(/마이크로그램/g, 'ug').replace(/밀리그램/g, 'mg')
    .replace(/밀리리터/g, 'ml').replace(/그램/g, 'g').replace(/퍼센트/g, '%')
    .replace(/mcg/g, 'ug').replace(/mℓ/g, 'ml');
  const mass = /^(\d+)(?:\.(\d+))?(ug|mg|g)$/.exec(normalized);
  if (!mass) return normalized; // Ratios and concentrations remain atomic.
  const fraction = mass[2] ?? '';
  let digits = `${mass[1]}${fraction}`.replace(/^0+/, '') || '0';
  let exponent = (mass[3] === 'g' ? 6 : mass[3] === 'mg' ? 3 : 0) - fraction.length;
  while (digits.endsWith('0') && digits.length > 1) {
    digits = digits.slice(0, -1);
    exponent += 1;
  }
  return digits === '0' ? 'mass:0' : `mass:${digits}e${exponent}`;
}

function withoutRepeatedStrength(value: string, seen: Set<string>): string {
  return value.normalize('NFKC').replace(STRENGTH_PATTERN, (token) => {
    const key = strengthKey(token);
    if (seen.has(key)) return '';
    seen.add(key);
    return token;
  }).replace(/\(\s*\)|\[\s*\]/g, '')
    .replace(/([·,;])\s*(?=[·,;]|$)/g, '')
    .replace(/^[\s·,;]+|[\s·,;]+$/g, '').replace(/\s+/g, ' ').trim();
}

/** Display only; keep stored OCR text untouched and retain the first distinct strength. */
export function formatMedicationStrength(strength?: string | null): string {
  return withoutRepeatedStrength(strength?.trim() ?? '', new Set());
}

/** Title = original name only, including any strength already printed in that name. */
export function formatMedicationLabel(name: string, _strength?: string | null): string {
  return name.trim();
}

/** Remove display-only decimal padding without rounding, changing units or stored OCR. */
export function formatMedicationDoseQuantity(value?: string | null): string {
  const text = value?.trim() ?? '';
  const match = /^(\d+)\.(\d+)(\s*[a-zA-Z가-힣μµℓ]*)$/.exec(text);
  if (!match) return text;
  const fraction = match[2].replace(/0+$/, '');
  return `${match[1]}${fraction ? `.${fraction}` : ''}${match[3]}`;
}
