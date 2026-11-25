# Privacy

FormulaOCR uses offline OCR by default. With API enabled, clicking **API OCR**
sends the current image to the selected provider. Turning on **Use API recognition
by default** also sends each newly opened, pasted or captured image to the active
profile. Restoring a history record reads its saved result locally.

History and non-secret settings remain in macOS Application Support. API keys
remain in macOS Keychain. FormulaOCR does not persist uploaded temporary images,
raw API responses or secrets, and logs must not contain those values.

The optional **Check for Updates** button contacts the public GitHub Release
endpoint for `haotian26/FormulaOCR`. It runs only after that button is clicked;
it sends no images, formulas, history, API credentials or persistent device ID.
There is no background update check, automatic download or installation.

History export writes the selected LaTeX drafts and record/source labels to the
file chosen in the macOS Save dialog. Images, image paths and credentials are
not included. The exported file is outside FormulaOCR's managed history; it is
not removed when a history entry is deleted.

Backend diagnostics are bounded fixed event names, such as process startup or
protocol failure. They do not retain raw backend stderr or recognition content.
