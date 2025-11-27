import ActivityBar from './ActivityBar';
import ArchiveBrowser from './ArchiveBrowser';
import logo from '../assets/logo.svg';

export default function Layout() {
  return (
    <div className="h-screen bg-base-200 flex flex-col overflow-hidden">
      {/* Navbar */}
      <div className="navbar bg-base-100 shadow-lg flex-none">
        <div className="flex-1 flex items-center">
          <a className="btn btn-ghost text-xl flex items-center gap-2">
            <img src={logo} alt="Logo" className="w-6 h-6" />
            Paperless AI Renamer
          </a>
        </div>
        <div className="flex-none flex items-center pr-4">
          <ActivityBar />
        </div>
      </div>

      {/* Main Content */}
      <div className="container mx-auto p-4 flex-1 flex flex-col min-h-0 overflow-hidden">
        <div className="flex-1 min-h-0 flex flex-col">
          <ArchiveBrowser />
        </div>
      </div>
    </div>
  );
}
