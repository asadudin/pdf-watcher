# PDF Watcher

A Python application that watches a directory for new PDF files, processes them using Google Cloud Vision API to extract text, and saves the results.

## Features

- Monitors a directory for new PDF files
- Processes PDFs using Google Cloud Vision API for OCR
- Saves extracted text to output files
- Runs in a Docker container for easy deployment

## Prerequisites

- Python 3.7+
- Docker and Docker Compose
- Google Cloud account with Vision API enabled
- Service account credentials with Vision API access

## Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/asadudin/pdf-watcher.git
   cd pdf-watcher
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up your Google Cloud credentials:
   - Place your service account JSON key file as `credentials.json` in the project root
   - Or set the `GOOGLE_APPLICATION_CREDENTIALS` environment variable to point to your credentials file

## Usage

### Running with Python

```bash
python pdf_watcher.py
```

### Running with Docker

1. Build the Docker image:
   ```bash
   docker-compose build
   ```

2. Start the service:
   ```bash
   docker-compose up -d
   ```

3. Place PDF files in the `input` directory and find the extracted text in the `output` directory.

## Configuration

- `INPUT_DIR`: Directory to watch for PDF files (default: `./input`)
- `OUTPUT_DIR`: Directory to save extracted text (default: `./output`)
- `CREDENTIALS_PATH`: Path to Google Cloud credentials file (default: `./credentials.json`)

## License

MIT
