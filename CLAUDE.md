# data_analysis

## Response style
- Be as concise and to the point as possible.
- Lead with the result, then a short note on method and any caveats. No step-by-step walkthroughs unless asked.
- Use bullets and tables over paragraphs; skip preamble and recaps.
- Keep replies short: a few lines when possible.
- Use plain language. Avoid technical jargon; if a technical term is needed, explain it in a few words.

## Data
- `S061226-v50.txt.gz`: raw data, ~18 GB compressed. Treat as read-only.
- Never load it fully into memory; stream it (`gzcat | head`, chunked reads, or polars/duckdb lazy scans).
