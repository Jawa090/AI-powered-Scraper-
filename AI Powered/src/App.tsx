import React, { useState, useEffect } from 'react';
import { DataOpsProvider } from './context/DataOpsContext';
import { AuthProvider, useAuth } from './context/AuthContext';
import { AppLayout } from './components/layout/AppLayout';

// Active Pages
import { Login } from './pages/Login';
import { Agent } from './pages/Agent';
import { Datasets } from './pages/Datasets';
import { DatasetDetail } from './pages/DatasetDetail';
import { Leads } from './pages/Leads';
import { Jobs } from './pages/Jobs';
import { JobDetail } from './pages/JobDetail';
import { Settings } from './pages/Settings';
import { AdminUsers } from './pages/AdminUsers';
import { AdminActivity } from './pages/AdminActivity';
import { AdminKnowledgeBase } from './pages/AdminKnowledgeBase';

// Preserved Inactive / Hidden Features per P13.6 (kept in codebase, routes removed)
import { Dashboard } from './pages/Dashboard';
import { DataRequests } from './pages/DataRequests';
import { DataRequestDetail } from './pages/DataRequestDetail';
import { Campaigns } from './pages/Campaigns';
import { CampaignDetail } from './pages/CampaignDetail';
import { Gantt } from './pages/Gantt';
import { Analytics } from './pages/Analytics';
import { Departments } from './pages/Departments';
import { DepartmentDetail } from './pages/DepartmentDetail';
import { Employees } from './pages/Employees';
import { EmployeeDetail } from './pages/EmployeeDetail';
import { Scripts } from './pages/Scripts';
import { Workflows } from './pages/Workflows';

const AppContent: React.FC = () => {
  const { isAuthenticated, isLoading, role } = useAuth();

  const [currentPath, setCurrentPath] = useState<string>(() => {
    const p = window.location.pathname;
    return p === '/' || p === '' || p === '/dashboard' || p === '/login' ? '/agent' : p;
  });

  useEffect(() => {
    const handlePopState = () => {
      const p = window.location.pathname;
      setCurrentPath(p === '/' || p === '/dashboard' ? '/agent' : p || '/agent');
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const navigate = (path: string) => {
    setCurrentPath(path);
    window.history.pushState({}, '', path);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[#F8F9FA] flex items-center justify-center">
        <div className="text-center space-y-2">
          <div className="w-8 h-8 border-2 border-[#2D4351] border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-xs text-gray-500 font-medium">Initializing workspace...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated || currentPath === '/login') {
    return (
      <Login
        onLoginSuccess={() => {
          navigate('/agent');
        }}
      />
    );
  }

  // Page title and breadcrumb mapping (P13.6 active routes)
  const getPageInfo = (path: string) => {
    if (path.startsWith('/agent')) return { title: 'AI Agent Intelligence', breadcrumb: 'Data Requirements' };
    if (path.startsWith('/datasets/')) return { title: 'Dataset Details', breadcrumb: 'Records' };
    if (path.startsWith('/datasets')) return { title: 'Intelligence Datasets', breadcrumb: 'Repository' };
    if (path.startsWith('/leads')) return { title: 'Leads Workspace', breadcrumb: 'Verified Leads' };
    if (path.startsWith('/jobs/')) return { title: 'Job Diagnostics', breadcrumb: 'Execution Telemetry' };
    if (path.startsWith('/jobs')) return { title: 'Job Monitoring', breadcrumb: 'Infrastructure' };
    if (path.startsWith('/settings')) return { title: 'Platform Settings', breadcrumb: 'Configuration' };
    if (path.startsWith('/admin/users')) return { title: 'User Management', breadcrumb: 'Admin Center' };
    if (path.startsWith('/admin/activity')) return { title: 'Activity Telemetry', breadcrumb: 'Admin Center' };
    if (path.startsWith('/admin/kb')) return { title: 'Knowledge Base (RAG)', breadcrumb: 'Admin Center' };
    return { title: 'AI Agent Intelligence', breadcrumb: 'Agent' };
  };

  const { title, breadcrumb } = getPageInfo(currentPath);

  const renderPage = () => {
    // Dynamic Routes
    if (currentPath.startsWith('/datasets/')) {
      const id = currentPath.split('/datasets/')[1];
      return <DatasetDetail id={id} onNavigate={navigate} />;
    }
    if (currentPath.startsWith('/jobs/')) {
      const id = currentPath.split('/jobs/')[1];
      return <JobDetail id={id} onNavigate={navigate} />;
    }

    // Static Routes
    switch (currentPath) {
      case '/agent':
        return <Agent onNavigate={navigate} />;
      case '/leads':
        return <Leads onNavigate={navigate} />;
      case '/datasets':
        return <Datasets onNavigate={navigate} />;
      case '/jobs':
        return <Jobs onNavigate={navigate} />;
      case '/settings':
        return <Settings />;
      case '/admin/users':
        return role === 'admin' ? <AdminUsers /> : <Agent onNavigate={navigate} />;
      case '/admin/activity':
        return role === 'admin' ? <AdminActivity /> : <Agent onNavigate={navigate} />;
      case '/admin/kb':
        return role === 'admin' ? <AdminKnowledgeBase /> : <Agent onNavigate={navigate} />;
      default:
        return <Agent onNavigate={navigate} />;
    }
  };

  return (
    <AppLayout
      currentPath={currentPath}
      onNavigate={navigate}
      pageTitle={title}
      breadcrumb={breadcrumb}
    >
      {renderPage()}
    </AppLayout>
  );
};

export const App: React.FC = () => {
  return (
    <AuthProvider>
      <DataOpsProvider>
        <AppContent />
      </DataOpsProvider>
    </AuthProvider>
  );
};

export default App;
