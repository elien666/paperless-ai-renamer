import { useState, useRef } from 'react';
import { apiService } from '../services/api';
import { FaPlus, FaFileAlt, FaDatabase, FaSearch } from 'react-icons/fa';

export default function FloatingActionButton() {
  const modalRef = useRef<HTMLDialogElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [documentId, setDocumentId] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const handleProcessDocument = () => {
    modalRef.current?.showModal();
    // Focus input field after modal opens
    setTimeout(() => {
      inputRef.current?.focus();
    }, 100);
  };

  const handleIndex = async () => {
    setLoading(true);
    setMessage(null);
    
    try {
      await apiService.triggerIndex();
      setMessage({ type: 'success', text: 'Index job started successfully' });
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

  const handleScan = async () => {
    setLoading(true);
    setMessage(null);
    
    try {
      await apiService.triggerScan();
      setMessage({ type: 'success', text: 'Scan job started successfully' });
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
      modalRef.current?.close();
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
      <dialog ref={modalRef} className="modal">
        <div className="modal-box">
          <form method="dialog">
            {/* if there is a button in form, it will close the modal */}
            <button
              type="button"
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

