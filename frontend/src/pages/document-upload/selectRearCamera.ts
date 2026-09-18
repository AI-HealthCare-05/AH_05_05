export type LensKind = 'front' | 'ultrawide' | 'tele' | 'main' | 'unknown';

// Camera labels are not standardized across browsers/OSes and this is only ever a best-effort hint,
// never a guaranteed lens identity. iOS Safari reliably names multi-lens rear cameras ("Back Camera",
// "Back Ultra Wide Camera", "Back Telephoto Camera"); many Android builds only expose generic or
// index-based strings with no optical hint at all, which this cannot classify past 'unknown'.
// A plain "wide" / "wide angle" / 광각 lens (no "ultra"/초 prefix) is the standard MAIN lens, not the
// ultrawide — only an explicit "ultra wide"/"ultra angle"/초광각 qualifier means the ultrawide module.
const FRONT_HINTS = /front|user-facing|selfie|facetime|전면/i;
const ULTRAWIDE_HINTS = /ultra[\s-]?wide|ultra[\s-]?angle|초광각/i;
const TELE_HINTS = /tele(photo)?\b|\bzoom lens\b|망원/i;
const MAIN_HINTS = /\bback camera\b|\bmain\b|\brear camera\b|\bwide[\s-]?angle\b|\bwide camera\b|후면|메인|광각/i;

export function classifyLensLabel(label: string): LensKind {
  if (!label) return 'unknown';
  if (FRONT_HINTS.test(label)) return 'front';
  if (ULTRAWIDE_HINTS.test(label)) return 'ultrawide';
  if (TELE_HINTS.test(label)) return 'tele';
  if (MAIN_HINTS.test(label)) return 'main';
  return 'unknown';
}

export type GenericCameraLabel = { id: number; facing: 'front' | 'back' };

// Matches the generic Camera2-style label some Android browsers expose with no lens-descriptive text
// at all, e.g. "camera 2, facing back" — confirmed on a real Galaxy S26 Ultra / Samsung Internet
// device, where every rear camera used exactly this schema and classifyLensLabel above could only ever
// return 'unknown' for them (a bare "facing back" is NOT evidence of "main"; see classifyLensLabel's
// MAIN_HINTS, which never match this pattern). The numeric id here is the platform's own camera index,
// not an enumerateDevices() array position, and by a common (not spec-guaranteed) Android Camera2
// convention id 0 is the primary rear sensor. This parser is a narrow, bounded fallback for that one
// exact label shape — never a general optical/native-field-of-view claim.
const GENERIC_CAMERA_LABEL = /^camera\s+(\d+)\s*,\s*facing\s+(front|back)$/i;

export function parseGenericCameraLabel(label: string): GenericCameraLabel | null {
  const match = GENERIC_CAMERA_LABEL.exec(label.trim());
  if (!match) return null;
  const id = Number(match[1]);
  if (!Number.isInteger(id) || id < 0) return null;
  return { id, facing: match[2].toLowerCase() as 'front' | 'back' };
}
