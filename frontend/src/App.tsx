import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider } from './lib/AuthContext'
import { Header } from './components/Header'
import { Landing } from './pages/Landing'
import { Problems } from './pages/Problems'
import { Solver } from './pages/Solver'
import { Result } from './pages/Result'

function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-full flex flex-col">
      <Header />
      {children}
      <footer className="mt-auto p-6 text-center text-gray-400 text-xs">
        © 2026 JCodeQuest · 프로토타입
      </footer>
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Layout>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/problems" element={<Problems />} />
            <Route path="/problems/:id" element={<Solver />} />
            <Route path="/submissions/:id" element={<Result />} />
          </Routes>
        </Layout>
      </BrowserRouter>
    </AuthProvider>
  )
}
