import type { ReactNode } from 'react'

export default function Card({ title, children }: { title: string; children: ReactNode }) {
  return <section className="rounded-xl border border-slate-200 bg-white p-6"><h2>{title}</h2>{children}</section>
}
