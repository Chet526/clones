# Product Requirements Document

## GeoBrief LE — Investigator Location Evidence Processor

## 1. Product Summary

GeoBrief LE is a clean-room, local-first software tool for law-enforcement investigators to process location evidence from spreadsheets, provider returns, phone records, app records, vehicle location data, tower dumps, and extraction exports.

The main goal is simple:

An investigator should be able to upload a file, answer a few plain-English questions, and get a map, timeline, Google Earth file, cleaned spreadsheet, and report-ready summary without needing to understand Excel, GIS, time zones, or provider-specific formatting.

This product should be built for the investigator who struggles with computers, not for a trained crime analyst.

---

## 2. Clean-Room Rule

This product must not copy Badge Apps, AMP, Pinged, BadgeMaps, or any competitor's private files, code, database, UI, branding, wording, documentation, legal-process database, or backend structure.

This is a clean-room rebuild of the general investigative workflow:

messy location records → cleaned data → map → timeline → report → court-ready export.

All code, designs, parser logic, templates, documentation, and branding must be original or based on lawful public sources, user-created sample data, agency-provided redacted examples, or original development.

---

## 3. Problem Statement

Investigators frequently receive location-related records in formats that are hard to understand. These may include:

- Google records
- Snapchat records
- Facebook / Instagram / Meta records
- AT&T, Verizon, T-Mobile, and other carrier returns
- Phone pings
- Tower dumps
- Geofence returns
- Vehicle telematics
- GPS tracker data
- Cellebrite / GrayKey exports
- CSV, XLSX, JSON, PDF, KML, KMZ, and ZIP files

Most investigators are not trained in GIS. Many struggle with spreadsheets, time zones, coordinate formats, data cleaning, and Google Earth exports.

A single time-zone mistake, coordinate error, or bad spreadsheet filter can create problems in a case. The software must reduce these risks by guiding the user step by step.

---

## 4. Product Vision

Build the easiest investigative location-evidence tool for law enforcement.

The product should let an investigator:

1. Create or open a case.
2. Upload records.
3. Let the system detect the file type and location data.
4. Confirm the time zone.
5. Review warnings.
6. Generate a map.
7. Export a Google Earth file.
8. Generate a report or court exhibit packet.

The user experience should feel like:

> "Upload the records. The software does the hard part."

---

## 5. Target Users

Primary users:

- Detectives
- Criminal investigators
- Drug task force officers
- ICAC / online predator investigators
- Patrol deputies working urgent cases
- Missing-person investigators
- Prosecutors reviewing evidence
- Agency administrators
- Crime analysts assisting smaller agencies

The product should be usable by both technical and nontechnical personnel.

---

## 6. Core Product Goals

**Goal 1: Make evidence processing simple**

The user should not have to know how to clean a spreadsheet, convert timestamps, or manually build a map.

**Goal 2: Reduce investigator mistakes**

The system should detect invalid coordinates, missing timestamps, time-zone uncertainty, duplicate records, and low-accuracy points.

**Goal 3: Preserve evidence integrity**

The original file must never be altered. Every imported file should be hashed and logged.

**Goal 4: Create court-ready exports**

The system should produce clean, explainable outputs that can be used in reports, briefings, warrant support, prosecutor review, and court exhibits.

**Goal 5: Default to local-first processing**

Sensitive investigative data should process locally by default. Cloud features should be optional and clearly labeled.

---

## 7. Non-Goals

The product will not:

- Obtain records without legal process.
- Hack accounts, providers, phones, or databases.
- Replace probable-cause analysis.
- Make legal conclusions for the investigator.
- Upload sensitive data to the cloud by default.
- Copy a competitor's backend, app, parser library, or database.
- Sell surveillance tools to private citizens.
- Allow public tracking, stalking, or non-law-enforcement misuse.

---

## 8. MVP Scope

The first MVP should be a local desktop application or local-first web app running on the user's machine.

MVP must include:

- Case workspace
- File upload
- CSV/XLSX support
- Automatic latitude/longitude detection
- Timestamp detection
- Manual column mapping
- Time-zone conversion
- Coordinate validation
- Source-file SHA-256 hashing
- Cleaned CSV export
- Interactive map
- Timeline filter
- Google Earth KML export
- Basic PDF/JSON processing report
- Simple guided wizard
- Audit log
- Training/sample mode

