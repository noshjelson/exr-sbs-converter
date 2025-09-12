# EXR-SBS-Converter TODO

## High Priority Fixes
- [ ] **Verify Dropbox Upload Status:** The current placeholder logic for Dropbox status is not always accurate. Implement a verification step to ensure the number of files in the Dropbox folder matches the number of SBS frames before marking a shot as "Complete".
- [ ] **Correct Dropbox Button URL:** The Dropbox button should link to the specific, correct folder for the selected shot. The current URL is a placeholder and needs to be replaced with a dynamic link.
- [ ] **Fix UI Alignment:** The Dropbox status text (`X/Y frames`) in the shots list is misaligned. It needs to be shifted to the right so it correctly falls under the "SBS Dropbox Upload Status" column header.

---

## Feature Requests

### Live Mode Stability and Safety
- [ ] **Prevent Race Conditions:** Implement a "File Stability Delay" to ensure the tool does not attempt to convert an EXR file while it is still being written by another application (e.g., Unreal Engine).
    - [ ] Add a "File Stability Delay (s)" setting to the UI, defaulting to a safe value (e.g., 10 seconds).
    - [ ] The live conversion logic must check that a source EXR file's modification time has not changed for the specified delay period before starting a conversion. This will prevent file locking and potential crashes.
- [ ] **Aggressive Temp File Cleanup:** Before a conversion process begins for a shot, the tool should automatically delete any orphaned `tmp*.exr` files from that shot's `_SBS` directory. This will prevent the buildup of failed temp files.

### Completed Features
- [x] **UI Cleanup and UX Improvement:**
    - [x] Remove `_SBS` folders from the shots list.
    - [x] Decouple shot selection from checkbox toggling.
    - [x] Add "Open Mono Folder" and "Open SBS Folder" buttons.
- [x] **Shot Details Display:**
    - [x] Display frame count, conversion status, compression, and `oiio` stats.
- [x] **Dropbox Upload Status:**
    - [x] Display Dropbox upload status for each shot (UI and placeholder logic).
    - [x] Use icons to indicate upload status.
    - [x] Show a progress indicator (`frames uploaded / total frames`).

**Note:** The Dropbox upload status is currently implemented with placeholder data. A full integration with the Dropbox API would be required for real-time status updates.