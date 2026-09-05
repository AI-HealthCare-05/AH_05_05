/** Keep the original product name; suppress only a separately repeated strength. */
export function medicationStrengthSuffix(name: string, strength?: string | null): string {
  const value = strength?.trim() ?? '';
  if (!value) return '';
  const normalize = (text: string) => text.normalize('NFKC').toLowerCase().replace(/\s+/g, '').replace(/[μµ]/g, 'u');
  const product = normalize(name);
  const amount = normalize(value);
  const index = product.lastIndexOf(amount);
  if (index >= 0 && !/[\d.]/.test(product[index - 1] ?? '') && !/[a-z\d.]/.test(product[index + amount.length] ?? '')) return '';
  return value;
}

export function formatMedicationLabel(name: string, strength?: string | null): string {
  return [name.trim(), medicationStrengthSuffix(name, strength)].filter(Boolean).join(' ');
}