MVP should not include yet:

- Full live ping system
- Full agency cloud collaboration
- Legal process guide database
- Mobile app
- RMS/CAD integration
- AI legal conclusions
- Automated warrant drafting as final output

---

## 9. Product Modules

### Module A: Case Workspace

Each investigation should have a case folder/workspace.

Required fields:

- Case number
- Agency name
- Investigator name
- Offense type
- Suspect identifier
- Victim identifier
- Device/account identifiers
- Notes
- Source files
- Processed records
- Exports
- Audit log

Required actions:

- Create case
- Open case
- Add files
- Process files
- View map
- Export report
- Export audit log

Acceptance criteria:

- User can create a new case in under 60 seconds.
- Original uploaded files are preserved unchanged.
- Every file receives a SHA-256 hash.
- Every import/export action is logged.

---

### Module B: File Intake and Detection

The system should accept files and automatically identify useful data.

MVP file types:

- CSV
- XLSX
- XLS

Phase 2 file types:

- JSON
- PDF
- ZIP
- KML
- KMZ
- TXT
- XML
- GeoJSON
- Cellebrite exports
- GrayKey exports

The system should detect:

- Latitude
- Longitude
- Timestamp
- Accuracy radius
- Altitude
- Speed
- Heading
- Provider/source
- Device ID
- Account ID
- Phone number
- IP address
- Tower ID
- Event type

User-facing detection summary:

> "I found 418 records. 397 have usable coordinates. The timestamps appear to be in UTC. There are 21 rows with missing or invalid location data."

Acceptance criteria:

- User can drag and drop a file.
- System identifies likely coordinate columns.
- System identifies likely timestamp columns.
- System warns when it cannot confidently detect fields.
- User can manually map columns if detection fails.

---

### Module C: Guided Wizard

The main user flow should be a wizard, not a technical data screen.

Wizard steps:

1. Upload your file
2. Confirm what type of file this is
   - Phone company records
   - App/company records
   - Google records
   - Social media records
   - Vehicle records
   - Extraction export
   - I don't know
3. Confirm detected columns
   - Latitude
   - Longitude
   - Time/date
   - Accuracy
4. Choose time zone
   - Agency time zone
   - Case location time zone
   - UTC
   - Help me decide
5. Choose output
   - Map
   - Google Earth file
   - Clean spreadsheet
   - Report
   - All of the above
6. Review warnings
7. Generate output

Acceptance criteria:

- First-time user can complete a basic map without training.
- Each screen has one clear main button.
- Every technical warning is explained in plain English.
- "I don't know" is always an available option.

---

### Module D: Data Cleaning Engine

The system should convert messy records into a consistent internal format.

Standard internal location record:

- Record ID
- Case ID
- Source file ID
- Source row number
- Provider/source type
- Original timestamp
- Original time zone
- Normalized UTC timestamp
- Display timestamp
- Display time zone
- Latitude
- Longitude
- Accuracy radius
- Altitude
- Speed
- Heading
- Address if available
- Device ID
- Account ID
- Phone number
- IP address
- Tower ID
- Event type
- Validation status
- Warnings
- Investigator notes

Cleaning functions:

- Trim spaces
- Normalize headers
- Convert coordinates to numbers
- Detect invalid coordinates
- Detect reversed latitude/longitude
- Convert timestamps
- Detect duplicates
- Flag low-accuracy points
- Flag missing data
- Preserve original values

Validation statuses:

- Valid
- Missing coordinate
- Missing timestamp
- Invalid coordinate
- Low accuracy
- Duplicate
- Time-zone uncertain
- Possible lat/long reversal
- Excluded from map

Acceptance criteria:

- Original data is preserved.
- Cleaned data is traceable to original rows.
- Bad rows are not silently deleted.
- Warnings appear in the report.

---

### Module E: Time Zone Intelligence

Time-zone handling is one of the most important parts of the product.

The system should detect and handle:

- UTC
- Local time
- Zulu time
- Unix epoch time
- ISO 8601 timestamps
- Date-only values
- Mixed formats

