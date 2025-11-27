import { useState, useRef } from 'react';
import { apiService } from '../services/api';
import { FaPlus, FaFileAlt, FaDatabase, FaSearch, FaTimes } from 'react-icons/fa';

export default function FloatingActionButton() {
  const processModalRef = useRef<HTMLDialogElement>(null);
  const indexModalRef = useRef<HTMLDialogElement>(null);
  const scanModalRef = useRef<HTMLDialogElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const indexDateRef = useRef<HTMLInputElement>(null);
  const scanDateRef = useRef<HTMLInputElement>(null);
  const [documentId, setDocumentId] = useState('');
  const [indexDate, setIndexDate] = useState('');
  const [scanDate, setScanDate] = useState(() => new Date().toISOString().split('T')[0]);
  const [scanDatePreset, setScanDatePreset] = useState<string>('today');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const handleProcessDocument = () => {
    processModalRef.current?.showModal();
    // Focus input field after modal opens
    setTimeout(() => {
      inputRef.current?.focus();
    }, 100);
  };

  const handleIndex = () => {
    indexModalRef.current?.showModal();
    // Focus date input field after modal opens
    setTimeout(() => {
      indexDateRef.current?.focus();
    }, 100);
  };

  const handleScan = () => {
    // Reset to default (Today)
    const today = new Date().toISOString().split('T')[0];
    setScanDate(today);
    setScanDatePreset('today');
    scanModalRef.current?.showModal();
    // Focus date input field after modal opens
    setTimeout(() => {
      scanDateRef.current?.focus();
    }, 100);
  };

  const handleProcessSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    const id = parseInt(documentId.trim());
    if (isNaN(id) || id <= 0) {
      setMessage({ type: 'error', text: 'Please enter a valid document ID (positive number)' });
      return;
    }

    setLoading(true);
    setMessage(null);

    try {
      const response = await apiService.processDocument(id);
      setDocumentId('');
      processModalRef.current?.close();
      setMessage({
        type: 'success',
        text: `Document ${id} has been queued for processing. ${response.document_count || 1} document(s) in queue.`,
      });
      setTimeout(() => setMessage(null), 3000);
    } catch (err: any) {
      setMessage({
        type: 'error',
        text: err.response?.data?.detail || err.message || 'Failed to process document',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleIndexSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    setLoading(true);
    setMessage(null);

    try {
      const olderThan = indexDate.trim() || undefined;
      await apiService.triggerIndex(olderThan);
      setIndexDate('');
      indexModalRef.current?.close();
      setMessage({
        type: 'success',
        text: 'Index job started successfully',
      });
      setTimeout(() => setMessage(null), 3000);
    } catch (err: any) {
      setMessage({
        type: 'error',
        text: err.response?.data?.detail || err.message || 'Failed to start index job',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleScanDatePresetChange = (preset: string) => {
    setScanDatePreset(preset);
    
    const today = new Date();
    let dateValue = '';
    
    switch (preset) {
      case 'today':
        dateValue = today.toISOString().split('T')[0];
        break;
      case 'this-week':
        const weekStart = new Date(today);
        weekStart.setDate(today.getDate() - today.getDay()); // Start of week (Sunday)
        dateValue = weekStart.toISOString().split('T')[0];
        break;
      case 'this-month':
        dateValue = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-01`;
        break;
      case 'this-year':
        dateValue = `${today.getFullYear()}-01-01`;
        break;
      case 'all':
        dateValue = '';
        break;
      default:
        return;
    }
    
    setScanDate(dateValue);
  };

  const handleScanSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    setLoading(true);
    setMessage(null);

    try {
      const newerThan = scanDate.trim() || undefined;
      await apiService.triggerScan(newerThan);
      setScanDate('');
      setScanDatePreset('');
      scanModalRef.current?.close();
      setMessage({
        type: 'success',
        text: 'Scan job started successfully',
      });
      setTimeout(() => setMessage(null), 3000);
    } catch (err: any) {
      setMessage({
        type: 'error',
        text: err.response?.data?.detail || err.message || 'Failed to start scan job',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {/* Floating Action Button */}
      <div className="fixed bottom-6 right-6 z-50">
        <div className="fab">
          {/* Main FAB Button - must be first child */}
          <div
            tabIndex={0}
            role="button"
            className="btn btn-lg btn-circle btn-primary"
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
              }
            }}
          >
            <FaPlus className="w-6 h-6" />
          </div>

          {/* Action Buttons - shown when FAB is open */}
          <div onClick={handleScan} className="cursor-pointer">
            <span className="cursor-pointer">Scan for bad titles</span>
            <button
              className="btn btn-lg btn-circle"
              onClick={handleScan}
              disabled={loading}
            >
              <FaSearch className="w-5 h-5" />
            </button>
          </div>
          <div onClick={handleIndex} className="cursor-pointer">
            <span className="cursor-pointer">Index items</span>
            <button
              className="btn btn-lg btn-circle"
              onClick={handleIndex}
              disabled={loading}
            >
              <FaDatabase className="w-5 h-5" />
            </button>
          </div>
          <div onClick={handleProcessDocument} className="cursor-pointer">
            <span className="cursor-pointer">Add document ID for processing</span>
            <button
              className="btn btn-lg btn-circle"
              onClick={handleProcessDocument}
              disabled={loading}
            >
              <FaFileAlt className="w-5 h-5" />
            </button>
          </div>
        </div>
      </div>

      {/* Process Document Modal */}
      <dialog ref={processModalRef} className="modal">
        <div className="modal-box">
          <form method="dialog">
            <button
              type="submit"
              className="btn btn-circle btn-ghost absolute right-2 top-2"
              onClick={() => {
                setDocumentId('');
                setMessage(null);
              }}
            >
              <span className="text-xl">✕</span>
            </button>
          </form>
          
          <h3 className="font-bold text-lg mb-4">Process Document</h3>
          
          <form onSubmit={handleProcessSubmit}>
            <fieldset className="fieldset">
              <input
                id="documentId"
                ref={inputRef}
                type="number"
                placeholder="Enter document ID"
                className="input"
                value={documentId}
                onChange={(e) => setDocumentId(e.target.value)}
                disabled={loading}
                min="1"
                required
              />
              <p className="label">Enter a document ID to manually trigger processing and renaming.</p>
            </fieldset>

            {message && message.type === 'error' && (
              <div className="alert alert-error mt-4">
                <span>{message.text}</span>
              </div>
            )}

            <div className="modal-action">
              <button
                type="submit"
                className={`btn btn-primary ${loading ? 'loading' : ''}`}
                disabled={loading || !documentId.trim()}
              >
                {loading ? 'Processing...' : 'Process Document'}
              </button>
            </div>
          </form>
        </div>
        <form method="dialog" className="modal-backdrop">
          <button onClick={() => {
            setDocumentId('');
            setMessage(null);
          }}>close</button>
        </form>
      </dialog>

      {/* Index Modal */}
      <dialog ref={indexModalRef} className="modal">
        <div className="modal-box">
          <form method="dialog">
            <button
              type="submit"
              className="btn btn-circle btn-ghost absolute right-2 top-2"
              onClick={() => {
                setIndexDate('');
                setMessage(null);
              }}
            >
              <span className="text-xl">✕</span>
            </button>
          </form>
          
          <h3 className="font-bold text-lg mb-4">Index Items</h3>
          
          <form onSubmit={handleIndexSubmit}>
            <fieldset className="fieldset">
              <legend className="fieldset-legend">Date Filter (Optional)</legend>
              <input
                id="indexDate"
                ref={indexDateRef}
                type="date"
                className="input input-bordered w-full"
                value={indexDate}
                onChange={(e) => setIndexDate(e.target.value)}
                disabled={loading}
              />
              <p className="label">
                <span className="label-text-alt whitespace-normal break-words">Only documents older than this date will be indexed. Leave empty to index all documents.</span>
              </p>
            </fieldset>

            {message && message.type === 'error' && (
              <div className="alert alert-error mt-4">
                <span>{message.text}</span>
              </div>
            )}

            <div className="modal-action">
              <button
                type="submit"
                className={`btn btn-primary ${loading ? 'loading' : ''}`}
                disabled={loading}
              >
                {loading ? 'Starting...' : 'Start Index'}
              </button>
            </div>
          </form>
        </div>
        <form method="dialog" className="modal-backdrop">
          <button onClick={() => {
            setIndexDate('');
            setMessage(null);
          }}>close</button>
        </form>
      </dialog>

      {/* Scan Modal */}
      <dialog ref={scanModalRef} className="modal">
        <div className="modal-box">
          <form method="dialog">
            <button
              type="submit"
              className="btn btn-circle btn-ghost absolute right-2 top-2"
              onClick={() => {
                setScanDate('');
                setScanDatePreset('');
                setMessage(null);
              }}
            >
              <span className="text-xl">✕</span>
            </button>
          </form>
          
          <h3 className="font-bold text-lg mb-4">Scan for Bad Titles</h3>
          
          <form onSubmit={handleScanSubmit}>
            <fieldset className="fieldset">
              <legend className="fieldset-legend">Date Filter (Optional)</legend>
              <div className="join w-full mb-4">
                <input
                  className={`join-item btn btn-sm flex-1 ${scanDatePreset === 'today' ? 'btn-secondary' : ''}`}
                  type="radio"
                  name="scanDatePreset"
                  aria-label="Today"
                  checked={scanDatePreset === 'today'}
                  onChange={() => handleScanDatePresetChange('today')}
                  disabled={loading}
                />
                <input
                  className={`join-item btn btn-sm flex-1 ${scanDatePreset === 'this-week' ? 'btn-secondary' : ''}`}
                  type="radio"
                  name="scanDatePreset"
                  aria-label="This week"
                  checked={scanDatePreset === 'this-week'}
                  onChange={() => handleScanDatePresetChange('this-week')}
                  disabled={loading}
                />
                <input
                  className={`join-item btn btn-sm flex-1 ${scanDatePreset === 'this-month' ? 'btn-secondary' : ''}`}
                  type="radio"
                  name="scanDatePreset"
                  aria-label="This month"
                  checked={scanDatePreset === 'this-month'}
                  onChange={() => handleScanDatePresetChange('this-month')}
                  disabled={loading}
                />
                <input
                  className={`join-item btn btn-sm flex-1 ${scanDatePreset === 'this-year' ? 'btn-secondary' : ''}`}
                  type="radio"
                  name="scanDatePreset"
                  aria-label="This year"
                  checked={scanDatePreset === 'this-year'}
                  onChange={() => handleScanDatePresetChange('this-year')}
                  disabled={loading}
                />
              </div>
              <div className="relative">
                <input
                  id="scanDate"
                  ref={scanDateRef}
                  type="date"
                  className={`input input-bordered w-full ${scanDate ? 'pr-10' : ''}`}
                  value={scanDate}
                  onChange={(e) => {
                    setScanDate(e.target.value);
                    setScanDatePreset(''); // Clear preset when manually editing
                  }}
                  disabled={loading}
                />
                {scanDate && (
                  <button
                    type="button"
                    className="absolute right-2 top-1/2 -translate-y-1/2 btn btn-ghost btn-xs btn-circle z-10"
                    onClick={() => {
                      setScanDate('');
                      setScanDatePreset('');
                    }}
                    disabled={loading}
                    aria-label="Clear date"
                  >
                    <FaTimes className="w-3 h-3" />
                  </button>
                )}
              </div>
              <p className="label">
                <span className="label-text-alt whitespace-normal break-words">Only documents newer than this date will be scanned. Leave empty to scan all documents.</span>
              </p>
            </fieldset>

            {message && message.type === 'error' && (
              <div className="alert alert-error mt-4">
                <span>{message.text}</span>
              </div>
            )}

            <div className="modal-action">
              <button
                type="submit"
                className={`btn btn-primary ${loading ? 'loading' : ''}`}
                disabled={loading}
              >
                {loading ? 'Starting...' : 'Start Scan'}
              </button>
            </div>
          </form>
        </div>
        <form method="dialog" className="modal-backdrop">
          <button onClick={() => {
            setScanDate('');
            setScanDatePreset('');
            setMessage(null);
          }}>close</button>
        </form>
      </dialog>

      {/* Toast Messages */}
      {message && (
        <div className="toast toast-center toast-top z-50">
          <div className={`alert ${message.type === 'success' ? 'alert-success' : 'alert-error'}`}>
            <span>{message.text}</span>
          </div>
        </div>
      )}
    </>
  );
}

