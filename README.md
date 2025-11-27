# Paperless AI Renamer

A local, Dockerized AI-powered service that integrates with Paperless-ngx to automatically rename documents using a local LLM and RAG (Retrieval Augmented Generation).

## Features

- **Local LLM Integration**: Uses Ollama for intelligent title generation
- **Vision Model Support**: Automatically detects and processes image documents using vision LLMs
- **RAG-Based Learning**: Learns from your existing "good" document titles
- **Webhook Support**: Processes documents automatically when added to Paperless
- **Manual Controls**: Trigger scans and indexing on-demand via API
- **Dry Run Mode**: Preview changes without modifying documents
- **Date Filtering**: Process documents by date range
- **Configurable Prompts**: Customize the AI's instructions
- **Language Support**: Generate titles in your preferred language (default: German)
- **Regex-Based Detection**: Flexible pattern matching for "bad" titles

## Quick Start

1. **Clone and Configure**:
   ```bash
   cd paperless-agent-rename
   ```

2. **Edit `docker-compose.yml`**:
   Update the environment variables (see [Configuration](#configuration) below):
   ```yaml
   environment:
     - PAPERLESS_API_URL=http://your-paperless-url:8000
     - PAPERLESS_API_TOKEN=your_api_token_here
     - BAD_TITLE_REGEX=^(Scan|\\\\d{4}[-/]\\\\d{2}[-/]\\\\d{2}).*
     - DRY_RUN=True  # Set to False when ready to apply changes
   ```

3. **Start the Services**:
   ```bash
   docker-compose up -d
   ```

4. **Pull the LLM Models**:
   ```bash
   docker exec -it ollama ollama pull llama3
   docker exec -it ollama ollama pull moondream  # For image document processing
   ```

5. **Build Your Baseline** (Index existing "good" documents):
   ```bash
   curl -X POST "http://localhost:8000/index?older_than=2024-01-01"
   ```

6. **Test with a Scan**:
   ```bash
   curl -X POST "http://localhost:8000/scan?newer_than=2024-01-01"
   ```

7. **Monitor Logs**:
   ```bash
   docker-compose logs -f app
   ```

## Usage

### Manual Scan
Trigger a search for documents with "bad" titles:
```bash
curl -X POST "http://localhost:8000/scan?newer_than=2025-11-01"
```

### Bulk Index
Build your baseline by indexing existing documents with good titles:
```bash
curl -X POST "http://localhost:8000/index?older_than=2024-01-01"
```

### Find Outliers
Identify documents that are isolated in the vector space (likely have poor titles):
```bash
curl -X GET "http://localhost:8000/find-outliers?k_neighbors=5&limit=50"
```

**Parameters**:
- `k_neighbors` (default: 5): Number of nearest neighbors to check for each document. Higher values provide more context but take longer.
- `limit` (default: 50): Maximum number of outliers to return.

**How it works**: For each document, the service finds its K nearest neighbors in the vector space and calculates the average distance. Documents with high average distances are isolated and likely have poor titles that don't match their content.

**Response**: Returns a JSON list of documents sorted by outlier score (highest = most isolated):
```json
{
  "status": "success",
  "count": 50,
  "outliers": [
    {
      "document_id": "839",
      "title": "Haus Links",
      "outlier_score": 1.3547,
      "avg_distance_to_neighbors": 1.3547
    },
    ...
  ]
}
```

### Process Specific Documents
Process a list of document IDs for renaming:
```bash
curl -X POST "http://localhost:8000/process-documents" \
  -H "Content-Type: application/json" \
  -d '{"document_ids": [123, 456, 789]}'
```

### Webhook Integration

Configure Paperless-ngx to send webhooks:
1. Go to Paperless Settings → Webhooks
2. Add webhook URL: `http://paperless-ai-renamer:8000/webhook`
3. Set trigger to `DOCUMENT_ADDED` or `DOCUMENT_CREATED`

#### Webhook Flow Explained

When a document is uploaded to Paperless, the following happens automatically:

1. **Document Upload**: You upload a file (e.g., "Scan.pdf" or "IMG_1234.jpg") to Paperless
2. **Paperless Processing**: Paperless processes the document (OCR, text extraction, etc.)
3. **Webhook Notification**: Paperless sends a webhook POST request to your service with `{"document_id": 839, ...}`
4. **Immediate Response**: Your service responds immediately with `{"status": "processing_started", "document_id": 839}` (non-blocking)
5. **Background Processing**: The service processes the document in the background:
   - Fetches document details from Paperless API
   - Detects document type (image vs. text) via MIME type
   - **For Images**: Downloads image → Vision model analyzes → Generates title in configured language
   - **For Text**: Finds similar documents (RAG) → Text LLM generates title in configured language
6. **Title Update**: If a better title is generated, the document is updated in Paperless
7. **Indexing**: The new title is added to the vector database for future learning

**Key Points**:
- Processing happens asynchronously (doesn't block Paperless)
- Images automatically use the vision model
- Text documents use RAG with the text LLM
- All titles are generated in your configured language (default: German)

### Health Check
```bash
curl http://localhost:8000/health
```

## Configuration

Configure the service by editing the `environment` section in `docker-compose.yml`:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `PAPERLESS_API_URL` | `http://paperless-webserver:8000` | URL of your Paperless-ngx instance |
| `PAPERLESS_API_TOKEN` | *Required* | Your Paperless API Token |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | URL of the Ollama service |
| `LLM_MODEL` | `llama3` | The Ollama model to use |
| `ENABLE_SCHEDULER` | `False` | Enable background job to periodically search for bad titles |
| `CRON_SCHEDULE` | `*/30 * * * *` | Cron expression for the scheduler (if enabled) |
| `BAD_TITLE_REGEX` | `^Scan.*` | Regex pattern to identify documents that need renaming |
| `DRY_RUN` | `False` | If `True`, logs proposed changes without updating Paperless |
| `PROMPT_TEMPLATE` | *See default in code* | Custom prompt for the LLM. Must include `{language}`, `{examples}`, `{content}`, `{filename}` |
| `VISION_MODEL` | `moondream` | The Ollama vision model to use for image documents |
| `LANGUAGE` | `German` | Language for generated titles (e.g., `German`, `English`, `French`) |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | SentenceTransformer model for embeddings |
| `CHROMA_DB_PATH` | `/app/data/chroma` | Path to store the vector database |

### Example: Custom Regex for Bad Titles

To match documents starting with "Scan" OR a date:
```yaml
- BAD_TITLE_REGEX=^(Scan|\\d{4}[-/]\\d{2}[-/]\\d{2}|\\d{2}[-/]\\d{2}[-/]\\d{4}).*
```

### Example: Custom Prompt Template

```yaml
- PROMPT_TEMPLATE=Analyze this document: {content}. The original file is {filename}. Based on these examples: {examples}, suggest a better title in {language}.
```

Note: The prompt template must include `{language}`, `{examples}`, `{content}`, and `{filename}` placeholders.

### Example: Change Language

To generate titles in English instead of German:
```yaml
- LANGUAGE=English
```

Or in French:
```yaml
- LANGUAGE=French
```

## API Documentation

For complete API documentation, see:
- **OpenAPI Specification**: [`openapi.json`](openapi.json) - Full API schema in OpenAPI 3.1.0 format
- **Postman Collection**: [`postman_collection.json`](postman_collection.json) - Import into Postman for testing

### API Overview

| Method | Endpoint | Description | Parameters |
|--------|----------|-------------|------------|
| `GET` | `/health` | Health check endpoint | None |
| `POST` | `/scan` | Trigger manual scan for documents with bad titles | `newer_than` (optional): Filter by date (YYYY-MM-DD) |
| `POST` | `/index` | Bulk index existing documents with good titles | `older_than` (optional): Filter by date (YYYY-MM-DD) |
| `GET` | `/find-outliers` | Find documents isolated in vector space (poor titles) | `k_neighbors` (default: 5): Number of neighbors to check<br>`limit` (default: 50): Max results to return |
| `POST` | `/process-documents` | Process specific document IDs for renaming | Body: `{"document_ids": [123, 456, ...]}` |
| `GET` | `/progress` | Get progress of scan jobs | `job_id` (optional): Specific job ID, or omit for all jobs |
| `POST` | `/webhook` | Webhook endpoint for Paperless-ngx | Body: `{"document_id": 123, ...}` |

### Endpoint Details

#### `GET /health`
Simple health check to verify the service is running.
```bash
curl http://localhost:8000/health
```

#### `POST /scan`
Manually trigger a search for documents matching `BAD_TITLE_REGEX`. Returns a `job_id` for tracking progress.
```bash
curl -X POST "http://localhost:8000/scan?newer_than=2024-01-01"
# Response: {"status": "scan_started", "job_id": "uuid", "newer_than": "2024-01-01"}
```

#### `POST /index`
Index existing documents with good titles into the vector database. Use this to build your baseline before scanning.
```bash
curl -X POST "http://localhost:8000/index?older_than=2024-01-01"
```

#### `GET /find-outliers`
Find documents that are outliers in the vector space (likely have poor titles). See [Find Outliers](#find-outliers) section for detailed explanation.
```bash
curl "http://localhost:8000/find-outliers?k_neighbors=5&limit=50"
```

#### `POST /process-documents`
Process a specific list of document IDs. Useful for targeting specific documents.
```bash
curl -X POST "http://localhost:8000/process-documents" \
  -H "Content-Type: application/json" \
  -d '{"document_ids": [123, 456, 789]}'
```

#### `GET /progress`
Get progress information for scan jobs. Without `job_id`, returns all jobs.
```bash
# Get all jobs
curl "http://localhost:8000/progress"

# Get specific job
curl "http://localhost:8000/progress?job_id=your-job-id"
```

#### `POST /webhook`
Webhook endpoint for Paperless-ngx. Automatically processes documents when they're added. See [Webhook Integration](#webhook-integration) for setup.

## How It Works

1. **Indexing Phase**: The service indexes your existing documents with good titles into a vector database (ChromaDB). This builds a knowledge base for RAG (Retrieval Augmented Generation).

2. **Document Detection**:
   - **Via Webhook**: All documents are processed automatically when added to Paperless (no regex filtering)
   - **Via Manual Scan**: Only documents matching `BAD_TITLE_REGEX` are processed

3. **MIME Type Detection**: The service automatically detects the document type using multiple fallback strategies:
   - Checks the Paperless API response for MIME type fields (`original_mime_type`, `mime_type`, `media_type`)
   - Falls back to HTTP headers from the download endpoint
   - Infers from file extension if needed

4. **Document Processing**:
   - **Image Documents**: Downloads the original image → Vision model (`VISION_MODEL`) analyzes the image → Generates title in configured language
   - **Text Documents**: Finds similar documents using RAG → Text LLM (`LLM_MODEL`) generates title based on content and examples → Generates title in configured language

5. **Title Evaluation**: The AI compares the generated title with the original:
   - If different and better → Updates Paperless (unless `DRY_RUN=True`)
   - If same → Logs that title is already good
   - If generation failed → Logs error, no update

6. **Learning**: The new title is added to the vector database for future RAG retrieval, improving title generation over time.

## Architecture

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────┐
│  Paperless-ngx  │─────▶│  AI Renamer API  │─────▶│   Ollama    │
│                 │      │   (FastAPI)      │      │   (LLM)     │
└─────────────────┘      └──────────────────┘      └─────────────┘
                                  │
                                  ▼
                         ┌─────────────────┐
                         │    ChromaDB     │
                         │ (Vector Store)  │
                         └─────────────────┘
```

## Troubleshooting

### No results when scanning
- Check that `BAD_TITLE_REGEX` is properly escaped in `docker-compose.yml`
- Verify the regex pattern matches your document titles
- Check logs: `docker-compose logs -f app`

### Embedding model not found
The `sentence-transformers` library downloads the model automatically on first use. You'll see "Batches: 100%" in the logs when generating embeddings.

### LLM not responding
Ensure you've pulled the models:
```bash
docker exec -it ollama ollama pull llama3
docker exec -it ollama ollama pull moondream  # Required for image documents
```

### MIME type not detected
If the log shows empty MIME types (e.g., `MIME: `), the service will automatically:
1. Try to get the MIME type from the download response headers
2. Infer from the file extension as a fallback

If image documents are still not being processed, check:
- The document is actually an image file (jpg, png, etc.)
- The vision model is pulled: `docker exec -it ollama ollama pull moondream`
- Check logs for any errors during image processing

## Development

### Running Tests
```bash
python -m pytest tests/
```

### Project Structure
```
.
├── app/
│   ├── main.py              # FastAPI application
│   ├── config.py            # Configuration management
│   └── services/
│       ├── ai.py            # AI/LLM/Vector Store
│       └── paperless.py     # Paperless API client
├── tests/
│   └── test_flow.py         # Unit tests
├── docker-compose.yml       # Service orchestration
├── Dockerfile               # Python service image
└── requirements.txt         # Python dependencies
```

## License

MIT
