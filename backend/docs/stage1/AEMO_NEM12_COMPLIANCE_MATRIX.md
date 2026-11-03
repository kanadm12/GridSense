# AEMO NEM12 compliance and source-time validation

**Review date:** 31 October 2026\
**Status:** MDFF v2.7 format details verified; clock basis and channel direction
remain blocked\
**Scope:** NEM12 records, not certification of a specific meter upload

## Authoritative source reviewed

The official AEMO PDF was downloaded from the link below and inspected as a
47-page PDF. Its title page states **Meter Data File Format Specification
NEM12 & NEM13**, version **2.7**, status **FINAL**, effective **1 December
2025**. The revision was approved for distribution on 31 March 2025.

- [Official MDFF v2.7 PDF](https://www.aemo.com.au/-/media/files/electricity/nem/retail_and_metering/market_settlement_and_transfer_solutions/2025/mdff-specification-nem12-nem13-v27.pdf)
- NEM12 inspection is under the document's section 4.
- The NEM12 file's record 100 identifies `NEM12`; it does not identify the
  MDFF specification revision used to create the file.

The v2.7 effective date is not applied retroactively by this project. A source
record whose `IntervalDate` predates 1 December 2025 may be governed by an
earlier MDFF revision or source-specific arrangement. GridSense does not know
the governing revision for historical uploads. Such a file must not be
retroactively certified as v2.7-compliant merely because it parses.

## Source-grounded interpretation matrix

| Requirement | AEMO source and exact location | Wording summary from source | Applicability / verification | GridSense implementation |
|---|---|---|---|---|
| File date representation and end-of-day convention | MDFF v2.7, §3.3.2, p. 7 | `Date(8)` is `CCYYMMDD`; the end-of-day standard is `00:00` on the following day. | Verified for v2.7 file coordinates; this does not establish a timezone or UTC offset. Historical revision applicability is not known. | Preserve source `IntervalDate` and 1-based position. Construct a naive nominal interval-end candidate. Do not assign UTC or fixed UTC+10. |
| Interval position and interval-end mapping | MDFF v2.7, §3.3.3, pp. 7–8 | Values are sequential; interval 1 ends at `00:05`, `00:15`, or `00:30` on `IntervalDate` for 5-, 15-, or 30-minute intervals; the final interval ends at `00:00` on the next date. | Verified as the MDFF's nominal day/index convention. Clock basis and DST realization are not specified by these clauses. | `timestamp` is the naive nominal end coordinate derived from date plus index. `source_interval_date` and `source_interval_number` retain the unambiguous source coordinates. UTC normalization is withheld. |
| Number of values in one daily interval record | MDFF v2.7, §4.4, p. 11 | A 300 record has a repeating interval-value field; the number of values equals `1440 / IntervalLength`. | Verified for this format revision. Thus a 30-minute 300 record has 48 values; it is not itself proof of a 46/48/50-slot local civil-day mapping. | Parser retains the source record shape and warns for short records. Tests demonstrate 48 nominal positions versus 46/50 Melbourne civil-day slots. No DST-to-UTC conversion is implemented. |
| NMI configuration and channel identifiers | MDFF v2.7, §4.3, pp. 9–10 | The 200 record carries NMI, NMIConfiguration, RegisterID, NMISuffix, MDMDataStreamIdentifier, serial, UOM and interval length. NMIConfiguration is the site's suffix configuration; RegisterID and stream identifier refer to named MSATS/CATS data. NMISuffix semantics are defined by the NMI Procedure. | Field layout verified. Field meaning that would establish import/export is not present in this section. NMI Procedure version/applicability remains blocked. | Preserve NMI configuration on each parsed interval and MDM stream identifier on the meter/channel. Register and suffix are opaque identifiers. Parser always emits `direction="unknown"`. |
| Import/export direction | MDFF v2.7, §4.3, p. 10; related NMI Procedure and source-specific MSATS/meter configuration required | The 200 record fields identify configuration/register/suffix/stream; the record does not define a GridSense import/export direction field or a universal suffix-to-direction rule. | No direction mapping verified. The official procedures page was blocked; NMI Procedure v7.4 and applicable meter/source-specific configuration could not be inspected. | No `E1`, `B1`, register, or stream suffix is mapped to import/export. Unknown and legacy null/B readings remain excluded from validated metrics. |
| Uniform 300 quality and method | MDFF v2.7, §4.4, p. 11; Appendix C, p. 23; Appendix D, p. 24 | 300 `QualityMethod` applies to every interval unless it is `V`. Codes: `A` actual; `E` forward estimated; `F` final substituted; `S` substituted; `V` indicates variable per-interval data and is only a 300-record summary. F/S require a method flag; S requires a reason. `V` is not a per-interval quality flag. | These labels/relationships are verified for v2.7. Appendix D says method numbers correspond to substitution types in Metrology Procedure Part B §2.6; that procedure was not retrieved, so individual method numbers are not interpreted. | Preserve full method text and derive per-interval quality only for uniform non-V records. Preserve `V` separately as `source_record_quality_method`; individual readings remain unresolved until valid 400 ranges are applied. |
| 400 event ranges | MDFF v2.7, §4.5, p. 13 | Start/End are inclusive 1-based interval numbers. Ranges must be ascending and cover the full day without gaps or overlaps. A 400 record is mandatory for 300 `V`; `V` itself is not allowed as a 400 quality method. | Verified for v2.7. | Parser buffers contiguous 400 records, validates complete ordered coverage, and applies each range to its exact source interval number. Invalid/missing partitions make the day's individual quality unresolved; no event is blanket-applied to the day. |
| Reason code field and `V` behavior | MDFF v2.7, §3.3.5, p. 8; §§4.4–4.5, pp. 11, 13; Appendix E, pp. 25–30 | S/F require reason codes; F does not take a reason code; A may carry information and requires codes 61, 79, or 89 for the specified meter events; V has no reason code. Code 0 requires a free-text description. Appendix E enumerates v2.7 codes. | Field relationships verified. Whether an A reason is mandatory depends on the underlying meter event, which the CSV alone may not establish. Version-specific code validity for older files remains unknown. | Parser checks numeric shape, code 0 description, S/F requirements and V restrictions; it retains the reason code but does not infer a physical event or whitelist code validity across unknown historical revisions. |
| UOM | MDFF v2.7, §4.3, p. 10; Appendix B, p. 22 | UOM is mandatory; Appendix B lists energy, power, voltage, current and other units. | Verified for v2.7. A value's meaning depends on its UOM; power is not interval energy. | Normalize only `Wh` to `kWh`; `kWh` is retained. Other units and original values are preserved but excluded from kWh analytics. No unverified MWh or power-to-energy conversion is performed. |
| Related procedure: clock, daylight saving, datastream/direction rules | NMI Procedure (user-cited v7.4); Metrology Procedure Part B; source-specific procedures | The MDFF explicitly delegates suffix semantics to the NMI Procedure and method-number interpretation to Metrology Procedure Part B. The PDF clauses reviewed do not supply a timezone, UTC offset, DST rule, or import/export suffix mapping. | **BLOCKED.** The official AEMO metering-procedures page returned HTTP 403 through the page fetch; a direct browser-style request returned an AEMO Cloudflare challenge. The named related documents and their effective versions could not be retrieved or independently verified. | No conversion from NEM12 naive coordinates to UTC and no register/suffix direction mapping. Block dependent customer consumption, billing, forecasting and scheduling claims. |

## IntervalDate, 48 records, and Melbourne DST

For a 30-minute interval record, MDFF v2.7 defines exactly 48 nominal values.
Index `i` maps to the nominal interval end `IntervalDate 00:00 + i × 30
minutes`; therefore index 1 ends at 00:30 on `IntervalDate` and index 48 ends
at 00:00 on the next date. This is the source-file coordinate convention, not
a UTC conversion.

Separately, a Melbourne local civil day can span 23, 24, or 25 hours, yielding
46, 48, or 50 expected half-hour UTC slots. MDFF's `1440 / IntervalLength`
daily record shape and a local civil-day slot count are different contracts.
The reviewed MDFF text does not state how a 48-value interval sequence is
realized across a local daylight-saving transition. Until the applicable
procedures establish the time standard and clock-reset/repeated/missing-time
rules, a 48-value NEM12 daily record on a DST date cannot be mapped to
Melbourne UTC instants. GridSense preserves `IntervalDate` and interval index,
sets `source_time_basis="unverified_nem12_clock_basis"`, and withholds UTC
metrics.

## Record 200: channel identity is not direction evidence

The parser now retains these distinct 200 fields:

- NMI configuration (copied to each source reading, since it can vary in time);
- RegisterID and NMISuffix (retained on the meter/channel);
- MDMDataStreamIdentifier (retained separately from NMISuffix);
- meter serial, UOM, and interval length.

The current data model now uses MDMDataStreamIdentifier when separating
channels. This prevents two stream identifiers from being merged solely
because their NMI/register/suffix fields match. It does **not** make a channel
an import or export. No historic record's direction is backfilled. For actual
direction assignment, implementation still requires the source's applicable
NMI Procedure/MSATS configuration and a reviewed, source-specific mapping.

## Record 300/400 quality resolution

The parser keeps the full 300 summary method separately. For non-variable
records it retains interval quality/method/reason at the uniform record level.
For a 300 `V`, it starts each value as unresolved, then applies 400 records only
if the ranges:

1. are valid inclusive 1-based ranges within the daily interval count;
2. appear in ascending contiguous order, with no gaps or overlaps;
3. cover every interval in the 300 record;
4. contain a valid non-V QMM shape and valid quality/reason field relations.

If any condition fails, individual quality is `U` and per-interval method and
reason are withheld; source values and nominal interval coordinates remain
available for audit. Method-number semantics and historical reason-code
applicability are not inferred.

## Effective-date and source applicability limits

- The new v2.7 fixture is dated 1 December 2025, the version's stated effective
  date. It is generated test data and not a real customer file.
- Existing repository sample data contains `IntervalDate` values from April
  2025, before v2.7 took effect. It remains a parser regression sample, not
  evidence of v2.7 conformance.
- NEM12 record 100 does not encode the MDFF specification version. No source
  upload-to-specification-version linkage currently exists.
- The effective version of NMI Procedure v7.4, Metrology Procedure Part B, and
  any applicable source-specific requirements for any uploaded customer file
  remains unverified. Do not certify any real NEM12 customer consumption.

## Outstanding blockers

1. Obtain the official metering-procedures page and the applicable NMI
   Procedure revision(s), including the exact effective dates and the sections
   defining NMIConfiguration, suffix, register, datastream, and direction
   evidence.
2. Obtain Metrology Procedure Part B and verify the revision applicable to
   each source data period, including method flags and substitutions/
   estimation semantics.
3. Verify the governing time standard and interval-boundary realization for
   NEM12 data, including DST and clock-reset behavior.
4. Obtain source-specific configuration evidence tying an individual
   datastream to import/export for each meter and effective period.
5. Establish source-document revision provenance for uploaded historical data;
   the NEM12 file's 100 record alone is insufficient.

Until blockers 1–4 are closed, NEM12-derived import/export totals, bills,
forecasts, recommendations, and scheduling inputs remain unavailable or
explicitly non-customer simulations.
