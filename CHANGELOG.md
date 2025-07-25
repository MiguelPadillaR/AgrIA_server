# 📝 Changelog – Version 1.1 (July 2025)

### 🚀 New Features
- **Parcel Drawer:** Users can now draw custom parcel geometries directly on the map. The system captures, stores, and processes this geometry.
- **Combined Parcel Finder & Drawer View:** The two tools are now integrated on the same page using tabs for seamless switching.
- **Detailed Descriptions:** Added the option to toggle between TL;DR and detailed LLM-enriched parcel descriptions.
- **SIGPAC Info Display:** New table columns for classification and crop types, with updated form to support SIGPAC data entry.
- **Multilingual Content:** Full description examples and TL;DR summaries now include both Spanish and English versions.

---

### 🛠 Fixes & Improvements
- Improved error handling across UI and backend.
- Debug prints removed from backend after initial testing.
- Updated documentation and README content.

---

### 📦 Enhancements
- Enriched data pipeline from UI to backend, allowing more structured and complete parcel info flow.
- New tile provider for improved map rendering.
- Auto-display of last searched parcel info in chat view.
- Backend support for enriched LLM-based content parsing and formatting.
- Support for parsing parcel geometry and SIGPAC metadata on the server side.

---

## 🖥️ Server-Specific Changes
- Added routes to process and store custom geometry and metadata from the frontend.
- Integrated enriched LLM content into backend responses.
- Included logic to validate inputs, return detailed errors, and handle new SIGPAC-related payloads.
