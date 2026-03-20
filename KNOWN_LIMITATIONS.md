# KNOWN_LIMITATIONS

- Automatic inline chaining of `generate -> apply_headers -> pdf` is not universal across all document-generation entrypoints.
- Brand asset selection is ID-based and assumes existing uploaded files.
- Repository still contains historical docs and compatibility modules that remain on disk for backward compatibility, even though the canonical paths are documented separately.
