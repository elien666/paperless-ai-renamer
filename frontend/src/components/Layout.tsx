import ActivityBar from './ActivityBar';
import ArchiveBrowser from './ArchiveBrowser';
import logo from '../assets/logo.svg';

export default function Layout() {
  return (
    <div className="min-h-screen bg-base-200 flex flex-col">
      {/* Navbar */}
      <div className="navbar bg-base-100 shadow-lg">
        <div className="flex-1 flex items-center">
          <a className="btn btn-ghost text-xl flex items-center gap-2">
            <img src={logo} alt="Logo" className="w-6 h-6" />
            Paperless AI Renamer
          </a>
        </div>
        <div className="flex-none">
          <ActivityBar />
        </div>
      </div>

      {/* Main Content */}
      <div className="container mx-auto p-4 flex-1 flex flex-col">
        <div className="flex-1">
          <ArchiveBrowser />
        </div>
      </div>
    </div>
  );
}
