# Secrets

Ten katalog jest **gitignorowany** (tylko `.gitkeep` i `README.md` w repo).

Tu trafia plik service account key do Vertex AI. Dokładną nazwę pliku
i ścieżkę zapisz w lokalnym `.env` (`GOOGLE_SA_KEY_FILE=./secrets/<nazwa>.json`).

Plik jest mountowany do kontenerów jako read-only volume pod ścieżką
`/gcp/sa-key.json` (zmienna `GOOGLE_APPLICATION_CREDENTIALS`).
