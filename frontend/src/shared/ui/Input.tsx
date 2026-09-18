import { BaseInput, type InputProps } from './BaseInput';
import { DateInput } from './DateInput';
export type { InputProps } from './BaseInput';

export function Input(props: InputProps) {
  return props.type === 'date' || props.type === 'datetime-local'
    ? <DateInput {...props} />
    : <BaseInput {...props} />;
}
