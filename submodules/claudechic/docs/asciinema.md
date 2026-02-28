# Asciinema Recordings

We use [asciinema](https://asciinema.org) to embed terminal recordings in our docs.

## Embedding

Use the script tag format:

```html
<script src="https://asciinema.org/a/ID.js" id="asciicast-ID" async="true"></script>
```

Replace `ID` with the asciinema recording ID (e.g., `LqXYSEsLQIHmIEYQ`).

## Recording

```bash
asciinema rec demo.cast
```

Then upload at https://asciinema.org or via `asciinema upload demo.cast`.

## Our Recordings

| ID | Description | Used in |
|----|-------------|---------|
| `LqXYSEsLQIHmIEYQ` | Chess: agents playing against each other | agents.md |
