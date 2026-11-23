import { NavLink, Outlet } from 'react-router-dom'
import { projectName } from '../title'

export default function Layout() {
  return <><header>{projectName}<nav aria-label="Навигация">
    <NavLink to="/" end>Главная</NavLink><NavLink to="/about">О проекте</NavLink>
  </nav></header><Outlet /></>
}
