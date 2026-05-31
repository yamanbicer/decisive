"""Project-brief ingestion: turn an uploaded deck (PDF), demo video (MP4), and/or
a website URL into ONE structured, reusable Brief that flows into the council as
session context.

Self-contained subpackage (no coupling to the agent-tooling engine modules). Every
stage degrades gracefully: with no keys / no libs the pipeline yields a deterministic
mock brief and the council still convenes. Groq is used for AUDIO transcription only;
the council agents stay entirely on W&B Inference.
"""
