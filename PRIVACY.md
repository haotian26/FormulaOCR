# Privacy

FormulaOCR performs local OCR without a network connection. Opening, pasting,
capturing, editing, previewing, copying and browsing history do not upload an
image. A current image is uploaded only when API re-recognition is enabled and
the user explicitly clicks that action.

History and non-secret settings remain in macOS Application Support. API keys
remain in macOS Keychain. FormulaOCR does not persist uploaded temporary images,
raw API responses or secrets, and logs must not contain those values.
