import React, { useState, useEffect } from 'react';
import { DataOpsProvider, useDataOps } from './context/DataOpsContext';
import { AuthProvider } from './context/AuthContext';
import { AppLayout } from './components/layout/AppLayout';

// Pages
import { Login } from './pages/Login';
import { Dashboard } from './pages/Dashboard';
import { Agent } from './pages/Agent';
import { DataRequests } from './pages/DataRequests';
import { DataRequestDetail } from './pages/DataRequestDetail';
import { Datasets } from './pages/Datasets';
import { DatasetDetail } from './pages/DatasetDetail';
import { Leads } from './pages/Leads';
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
import { Jobs } from './pages/Jobs';
import { JobDetail } from './pages/JobDetail';
import { Settings } from './pages/Settings';

const AppContent: React.FC = () => {
  const [currentPath, setCurrentPath] = useState<string>(() => {
    return window.location.pathname === '/' || window.location.pathname === ''
      ? '/dashboard'
      : window.location.pathname;
  });

  const [isLoggedIn, setIsLoggedIn] = useState(true);

  useEffect(() => {
    const handlePopState = () => {
      setCurrentPath(window.location.pathname || '/dashboard');
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const navigate = (path: string) => {
    setCurrentPath(path);
    window.history.pushState({}, '', path);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  if (!isLoggedIn || currentPath === '/login') {
    return (
      <Login
        onLoginSuccess={() => {
          setIsLoggedIn(true);
          navigate('/dashboard');
        }}
      />
    );
  }

  // Page title mapping
  const getPageInfo = (path: string) => {
    if (path.startsWith('/agent')) return { title: 'AI Agent Intelligence', breadcrumb: 'Data Requirements' };
    if (path.startsWith('/data-requests/')) return { title: 'Data Pipeline Execution', breadcrumb: 'Live Telemetry' };
    if (path.startsWith('/data-requests')) return { title: 'Data Requests', breadcrumb: 'Pipelines' };
    if (path.startsWith('/datasets/')) return { title: 'Dataset Details', breadcrumb: 'Records' };
    if (path.startsWith('/datasets')) return { title: 'Intelligence Datasets', breadcrumb: 'Repository' };
    if (path.startsWith('/leads')) return { title: 'Leads Workspace', breadcrumb: 'Direct Outreach' };
    if (path.startsWith('/campaigns/')) return { title: 'Campaign Summary', breadcrumb: 'Outreach Waves' };
    if (path.startsWith('/campaigns')) return { title: 'Outreach Campaigns', breadcrumb: 'Sequences' };
    if (path.startsWith('/gantt')) return { title: 'Operations Timeline', breadcrumb: 'Gantt Schedule' };
    if (path.startsWith('/analytics')) return { title: 'Executive Analytics', breadcrumb: 'Performance' };
    if (path.startsWith('/departments/')) return { title: 'Department Hub', breadcrumb: 'Overview' };
    if (path.startsWith('/departments')) return { title: 'Departments', breadcrumb: 'Organization' };
    if (path.startsWith('/employees/')) return { title: 'Employee Profile', breadcrumb: 'Performance' };
    if (path.startsWith('/employees')) return { title: 'Employee Directory', breadcrumb: 'Productivity' };
    if (path.startsWith('/scripts')) return { title: 'Script Registry', breadcrumb: 'Autonomous Scrapers' };
    if (path.startsWith('/workflows')) return { title: 'Data Workflows', breadcrumb: 'Node Pipeline' };
    if (path.startsWith('/jobs/')) return { title: 'Job Diagnostics', breadcrumb: 'Worker Details' };
    if (path.startsWith('/jobs')) return { title: 'Job Monitoring', breadcrumb: 'Infrastructure' };
    if (path.startsWith('/settings')) return { title: 'Platform Settings', breadcrumb: 'Configuration' };
    return { title: 'Operations Overview', breadcrumb: 'Dashboard' };
  };

  const { title, breadcrumb } = getPageInfo(currentPath);

  const renderPage = () => {
    // Dynamic Routes
    if (currentPath.startsWith('/data-requests/')) {
      const id = currentPath.split('/data-requests/')[1];
      return <DataRequestDetail id={id} onNavigate={navigate} />;
    }
    if (currentPath.startsWith('/datasets/')) {
      const id = currentPath.split('/datasets/')[1];
      return <DatasetDetail id={id} onNavigate={navigate} />;
    }
    if (currentPath.startsWith('/campaigns/')) {
      const id = currentPath.split('/campaigns/')[1];
      return <CampaignDetail id={id} onNavigate={navigate} />;
    }
    if (currentPath.startsWith('/departments/')) {
      const id = currentPath.split('/departments/')[1];
      return <DepartmentDetail id={id} onNavigate={navigate} />;
    }
    if (currentPath.startsWith('/employees/')) {
      const id = currentPath.split('/employees/')[1];
      return <EmployeeDetail id={id} onNavigate={navigate} />;
    }
    if (currentPath.startsWith('/jobs/')) {
      const id = currentPath.split('/jobs/')[1];
      return <JobDetail id={id} onNavigate={navigate} />;
    }

    // Static Routes
    switch (currentPath) {
      case '/agent':
        return <Agent onNavigate={navigate} />;
      case '/data-requests':
        return <DataRequests onNavigate={navigate} />;
      case '/datasets':
        return <Datasets onNavigate={navigate} />;
      case '/leads':
        return <Leads onNavigate={navigate} />;
      case '/campaigns':
        return <Campaigns onNavigate={navigate} />;
      case '/gantt':
        return <Gantt />;
      case '/analytics':
        return <Analytics />;
      case '/departments':
        return <Departments onNavigate={navigate} />;
      case '/employees':
        return <Employees onNavigate={navigate} />;
      case '/scripts':
        return <Scripts />;
      case '/workflows':
        return <Workflows />;
      case '/jobs':
        return <Jobs onNavigate={navigate} />;
      case '/settings':
        return <Settings />;
      case '/dashboard':
      default:
        return <Dashboard onNavigate={navigate} />;
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
    <DataOpsProvider>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </DataOpsProvider>
  );
};

export default App;
