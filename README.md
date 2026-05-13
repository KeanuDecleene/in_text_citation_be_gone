# Citation Cleaner PDF

Citation Cleaner PDF is a small FastAPI web app that accepts a PDF, removes common in-text citations, and returns a cleaned PDF while preserving the original page structure and embedded images as closely as possible.

## What it does

- Uploads a PDF directly in the browser.
- Removes common citation styles such as `(Smith, 2020)`, `Johnson (2021)`, and `[12]`.
- Preserves page dimensions, page count, and embedded images.
- Avoids storing uploads on disk by processing files in memory.
- Skips content after headings like `References`, `Bibliography`, or `Works Cited` so the reference list is not rewritten.

## What it does not guarantee

PDF editing is much harder than editing plain text because PDFs are layout-first documents. This app preserves the existing layout by redacting edited text blocks and writing cleaned text back into the same block area. That means:

- Images stay intact.
- Overall page structure stays intact.
- Exact original typography may vary slightly in edited blocks if the PDF used embedded fonts that are not reusable for new text insertion.

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Free hosting

GitHub Pages will not run this app by itself because GitHub Pages is for static HTML, CSS, and JavaScript sites, while this project needs a live Python/FastAPI backend to process uploaded PDFs.

The simplest free option for this repo is Render. This project includes a root-level `render.yaml` file so you can deploy it as a Render Blueprint with minimal setup.

Typical flow:

1. Push the repo to GitHub.
2. In Render, create a new Blueprint and connect this repository.
3. Keep the default `render.yaml` path.
4. Deploy the web service.
5. Add the resulting `onrender.com` URL to your portfolio site, or attach your own custom domain if you have one.

For local development, nothing changes. You can still run the app with Uvicorn as shown above.
