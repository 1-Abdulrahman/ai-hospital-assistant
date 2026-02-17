import { Outlet } from 'react-router-dom';
import { MockBanner } from './MockBanner';
import { Header } from './Header';
import { Sidebar } from './Sidebar';
import { Footer } from './Footer';

export function AppLayout() {
  return (
    <div className="flex flex-col h-screen">
      <MockBanner />
      <Header />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-auto p-6 bg-background">
          <Outlet />
        </main>
      </div>
      <Footer />
    </div>
  );
}
