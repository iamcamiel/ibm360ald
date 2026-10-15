# Older SLT card catalog: source review

Source: `D:/Reference Materials/IBM 360/SLT_Card_Schematics_Jan67.pdf` (455 PDF pages, 35,624,039 bytes, SHA-256 `32551F42C44F1A9F28CF6FD1D880412D84952712CBFB72B837586E84C54A8F5D`). The source is a raster scan with no extractable text. Every finding below was checked on rendered page images, using one-based PDF page numbers. The first printed card sheet is dated `1-67`; page 217 prints `Jan. 67`. Card sheets are organized largely by `580xxxx` part number, followed by a short supplemental card run at PDF pages 382-410 and non-card material.

## What the card sheets encode

- The upper-right `P/N` is the full seven-digit IBM card part number. The last four digits match the card-type shorthand in our database (for example, `5800494` / `0494` on PDF page 110 and `5803309` / `3309` on page 217). The adjacent `EC` is an engineering-change identifier, not a card type.
- Each card starts with a logic diagram and continues with one or more physical schematics; the footer gives the within-card page count. For example, `5800494` is a three-page set (PDF 110-112), and `5803309` a four-page set (PDF 217-220). Preserve the PDF page and within-card page when citing an observation.
- Card size `1-6` or `1-12` is printed in the title table and can check single- or double-width assignments. Page 110 says `5800494`, `1-6`; page 217 says `5803309`, `1-12`.
- Box interiors show the printed function, unit code and portion. On PDF page 110, the `5800494` logic sheet has `AR / T06AA` portions `A1 B1 C1 D1 E1 F1 G1 H1 J1 K1` (no `I1`). For `A1`, the printed input is `D05` and its two right-side pin labels are `B02` and `D05`. The physical circuit on PDF page 111 gives component-level evidence for that card and its pin designations. The database also observes later or additional portions `M1 R1 U1 X1`; therefore this 1967 sheet is **not** a complete present-machine inventory.
- The catalog demonstrates that a card may contain multiple named logic stages and internal wiring, so one function or port-count signature per card type is unsafe. On PDF page 217, `5803309` portion `F` is drawn as `A / T03AC / F1` feeding `OR / T03AD / F2` feeding `N / T15AA / F3`; PDF page 218 shows the corresponding circuitry. PDF page 227 similarly draws `5803333` portions `A1-A5` as an internally connected succession of `A`, `N`, `OR`, `*SS`, and `A`. These are specific examples, not definitions of those function names.

## Requested debated types

The following twelve full part numbers are **not found in the catalog's printed part-number runs inspected at the brackets below**. This is an age/coverage limitation, not evidence against any current ALD reading or card database entry.

| Card shorthand | Main-run bracket (one-based PDF pages) | Supplemental-run check |
|---|---|---|
| `0141`, `0143` | `5800099` on pp. 35-37, then `5800197` on pp. 38-39 | Supplemental cards begin at `5800280` on p. 382 |
| `0490` | `5800489` on pp. 106-109, then `5800494` on pp. 110-112 | `5800387` on pp. 396-397, then `5800538` on pp. 398-399 |
| `0497`, `0500`, `0505` | `5800494` on pp. 110-112, then `5800509` on pp. 113-114 | `5800387` on pp. 396-397, then `5800538` on pp. 398-399 |
| `0512` | `5800509` on pp. 113-114, then `5800536` on pp. 115-116 | `5800387` on pp. 396-397, then `5800538` on pp. 398-399 |
| `3161` | `5803130` on pp. 200-203, then `5803165` on pp. 204-206 | Supplemental card run ends below this number (around p. 410) |
| `3311` | `5803309` on pp. 217-220, then `5803325` on pp. 221-223 | Same |
| `3365` | `5803345` on pp. 237-238, then `5803404` on pp. 239-240 | Same |
| `4633` | `5804007` on pp. 332-334, then `5805015` on pp. 338-341; pp. 335-337 have no new printed P/N at the upper-right location | Same |
| `8005` | `5807202` on pp. 374-376, then `5808045` on pp. 377-381 | Same |

The source contains no searchable text layer, and this check followed the main sequence and visible supplemental part-number sheets, not a machine-read OCR index of every pixel. The negative findings should be treated as catalog-coverage findings only.

## Confirmed overlap index (not exhaustive)

These fourteen printed P/Ns were directly read from rendered pages and have matching `json/Card types/xxxx.json` files in the current `ibm360ald` repository. The entries are useful starting points for source-bound pin/portion checks, not blanket authority for a later card revision.

| Card type | Full P/N | Checked PDF pages | Observed card-size or other immediate point |
|---|---|---|---|
| `0000` | `5800000` | 1-2 | `1-6`, `A / T03AB` portions on p. 1 |
| `0430` | `5800430` | 99-101 | `1-6` |
| `0494` | `5800494` | 110-112 | `1-6`, `AR / T06AA` portions A1-K1 excluding I1 |
| `0536` | `5800536` | 115-116 | `1-6` |
| `3028` | `5803028` | 180-182 | `1-12` |
| `3309` | `5803309` | 217-220 | `1-12`, grouped A/OR/N stages on p. 217 |
| `3325` | `5803325` | 221-223 | `1-12` |
| `3332` | `5803332` | 224-226 | `1-12` |
| `3333` | `5803333` | 227-230 | `1-12`, five internally connected stages on p. 227 |
| `3340` | `5803340` | 233-234 | `1-12` |
| `4007` | `5804007` | 332-334 | `1-12` |
| `5015` | `5805015` | 338-341 | `1-12` |
| `6194` | `5806194` | 354-356 | `1-12` |
| `7054` | `5807054` | 363-365 | `1-12` |

## Safe use in the transcription database

Store each catalog claim as a separate source observation keyed by **full part number + printed EC + PDF page + portion + pin**. Use it to propose and review a current ALD reading, but do not overwrite a literal 1970 ALD glyph or assume 1967 coverage is complete. In particular, the user's explanation of an `0143` group cannot be directly checked in this older catalog because `5800143` is absent. The nearby `5803309` and `5803333` diagrams support the general principle that card internals can be multi-stage, but they do not prove the specific `0143` C1/C2/C3 topology.

Rendered visual evidence: `catalog page 1.png`, `catalog page 110.png`, `catalog page 111.png`, `catalog page 217.png`, `catalog page 218.png`, `catalog page 227.png`, and targeted part-number contact sheets in this directory. No canonical ALD text, card-type database or repository file was changed for this review.
