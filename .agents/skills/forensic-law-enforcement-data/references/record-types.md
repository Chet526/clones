# Record Type Playbook

## Tower Dump
- Key fields: cell_id, sector, azimuth, start/end time, event count.
- Typical caveats: high volume, non-target subscribers, sector overlap.
- Best use: coarse inclusion/exclusion, corroboration with narrower sources.

## CDR / CSLI
- Key fields: msisdn, imsi, imei, event type, timestamp, serving cell.
- Caveats: event-triggered sampling, sparse movement capture between events.
- Best use: sequence of network interactions, continuity checks.

## Geofence Return
- Key fields: device id, confidence radius, enter/exit times, source provider.
- Caveats: varying precision by provider/device permissions.
- Best use: proximity windows and movement hypotheses with uncertainty bands.

## App Location Export
- Key fields: latitude/longitude, accuracy, activity type, timestamp.
- Caveats: background throttling, device clock skew, permission changes.
- Best use: fine-grained movement and dwell reconstruction.

## ALPR / Camera / External Signals
- Key fields: timestamp, camera id, plate/entity, confidence.
- Caveats: OCR error, camera clock drift.
- Best use: independent corroboration of movement timeline.
