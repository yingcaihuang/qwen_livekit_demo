import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider } from '@/components/auth/AuthProvider'
import { ProtectedRoute } from '@/components/auth/ProtectedRoute'
import { AppShell } from '@/components/layout/AppShell'
import { DashboardPage } from '@/pages/DashboardPage'
import { InstancesPage } from '@/pages/InstancesPage'
import { InstanceFormPage } from '@/pages/InstanceFormPage'
import { VoiceSessionPage } from '@/pages/VoiceSessionPage'
import { ChatPlaygroundPage } from '@/pages/ChatPlaygroundPage'
import { ImagePlaygroundPage } from '@/pages/ImagePlaygroundPage'
import { TranslatePage } from '@/pages/TranslatePage'
import { TranscribePage } from '@/pages/TranscribePage'
import { HistoryPage } from '@/pages/HistoryPage'
import { SessionDetailPage } from '@/pages/SessionDetailPage'
import { ImageDetailPage } from '@/pages/ImageDetailPage'
import { LoginPage } from '@/pages/LoginPage'
import { ChangePasswordPage } from '@/pages/ChangePasswordPage'
import { UsersPage } from '@/pages/admin/UsersPage'
import { GroupMappingsPage } from '@/pages/admin/GroupMappingsPage'
import { SsoConfigPage } from '@/pages/admin/SsoConfigPage'
import { AuditPage } from '@/pages/admin/AuditPage'
import { MonitorPage } from '@/pages/admin/MonitorPage'
import { UdpMonitorPage } from '@/pages/admin/UdpMonitorPage'
import { Toaster } from '@/components/ui/toast'

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          {/* Public routes */}
          <Route path="/login" element={<LoginPage />} />
          <Route path="/change-password" element={<ChangePasswordPage />} />

          {/* Protected routes */}
          <Route path="/" element={<ProtectedRoute capability="dashboard:read"><AppShell><DashboardPage /></AppShell></ProtectedRoute>} />
          <Route path="/instances" element={<ProtectedRoute capability="instance:read"><AppShell><InstancesPage /></AppShell></ProtectedRoute>} />
          <Route path="/instances/new" element={<ProtectedRoute capability="instance:write"><AppShell><InstanceFormPage /></AppShell></ProtectedRoute>} />
          <Route path="/instances/:id" element={<ProtectedRoute capability="instance:read"><AppShell><InstanceFormPage /></AppShell></ProtectedRoute>} />
          <Route path="/sessions/new" element={<ProtectedRoute capability="session:run"><AppShell><VoiceSessionPage /></AppShell></ProtectedRoute>} />
          <Route path="/chat/new" element={<ProtectedRoute capability="chat:use"><AppShell><ChatPlaygroundPage /></AppShell></ProtectedRoute>} />
          <Route path="/images/new" element={<ProtectedRoute capability="image:use"><AppShell><ImagePlaygroundPage /></AppShell></ProtectedRoute>} />
          <Route path="/translate/new" element={<ProtectedRoute capability="translate:use"><AppShell><TranslatePage /></AppShell></ProtectedRoute>} />
          <Route path="/transcribe/new" element={<ProtectedRoute capability="transcribe:use"><AppShell><TranscribePage /></AppShell></ProtectedRoute>} />
          <Route path="/history" element={<ProtectedRoute><AppShell><HistoryPage /></AppShell></ProtectedRoute>} />
          <Route path="/history/:id" element={<ProtectedRoute><AppShell><SessionDetailPage /></AppShell></ProtectedRoute>} />
          <Route path="/history/image/:id" element={<ProtectedRoute><AppShell><ImageDetailPage /></AppShell></ProtectedRoute>} />

          {/* Admin routes */}
          <Route path="/admin/users" element={<ProtectedRoute capability="user:manage"><AppShell><UsersPage /></AppShell></ProtectedRoute>} />
          <Route path="/admin/group-mappings" element={<ProtectedRoute capability="role:manage"><AppShell><GroupMappingsPage /></AppShell></ProtectedRoute>} />
          <Route path="/admin/sso" element={<ProtectedRoute capability="sso:manage"><AppShell><SsoConfigPage /></AppShell></ProtectedRoute>} />
          <Route path="/admin/audit" element={<ProtectedRoute capability="audit:read"><AppShell><AuditPage /></AppShell></ProtectedRoute>} />
          <Route path="/admin/monitor/udp" element={<ProtectedRoute capability="audit:read"><AppShell><UdpMonitorPage /></AppShell></ProtectedRoute>} />
          <Route path="/admin/monitor" element={<ProtectedRoute capability="audit:read"><AppShell><MonitorPage /></AppShell></ProtectedRoute>} />
        </Routes>
        <Toaster />
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
