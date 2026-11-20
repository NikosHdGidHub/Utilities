# {{project_name}} · React + Vite + TypeScript

Выполняйте команды из папки проекта.

## Разработка

- `npm run dev` — запустить Vite. Откройте адрес из терминала. Ctrl+C остановит сервер.
- `npm run lint` — проверить код через Oxlint.
- `npm run build` — проверить TypeScript и собрать сайт в `dist/`.
- `npm run preview` — локально просмотреть готовую сборку после `build`.
- `npm ci` — установить версии из `package-lock.json`.
- `npm install имя-пакета` или `npm install -D имя-пакета` — добавить зависимость.

## React

- `src/App.tsx` — начальный компонент. Компоненты называют с заглавной буквы.
- `<Card title="Привет" />` — передача свойств (props) компоненту. Опишите их тип в TypeScript.
- `const [count, setCount] = useState(0)` — состояние компонента. Для увеличения используйте `setCount(value => value + 1)`.
- `onClick={handleClick}` — передача функции-обработчика.
- `src/main.tsx` — точка входа, где React монтирует приложение.

## Git

- `git status` — посмотреть изменения.
- `git diff` — посмотреть правки перед добавлением.
- `git add .` и `git commit -m "Initial commit"` — создать первый коммит в main.
- `git switch -c feature/my-change` — создать рабочую ветку после первого коммита.
- `git switch main` — вернуться в main.
- `git log --oneline` — посмотреть историю.
- `git remote add origin URL` и `git push -u origin main` — отправить main в созданный удалённый репозиторий.