User-facing explanation:

> "The source file appears to use UTC. Your case is set to Central Time. The report will show Central Time while preserving the original UTC time in the audit log."

Requirements:

- Never silently guess when confidence is low.
- Always preserve original timestamp.
- Always show converted timestamp.
- Every report must include a time-zone statement.
- User must confirm uncertain conversions.

Acceptance criteria:

- User can select display time zone.
- Report shows original and converted time logic.
- Time-zone uncertainty is flagged.

---

### Module F: Map Interface

The map should be simple and field-friendly.

Default map features:

- Point map
- Accuracy circles
- Timeline order
- Clickable point details
- Address search
- Date/time filter
- Source/provider filter
- Measurement tool
- Export screenshot button

Large primary buttons:

- Show All
- Filter Time
- Play Timeline
- Find Address
- Measure Distance
- Export Google Earth
- Make Report

Point popup should show:

- Date/time
- Original time
- Converted time
- Provider/source
- Source file
- Row number
- Coordinates
- Accuracy
- Notes
- Validation warning if any

Acceptance criteria:

- User can view all valid points.
- User can toggle accuracy circles.
- User can filter by date/time.
- User can click a point and see source details.
- User can export the map.

---

### Module G: Timeline and Animation

The timeline should let investigators see movement over time.

Features:

- Play/pause animation
- Speed control
- Date/time slider
- First point / last point
- Gaps in time
- Movement path
- Dwell locations
- Multiple devices/accounts
- Important point markers

Timeline insights:

- First known point
- Last known point
- Total mapped points
- Longest time gap
- Points near selected location
- Points during selected offense window

Acceptance criteria:

- User can animate points chronologically.
- User can filter to a time window.
- User can mark important moments.
- User can export timeline screenshots.

---

### Module H: Google Earth Export

The product should support Google Earth because many investigators already use it.

Required exports:

- KML
- KMZ

KML/KMZ should include:

- Points
- Timestamps
- Accuracy circles
- Path lines
- Source folders
- Provider folders
- Important markers
- Notes
- Legend
- Export metadata

Each placemark should include:

- Case number
- Date/time
- Source file
- Source row
- Coordinates
- Accuracy
- Notes
- Validation warning

Acceptance criteria:

- Export opens in Google Earth Pro.
- Points are organized by source/provider/date.
- Metadata is included.
- Accuracy radius is represented.

---

### Module I: Report Generator

The report generator should create investigator-ready summaries.

Report types:

**1. Basic Processing Report**

Includes:

- Case number
- Agency
- Investigator
- Date processed
- Source files
- SHA-256 hashes
- Record count
- Valid point count
- Invalid/skipped row count
- Time range
- Time-zone statement
- Warnings
- Export list

**2. Investigative Summary**

Includes:

- Overview of processed records
- Important locations
- Important time windows
- Points near selected address
- Movement summary
- Investigator-selected records

**3. Court Exhibit Packet**

Includes:

- Cover page
- Map overview
- Timeline screenshots
- Legend
- Accuracy explanation
- Time-zone explanation
- Source-file hash table
- Selected records table
- Processing log

**4. Warrant Support Summary**

Includes factual language for investigator review, such as:

> "The uploaded records contained 418 location points between [date] and [date]. After processing, 397 records contained valid coordinates. Several records placed the device within approximately [distance] of [location] during the selected time period."

The system must not present this as final legal language.

Acceptance criteria:

- User can generate PDF report.
- Report includes hashes.
- Report includes warnings.
- Report includes time-zone explanation.
- User can edit narrative before export.

---

### Module J: Evidence Integrity and Audit Log

Every case must maintain a defensible record.

Audit events:

- Case created
- File imported
- File hashed
- File processed
- Column mapping changed
- Time zone selected
- Records filtered
- Points excluded
- Report generated
- KML exported
- User edited notes
- Case archived

Each source file should store:

- Original filename
- File size
- SHA-256 hash
- Import date/time
- Imported by
- Parser used
- Parser confidence

Acceptance criteria:

- Original files are never overwritten.
- Audit log cannot be edited through normal UI.
- Every export is traceable to source files.
- User edits are logged.

---

