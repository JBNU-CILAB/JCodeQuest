import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider } from './lib/AuthContext'
import { Header } from './components/Header'
import { Landing } from './pages/Landing'
import { Problems } from './pages/Problems'
import { Solver } from './pages/Solver'
import { Result } from './pages/Result'
import { Notices } from './pages/Notices'
import { NoticeDetail } from './pages/NoticeDetail'
import { MyPage } from './pages/MyPage'

function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-full flex flex-col">
      <Header />
      {children}
      <footer className="mt-auto p-6 text-center text-gray-400 text-xs">
        © 2026 JCodeQuest · JBNU Compiler Intelligence Lab. All rights reserved.
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
            <Route path="/settings/api-key" element={<Landing />} />
            <Route path="/problems" element={<Problems />} />
            <Route path="/problems/:id" element={<Solver />} />
            <Route path="/submissions/:id" element={<Result />} />
            <Route path="/notices" element={<Notices />} />
            <Route path="/notices/:id" element={<NoticeDetail />} />
            <Route path="/mypage" element={<MyPage />} />
          </Routes>
        </Layout>
      </BrowserRouter>
    </AuthProvider>
  )
}
