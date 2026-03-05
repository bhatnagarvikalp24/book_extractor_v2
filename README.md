# PDF Book Metadata Extractor

Upload up to 50 PDFs and automatically extract: title, author, publisher, ISBN, copyright holder.
Results are ephemeral — all job state expires after 1 hour (no database).

## Setup

```bash
cp .env.example .env
# Edit .env — add OPENAI_API_KEY if you want LLM fallback for low-confidence results
```

## Run

```bash
docker-compose up --build
```

- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/extract` | Upload PDFs, returns `{job_id}` |
| GET | `/extract/{job_id}/status` | Poll job progress |
| GET | `/extract/{job_id}/results` | Fetch all results |
| GET | `/extract/{job_id}/export?format=csv\|json` | Download export |