### Module K: Provider Parser System

Provider parsers should be modular.

Each parser should define:

- Provider name
- Supported file types
- Required columns
- Optional columns
- Timestamp rules
- Coordinate rules
- Accuracy rules
- Known quirks
- Validation tests
- Last updated date

Initial parser priorities:

1. Generic CSV/XLSX
2. Google location records
3. Snapchat records
4. Meta/Facebook/Instagram records
5. AT&T records
6. Verizon records
7. T-Mobile records
8. Tower dump records
9. Vehicle location records
10. Cellebrite / GrayKey location exports

Parser confidence levels:

- High
- Medium
- Low
- Unknown

Acceptance criteria:

- System can detect provider template.
- Low-confidence parser requires user confirmation.
- User can manually map fields.
- Parser updates do not alter original files.

---

### Module L: Legal Process Guide

This should be Phase 2 or Phase 3.

Purpose:

Give investigators a searchable directory of where and how to send legal process.

Fields:

- Company name
- Parent company
- Product/app names
- Law enforcement portal
- Email
- Mailing address
- Emergency request process
- Preservation request process
- Subpoena requirements
- Search warrant requirements
- Court order requirements
- Required identifiers
- Available data types
- Retention notes
- Last verified date
- Verification source
- Agency notes

Clean-room requirement:

The legal-process database must be built from public company pages, agency-submitted corrections, verified sources, and original research. It must not copy another company's proprietary database.

Acceptance criteria:

- User can search by app, company, or data type.
- Every entry has last verified date.
- Outdated entries are flagged.
- User submissions require admin review.

---

### Module M: Live Ping / Field Mapping

This should be Phase 3 because it has higher operational and security risk.

Purpose:

Allow authorized investigators to receive and view live pings during active cases.

Features:

- Create live ping session
- Manually enter coordinates
- Secure email ingestion
- Auto-map new pings
- Alert users of new location
- Show accuracy radius
- Share with authorized team
- Export ping history
- End/archive session

Field interface:

- Large map
- Last known location
- Time since last ping
- Accuracy radius
- Navigate button
- Add note
- Notify team
- End session

Acceptance criteria:

- New pings appear on map.
- Authorized users receive alerts.
- All pings are logged.
- Session export is available.
- No public sharing links.

---

### Module N: Training Mode

Training mode should help computer-limited investigators learn safely.

Features:

- Fake sample cases
- Practice files
- Guided walkthrough
- "What is UTC?" explanation
- "What is accuracy radius?" explanation
- "How to export to Google Earth"
- "How to explain this in court"
- Common mistakes checklist

Acceptance criteria:

- Training data is clearly fake.
- Training exports are watermarked.
- User can complete practice workflow.
- Admin can view training completion.

---

### Module O: Admin and Agency Management

Agency version should include:

Roles:

- Super Admin
- Agency Admin
- Investigator
- Analyst
- Patrol User
- Prosecutor Viewer
- Auditor
- Training User

Admin features:

- Invite users
- Disable users
- Assign roles
- Require MFA
- Manage agency branding
- View audit logs
- Manage license seats
- Export compliance report
- Configure retention
- Configure local/cloud mode

Acceptance criteria:

- Admin can manage users.
- Admin can require MFA.
- Admin can export audit logs.
- Read-only users cannot alter data.

---

## 10. Security Requirements

Default architecture:

- Local-first processing
- Encrypted local case vault
- Encrypted database
- No default cloud upload
- User-controlled exports
- Optional agency cloud mode later

Security features:

- SHA-256 file hashing
- Audit logging
- Role-based access
- MFA for agency mode
- Session timeout
- Encrypted storage
- Tamper-resistant logs
- Admin export logs
- No third-party analytics on case data

Privacy rules:

- Do not train AI models on agency data without written agreement.
- Do not send case data to cloud services by default.
- Do not create public case links.
- Redaction tools must be available for exports.
- Every external transmission must be logged.

---

## 11. AI Features

AI should assist, not decide.

Allowed AI features:

- Explain uploaded data in plain English
- Draft report summaries
- Explain time-zone conversions
- Identify missing fields
- Suggest filters
- Summarize movement
- Draft factual warrant-support language
- Generate prosecutor-friendly summaries

