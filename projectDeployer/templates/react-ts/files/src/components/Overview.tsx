import Card from './Card'
import Counter from './Counter'
import Toggle from './Toggle'
import { projectName } from '../title'

export default function Overview() {
  return <main><h1>{projectName}</h1><p>Проект готов к работе.</p>
    <div className="cards">
      <Card title="Счётчик"><Counter /></Card>
      <Card title="Переключатель"><Toggle /></Card>
    </div>
  </main>
}
