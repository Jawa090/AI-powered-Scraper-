import React, { useState } from 'react';
import { Sidebar } from './Sidebar';
import { TopHeader } from './TopHeader';
import { ToastContainer } from '../common/ToastContainer';
import { InteractiveBackground } from '../common/InteractiveBackground';

interface AppLayoutProps {
  currentPath: string;
  onNavigate: (path: string) => void;
  pageTitle: string;
  breadcrumb?: string;
  children: React.ReactNode;
}

export const AppLayout: React.FC<AppLayoutProps> = ({
  currentPath,
  onNavigate,
  pageTitle,
  breadcrumb,
  children,
}) => {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isOpenMobile, setIsOpenMobile] = useState(false);

  return (
    <div className="min-h-screen bg-[#F8F9FA]/85 text-[#111827] flex relative selection:bg-emerald-500/20">
      {/* Interactive Animated Dynamic Background with Particles & Constellation */}
      <InteractiveBackground variant="adaptive" showControls={true} />

      {/* Navigation Sidebar */}
      <Sidebar
        currentPath={currentPath}
        onNavigate={onNavigate}
        isCollapsed={isCollapsed}
        onToggleCollapse={() => setIsCollapsed(!isCollapsed)}
        isOpenMobile={isOpenMobile}
        onCloseMobile={() => setIsOpenMobile(false)}
      />

      {/* Main Content Area */}
      <div
        className={`flex-1 flex flex-col min-w-0 transition-all duration-200 ${
          isCollapsed ? 'md:ml-16' : 'md:ml-60'
        }`}
      >
        <TopHeader
          onToggleSidebar={() => setIsOpenMobile(!isOpenMobile)}
          pageTitle={pageTitle}
          breadcrumb={breadcrumb}
        />

        <main className="flex-1 p-4 md:p-6 lg:p-8 max-w-[1600px] w-full mx-auto">
          {children}
        </main>
      </div>

      <ToastContainer />
    </div>
  );
};