AI must not:

- Invent facts
- Determine guilt
- Determine probable cause
- Make final legal conclusions
- Hide warnings
- Alter original data
- Create final warrant language without review

Every AI output should say:

> "Draft language generated from processed records. Investigator must verify before use."

---

## 12. Technical Architecture

Recommended MVP stack:

- Python processing engine
- FastAPI backend if web-based
- React frontend
- Tauri or Electron for desktop
- SQLite local database
- SQLCipher or encrypted local vault
- pandas / openpyxl for spreadsheets
- MapLibre or Folium for maps
- simplekml or custom KML writer
- WeasyPrint / Playwright / ReportLab for PDF exports
- SHA-256 hashing
- Local file storage

Optional future cloud stack:

- Next.js frontend
- FastAPI or Node backend
- PostgreSQL + PostGIS
- S3-compatible encrypted storage
- SSO/SAML/OIDC
- Agency tenant isolation
- Centralized audit logs

---

## 13. Data Model

**Case**

- case_id
- agency_id
- case_number
- title
- offense_type
- investigator_id
- created_at
- updated_at
- status
- notes

**SourceFile**

- source_file_id
- case_id
- original_filename
- file_type
- file_size
- sha256_hash
- imported_by
- imported_at
- provider_detected
- parser_used
- parser_confidence
- storage_path

**LocationRecord**

- location_record_id
- case_id
- source_file_id
- source_row_number
- provider
- source_type
- original_timestamp
- normalized_timestamp_utc
- display_timestamp
- display_timezone
- latitude
- longitude
- accuracy_radius
- altitude
- speed
- heading
- address
- ip_address
- device_id
- account_id
- event_type
- validation_status
- warnings
- notes

**Export**

- export_id
- case_id
- export_type
- filename
- generated_by
- generated_at
- included_files
- included_records
- filters_applied
- export_hash

**AuditEvent**

- audit_event_id
- case_id
- user_id
- event_type
- event_details
- timestamp
- device_id
- ip_address
- immutable_hash

---

## 14. UX Requirements

The product must use plain language.

Replace technical terms:

- "Geospatial layer" → "Map layer"
- "Temporal filter" → "Date/time filter"
- "Coordinate validation" → "Check location points"
- "KML serialization" → "Google Earth file"
- "Parser schema" → "File reader"

Design rules:

- Large buttons
- Few choices per screen
- Clear next step
- No blank error screens
- Plain-English warnings
- "Help me decide" buttons
- "I don't know" option
- Training tooltips
- Dark mode and light mode

Example user messages:

- "I found location data in this file."
- "Some rows do not have latitude or longitude. I can still map the usable rows and list the skipped rows in your report."
- "The file appears to use UTC time. I will convert it to Central Time and preserve the original UTC values."
- "Some points have a large accuracy radius. These may show a general area instead of an exact location."

---

## 15. MVP User Stories

**Story 1: Basic file upload**

As an investigator, I want to upload a CSV or Excel file so the software can find location points and create a map.

Acceptance criteria:

- User uploads file.
- System detects coordinate columns.
- System detects timestamp column.
- System maps valid points.
- System reports skipped rows.

**Story 2: Time-zone conversion**

As an investigator, I want the system to convert UTC times into local case time so my report is understandable.

Acceptance criteria:

- System detects likely UTC.
- User confirms display time zone.
- Report includes time-zone explanation.

**Story 3: Google Earth export**

As an investigator, I want a Google Earth file so I can open the map in a tool I already know.

Acceptance criteria:

- User exports KML/KMZ.
- File opens in Google Earth.
- Points include source metadata.

**Story 4: Court exhibit**

As an investigator, I want a clean report packet with map screenshots, hashes, and time-zone notes.

Acceptance criteria:

- PDF includes maps.
- PDF includes hashes.
- PDF includes warnings.
- PDF includes selected important points.

**Story 5: Nontechnical user**

As a user who struggles with computers, I want the software to guide me through each step.

Acceptance criteria:

- Wizard uses plain language.
- User can choose "I don't know."
- System recommends safe defaults.
- User can complete the workflow without Excel formulas or GIS work.

