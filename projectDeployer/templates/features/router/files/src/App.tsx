import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Layout from './layouts/Layout'
import Home from './pages/Home'
import About from './pages/About'

export default function App() {
  return <BrowserRouter><Routes><Route element={<Layout />}>
    <Route index element={<Home />} /><Route path="about" element={<About />} />
  </Route></Routes></BrowserRouter>
}
