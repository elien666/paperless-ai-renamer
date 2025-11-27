import { useState } from 'react';
import { apiService } from '../services/api';
import { FaPlus } from 'react-icons/fa';

export default function DocumentProcessor() {
  const [isOpen, setIsOpen] = useState(false);
  const [documentId, setDocumentId] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
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
      setMessage({
        type: 'success',
        text: `Document ${id} has been queued for processing. ${response.document_count || 1} document(s) in queue.`,
      });
      setDocumentId('');
      // Close modal after a short delay on success
      setTimeout(() => {
        setIsOpen(false);
        setMessage(null);
      }, 2000);
    } catch (err: any) {
      setMessage({
        type: 'error',
        text: err.response?.data?.detail || err.message || 'Failed to process document',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setIsOpen(false);
    setDocumentId('');
    setMessage(null);
  };

  return (
    <>
      {/* Button */}
      <button
        className="btn btn-primary btn-sm"
        onClick={() => setIsOpen(true)}
      >
        <FaPlus className="w-4 h-4" />
        Do something
      </button>

      {/* Modal */}
      <dialog className={`modal ${isOpen ? 'modal-open' : ''}`}>
        <div className="modal-box">
          <h3 className="font-bold text-lg mb-4">Process Document</h3>
          
          <p className="text-sm text-base-content/70 mb-4">
            Enter a document ID to manually trigger processing and renaming.
          </p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="form-control">
              <label className="label" htmlFor="documentId">
                <span className="label-text">Document ID</span>
              </label>
              <input
                id="documentId"
                type="number"
                placeholder="Enter document ID"
                className="input input-bordered w-full"
                value={documentId}
                onChange={(e) => setDocumentId(e.target.value)}
                disabled={loading}
                min="1"
                required
              />
            </div>

            {message && (
              <div className={`alert ${message.type === 'success' ? 'alert-success' : 'alert-error'}`}>
                <span>{message.text}</span>
              </div>
            )}

            <div className="modal-action">
              <button
                type="button"
                className="btn"
                onClick={handleClose}
                disabled={loading}
              >
                Cancel
              </button>
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
        <form method="dialog" className="modal-backdrop" onClick={handleClose}>
          <button>close</button>
        </form>
      </dialog>
    </>
  );
}
