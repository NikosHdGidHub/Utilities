import { useState } from 'react'
import Button from './Button'

export default function Counter() {
  const [count, setCount] = useState(0)
  return <div><p aria-live="polite">Значение: {count}</p>
    <Button onClick={() => setCount(value => value + 1)}>Увеличить</Button></div>
}
