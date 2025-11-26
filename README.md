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

This returns a JSON list of document IDs sorted by outlier score (highest = most isolated).

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

- **OpenAPI Spec**: See `openapi.json`
- **Postman Collection**: Import `postman_collection.json` into Postman

### Endpoints

- `GET /health` - Health check
- `POST /scan?newer_than=YYYY-MM-DD` - Trigger manual scan
- `POST /index?older_than=YYYY-MM-DD` - Trigger bulk indexing
- `GET /find-outliers?k_neighbors=5&limit=50` - Find outlier documents
- `POST /process-documents` - Process specific document IDs
- `POST /webhook` - Webhook endpoint for Paperless

## How It Works

1. **Indexing Phase**: The service indexes your existing documents with good titles into a vector database (ChromaDB)
2. **Detection**: When a new document arrives (via webhook or scan), it checks if the title matches your `BAD_TITLE_REGEX`
3. **MIME Type Detection**: The service automatically detects the document type:
   - Checks the Paperless API response for MIME type fields
   - Falls back to HTTP headers from the download endpoint
   - Infers from file extension if needed
4. **Document Processing**:
   - **Image Documents**: Uses the vision model (`VISION_MODEL`) to analyze the image and generate a title
   - **Text Documents**: Uses RAG retrieval to find similar documents, then the text LLM (`LLM_MODEL`) to generate a title
5. **Language**: All generated titles are created in the language specified by `LANGUAGE` (default: German)
6. **Update**: The new title is applied to Paperless (unless in dry run mode)

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
