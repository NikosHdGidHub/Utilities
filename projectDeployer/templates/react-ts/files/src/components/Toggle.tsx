import { useState } from 'react'
import Button from './Button'

export default function Toggle() {
  const [enabled, setEnabled] = useState(false)
  return <div><p aria-live="polite">{enabled ? 'Включено' : 'Выключено'}</p>
    <Button aria-pressed={enabled} onClick={() => setEnabled(value => !value)}>Переключить</Button></div>
}
