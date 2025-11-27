# Paperless AI Renamer - Frontend

Modern React-based web interface for the Paperless AI Renamer service. Provides a user-friendly UI for monitoring document processing progress, browsing archive history, managing vector database indexing, and triggering manual scans.

## Tech Stack

- **React 19** - UI framework
- **TypeScript** - Type safety
- **Vite** - Build tool and dev server
- **Tailwind CSS 4** - Utility-first CSS framework
- **DaisyUI** - Component library built on Tailwind
- **Axios** - HTTP client for API communication
- **date-fns** - Date formatting utilities
- **react-icons** - Icon library

## Project Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── ActivityBar.tsx          # Activity indicator in navbar
│   │   ├── ArchiveBrowser.tsx       # Main tabbed interface (Renaming, Jobs, Issues)
│   │   ├── DocumentProcessor.tsx    # Document processing component
│   │   ├── FloatingActionButton.tsx # FAB for triggering actions (scan, index, etc.)
│   │   ├── Layout.tsx               # Main layout wrapper
│   │   └── ProgressView.tsx         # Progress bar component
│   ├── contexts/
│   │   └── ProgressContext.tsx      # React context for real-time progress updates
│   ├── services/
│   │   └── api.ts                   # API client service
│   ├── App.tsx                      # Root component
│   ├── main.tsx                     # Entry point
│   └── index.css                    # Global styles
├── public/                          # Static assets (favicons, etc.)
├── dist/                            # Production build output
└── package.json
```

## Features

### Archive Browser
Three-tab interface for browsing historical data:
- **Renaming Tab**: Shows all document title changes with before/after comparisons
- **Jobs Tab**: Displays index and scan job history with status and statistics
- **Issues Tab**: Lists processing errors with details and timestamps

### Real-time Progress
- Live progress updates via long-polling
- Progress bars for active jobs (indexing, scanning, document processing)
- Activity indicators in the navbar

### Floating Action Button (FAB)
Quick access to common actions:
- Trigger manual scan
- Start bulk indexing
- Process specific documents
- Find outliers in vector space

## Development

### Prerequisites

- Node.js 20+ and npm
- Backend API running (see main README for setup)

### Setup

1. **Install dependencies**:
   ```bash
   npm install
   ```

2. **Start development server**:
   ```bash
   npm run dev
   ```

   The dev server runs on `http://localhost:5173` and proxies API requests to `http://localhost:8000` (configured in `vite.config.ts`).

### Available Scripts

- `npm run dev` - Start development server with hot-reload
- `npm run build` - Build for production (outputs to `dist/`)
- `npm run preview` - Preview production build locally
- `npm run check` - Type check without building
- `npm run lint` - Run ESLint

### Building for Production

The frontend is built as static files and served by the FastAPI backend in production:

```bash
npm run build
```

This creates the `dist/` directory that gets copied into the Docker image during the build process.

## API Integration

The frontend communicates with the backend API through the `api.ts` service module. All API endpoints are prefixed with `/api` and are automatically proxied during development.

Key API endpoints used:
- `GET /api/progress` - Get job progress (with long-polling support)
- `GET /api/archive/*` - Fetch archive data (renames, jobs, errors)
- `POST /api/scan` - Trigger manual scan
- `POST /api/index` - Start bulk indexing
- `POST /api/process-documents` - Process specific documents
- `GET /api/find-outliers` - Find outlier documents

## Styling

The UI uses Tailwind CSS with DaisyUI components and the "sunset" theme (configured in `index.html`). The design follows a modern, clean aesthetic with:

- Responsive layout
- Dark theme support (via DaisyUI)
- Smooth animations and transitions
- Accessible components

## Type Safety

The project uses TypeScript with strict type checking. API response types are defined in `src/services/api.ts` and shared across components.

## State Management

- **Local State**: React hooks (`useState`, `useEffect`) for component-level state
- **Context API**: `ProgressContext` for sharing progress updates across components
- **Server State**: Components fetch data directly from the API as needed

## Browser Support

Modern browsers with ES2020+ support. The build targets are configured in `vite.config.ts` and `tsconfig.json`.