---

## 16. Roadmap

**Phase 1: Prototype**

- CSV/XLSX upload
- Coordinate detection
- Time detection
- Cleaning engine
- Basic map
- Cleaned CSV export
- JSON summary
- SHA-256 hashing

**Phase 2: MVP**

- Case workspace
- Guided wizard
- Manual column mapping
- Time-zone confirmation
- Validation warnings
- KML export
- PDF processing report
- Audit log
- Training mode

**Phase 3: Beta**

- Provider parser templates
- Google parser
- Snapchat parser
- Meta parser
- Carrier parser
- Tower dump parser
- Timeline animation
- Court exhibit builder
- Agency branding

**Phase 4: Agency Version**

- User accounts
- Role-based access
- Admin panel
- MFA
- Encrypted case vault
- Legal-process guide beta
- Parser update system

**Phase 5: Advanced Version**

- Live ping module
- Mobile companion app
- Team collaboration
- Secure email ingestion
- Prosecutor viewer
- Cloud optional mode
- SSO
- CAD/RMS integration
- Advanced tower/cell analysis

---

## 17. Success Metrics

MVP success targets:

- User can generate a map from a basic CSV/XLSX file in under 3 minutes.
- 80% of common files have auto-detected coordinate columns.
- First-time user can complete the guided workflow without live training.
- Every processed file receives a hash.
- Every report includes source file, count, time range, and warnings.
- Beta users can produce KML and report exports without developer help.

Business/product metrics:

- Number of files processed
- Number of maps generated
- Number of KML exports
- Number of reports generated
- Average upload-to-map time
- Percentage of successful parser detections
- Number of warnings resolved
- Training completion rate
- Agency renewal rate

---

## 18. Risks and Mitigations

**Risk: Provider file formats change**

Mitigation:

- Modular parsers
- Manual column mapping
- Parser updates
- Agency-submitted sample files

**Risk: Time-zone mistakes**

Mitigation:

- Preserve original timestamp
- Require confirmation
- Include time-zone statement
- Flag uncertainty

**Risk: Evidence admissibility concerns**

Mitigation:

- Preserve original files
- Hash source files
- Maintain audit log
- Generate methodology reports
- Avoid unsupported conclusions

**Risk: Agencies distrust cloud storage**

Mitigation:

- Local-first default
- Optional cloud only
- Clear data-flow explanation
- Encrypted storage

**Risk: Nontechnical users still struggle**

Mitigation:

- Guided wizard
- Plain language
- Training mode
- Big buttons
- Help prompts

---

## 19. Recommended Product Name

Preferred:

**GeoBrief LE**

Tagline:

> "Turn location records into maps, timelines, and reports."

Other options:

- CaseMap LE
- EvidenceMap
- TracePoint LE
- SignalMap
- WarrantMap
- CellMap Pro
- LocateCase
- FieldMap Evidence

---

## 20. Final Product Definition

GeoBrief LE is a local-first evidence processing tool that helps investigators turn confusing location records into:

- Clean maps
- Timelines
- Google Earth files
- Cleaned spreadsheets
- Source-file hash logs
- Processing reports
- Court-ready exhibits
- Investigator-reviewed summaries

The entire product should be designed around this standard:

A busy investigator with limited computer skills should be able to upload records, follow plain-English prompts, and produce a defensible map and report without needing a crime analyst, GIS training, or advanced Excel knowledge.

---

## 21. Release Governance and Launch Evidence

To support defensibility, reproducibility, and commercial reliability, each market launch must include release-governance evidence.

Required controls:

- CI must pass on the launch-governance commit used for release signoff.
- The release record must include an annotated governance snapshot tag.
- Customer install instructions must pin to an immutable commit SHA.
- Launch checklist must classify items as blocker, conditional-blocker, or optional.
- Conditional controls must include scope boundaries and explicit signoff requirements when activated.

Acceptance criteria:

- A reviewer can identify one governance snapshot tag for the release.
- A reviewer can verify the customer install pin SHA from public docs.
- A reviewer can trace CI pass evidence (run ID/URL) for the launch-governance commit.
- A reviewer can determine, from documented scope rules, whether conditional controls are required for the deployment profile.
