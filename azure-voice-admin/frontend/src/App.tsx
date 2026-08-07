import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { DashboardPage } from '@/pages/DashboardPage'
import { InstancesPage } from '@/pages/InstancesPage'
import { InstanceFormPage } from '@/pages/InstanceFormPage'
import { VoiceSessionPage } from '@/pages/VoiceSessionPage'
import { HistoryPage } from '@/pages/HistoryPage'
import { SessionDetailPage } from '@/pages/SessionDetailPage'

function App() {
  return (
    <BrowserRouter>
      <AppShell>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/instances" element={<InstancesPage />} />
          <Route path="/instances/new" element={<InstanceFormPage />} />
          <Route path="/instances/:id" element={<InstanceFormPage />} />
          <Route path="/sessions/new" element={<VoiceSessionPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/history/:id" element={<SessionDetailPage />} />
        </Routes>
      </AppShell>
    </BrowserRouter>
  )
}

export default App
