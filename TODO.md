# EXR-SBS-Converter Feature Requests

Here is a list of features to be added to the EXR-SBS-Converter tool.

## Feature 1: UI Cleanup and UX Improvement
- [x] Remove `_SBS` folders from the shots list.
- [x] Decouple shot selection from checkbox toggling. Clicking a shot should not affect its checkbox.
- [x] Add "Open Mono Folder" and "Open SBS Folder" buttons when a shot is selected.

## Feature 2: Shot Details Display
- [x] Display shot details upon selection:
    - [x] Frame count
    - [x] Conversion status
    - [x] Compression type
    - [x] Basic `oiio` stats

## Feature 3: Dropbox Upload Status
- [x] Display Dropbox upload status for each shot (UI and placeholder logic).
- [x] Use icons to indicate upload status (Not Started, In Progress, Complete).
- [x] Show a progress indicator: `frames uploaded / total frames` and percentage.

**Note:** The Dropbox upload status is currently implemented with placeholder data. A full integration with the Dropbox API would be required for real-time status updates.