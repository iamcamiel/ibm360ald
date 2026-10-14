"""Preserve review/provenance records and reusable historical tool sources.

Reads the coordinator's reviewed-export snapshot; never changes working files.
Run with --write to publish. Diagram content JSON/CSV is a separate import.
"""
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timezone
import argparse
import ast
import hashlib
import json


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def companion(text):
    key = text.name.split(' ', 1)[0]
    for path in [text.with_suffix('.json'),
                 text.with_name(text.stem+' verification.json'),
                 text.with_name(key+' verification.json'),
                 text.with_name(key+' review.json')]:
        if path.is_file():
            return path
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path,
                        default=Path(__file__).resolve().parents[3])
    parser.add_argument('--reference', type=Path,
                        default=Path('D:/Reference Materials/IBM 360/IBM_360_ALD'))
    parser.add_argument('--repo', type=Path,
                        default=Path(__file__).resolve().parents[2])
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    repo, workspace = args.repo.resolve(), args.workspace.resolve()
    assert (repo/'.git').is_dir(), 'Choose the ALD repository'
    exports = workspace/'ALD_Visual_Transcriptions'
    audit = workspace/'tmp/ald-text/ald/repository-export'
    manifest_raw = (audit/'last export manifest.json').read_bytes()
    exported = json.loads(manifest_raw)
    assert not exported.get('export_in_progress'), 'Wait for the text export'
    folders = {path.name for path in args.reference.iterdir() if path.is_dir()}
    by_family = {name[:2]: name for name in folders}
    planned = {}

    def add(destination, raw, source, role):
        destination = destination.resolve()
        assert destination.is_relative_to(repo)
        relative = destination.relative_to(repo).as_posix()
        item = {'path': relative, 'sha256': digest(raw),
                'source': str(source), 'role': role, '_raw': raw}
        if relative in planned:
            assert planned[relative]['sha256'] == item['sha256'], relative
        planned[relative] = item

    def copy(source, destination, role):
        add(destination, source.read_bytes(), source, role)

    # Keep original identities/order and current approved grid/glyph policies.
    copy(args.reference/'ALD Scan Order.csv', repo/'notes/ALD Scan Order.csv',
         'Original scan order and current TIFF filename catalogue')
    shared = {
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/OR function human correction current audit.json':
            'Manual verification/OR function human correction current audit.json',
        'tmp/ald-text/ald/card-type-database/Direct human card-type observations.json':
            'Card types/Direct human card-type observations.json',
        'tmp/ald-text/ald/card-type-database/Direct human OR function correction.json':
            'Card types/Direct human OR function correction.json',
        'tmp/ald-text/ald/card-type-database/Direct human additional function corrections.json':
            'Card types/Direct human additional function corrections.json',
        'tmp/ald-text/ald/card-type-database/Direct human function whitespace and R TO corrections.json':
            'Card types/Direct human function whitespace and R TO corrections.json',
        'tmp/ald-text/ald/ap3/root/Combined human function batches final exact audit.json':
            'AP Parallel Adder/Human function correction history/Combined human function batches final exact audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Recorded and recovered UTF8 application current audit.json':
            'Manual verification/Recorded and recovered UTF8 application current audit.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet-v5/Workbook binding manifest v5.json':
            'Manual verification/Workbook binding manifest v5.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet-v5/Workbook independent audit v5.json':
            'Manual verification/Workbook independent audit v5.json',
        'outputs/01a12afd-f7e4-7a21-aa71-cbee821ab67d/ALD manual verification questions v5.xlsx':
            'Manual verification/ALD manual verification questions v5.xlsx',
        'tmp/ald-text/ald/Parallel until complete coordination broadcast.json':
            'Parallel until complete coordination broadcast.json',
        'tmp/ald-text/ald/repository-export/Coordinator source review holds.json':
            'Coordinator source review holds.json',
        'tmp/ald-text/ald/repository-export/Coordinator transcription scope exclusions.json':
            'Coordinator transcription scope exclusions.json',
        'tmp/ald-text/ald/repository-export/ED direct human scope exclusion verified.json':
            'ED ROS Diagrams, Drivers/ED direct human scope exclusion verified.json',
        'tmp/ald-text/ald/filename-corrections/ED000-01 DT to ED folder move audit.json':
            'ED ROS Diagrams, Drivers/ED000-01 DT to ED folder move audit.json',
        'tmp/ald-text/rt/root/AR KU handoff.json':
            'RT T Register/AR KU half-workload handoff.json',
        'tmp/ald-text/ald/repository-export/ZA corrected source review hold release.json':
            'ZA Programmed Grounds/ZA corrected source review hold release.json',
        'tmp/ald-text/ald/repository-export/XM905 corrected source review hold release.json':
            'XM Mixer/XM905 corrected source review hold release.json',
        'tmp/ald-text/ls/physical-copy-2026-10-13/Frozen physical copy publication receipts.json':
            'LS LS Bus/Frozen physical copy publication receipts.json',
        'tmp/ald-text/ls/physical-copy-2026-10-13/Before physical copy snapshot receipt.json':
            'LS LS Bus/Before physical copy snapshot receipt.json',
        'tmp/ald-text/ls/workbook-46e7d24ea74f/Before returned workbook snapshot receipt.json':
            'LS LS Bus/Before returned workbook snapshot receipt.json',
        'tmp/ald-text/ls/workbook-46e7d24ea74f/Frozen workbook publication receipts.json':
            'LS LS Bus/Historical returned workbook publication receipts.json',
        'tmp/ald-text/ls/source-derived-2026-10-13/Before source-derived recovery snapshot receipt.json':
            'LS LS Bus/Before source-derived recovery snapshot receipt.json',
        'tmp/ald-text/ls/source-derived-2026-10-13/Frozen source-derived publication receipts.json':
            'LS LS Bus/Frozen source-derived publication receipts.json',
        'tmp/ald-text/ald/manual-verification/received/2026-10-13-46e7d24ea74f/Answer receipt.json':
            'Manual verification/2026-10-13 returned workbook answer receipt.json',
        'tmp/ald-text/ald/manual-verification/received/2026-10-13-46e7d24ea74f/Returned question workbook.xlsx':
            'Manual verification/2026-10-13 returned question workbook.xlsx',
        'tmp/ald-text/ald/manual-verification/received/2026-10-14-5796f6dd2e40/Answer receipt.json':
            'Manual verification/2026-10-14 returned V4 answer receipt.json',
        'tmp/ald-text/ald/manual-verification/received/2026-10-14-5796f6dd2e40/Returned question workbook.xlsx':
            'Manual verification/2026-10-14 returned V4 question workbook.xlsx',
        'tmp/ald-text/ald/manual-verification/spreadsheet/Workbook binding manifest v2.json':
            'Manual verification/Workbook binding manifest v2.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet/Question recovery decisions v2.json':
            'Manual verification/Question recovery decisions v2.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet/Workbook validation v2.json':
            'Manual verification/Workbook validation v2.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet/Workbook decision partition validation v2.json':
            'Manual verification/Workbook decision partition validation v2.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet/Workbook delivery receipt v2.json':
            'Manual verification/Workbook delivery receipt v2.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet/Workbook binding manifest v3.json':
            'Manual verification/Workbook binding manifest v3.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet/Workbook binding manifest v4.json':
            'Manual verification/Workbook binding manifest v4.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v4/WA140 WA150 corrected reference recoveries.json':
            'A1 Socket Listing/WA140 WA150 corrected reference recoveries.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v4/Pending inventory after V4.json':
            'Manual verification/Pending inventory after V4.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v4/C2A endpoint prefix direct human correction.json':
            'Manual verification/C2A endpoint prefix direct human correction.json',
        'tmp/ald-text/ald/manual-verification/socket-function-recovery-v1/Direct human socket function instructions.json':
            'Manual verification/Socket function reference checks/Direct human socket function instructions.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/C2A human correction current audit.json':
            'Manual verification/C2A human correction current audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/AP001 human socket correction current audit.json':
            'AP Parallel Adder/AP001 human socket correction current audit.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet/Workbook reconciliation audit v4.json':
            'Manual verification/Workbook reconciliation audit v4.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet/Workbook independent audit v4.json':
            'Manual verification/Workbook independent audit v4.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet/Workbook validation v4.json':
            'Manual verification/Workbook validation v4.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet/Workbook delivery receipt v4.json':
            'Manual verification/Workbook delivery receipt v4.json',
        'outputs/01a12afd-f7e4-7a21-aa71-cbee821ab67d/ALD manual verification questions v4.xlsx':
            'Manual verification/ALD manual verification questions v4.xlsx',
        'tmp/ald-text/ald/manual-verification/spreadsheet/Question recovery decisions v3.json':
            'Manual verification/Question recovery decisions v3.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet/Workbook validation v3.json':
            'Manual verification/Workbook validation v3.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet/Workbook decision partition validation v3.json':
            'Manual verification/Workbook decision partition validation v3.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet/Workbook delivery receipt v3.json':
            'Manual verification/Workbook delivery receipt v3.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Human J6 reference reading receipt.json':
            'Manual verification/Human J6 reference reading receipt.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Contextual independent cross-review v3.json':
            'Manual verification/Contextual independent cross-review v3.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/A1 contextual recovery candidates v3.json':
            'Manual verification/A1 contextual recovery candidates v3.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Non-A1 contextual recovery candidates v3.json':
            'Manual verification/Non-A1 contextual recovery candidates v3.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Source-derived acceptance adapter audit.json':
            'Manual verification/Source-derived acceptance adapter audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Supplementary source-derived acceptance adapter audit.json':
            'Manual verification/Supplementary source-derived acceptance adapter audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Next source-derived acceptance adapter audit.json':
            'Manual verification/Next source-derived acceptance adapter audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/WA accepted current audit.json':
            'Manual verification/WA accepted current audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/V3 current publication audit.json':
            'Manual verification/V3 current publication audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/KT V2 unchanged current rebind audit.json':
            'Manual verification/KT V2 unchanged current rebind audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/WA final current audit.json':
            'Manual verification/WA final current audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/WA301 current authority audit.json':
            'Manual verification/WA301 current authority audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/WA glyph and footer current audit.json':
            'Manual verification/WA glyph and footer current audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/FX RT V3 current publication audit.json':
            'Manual verification/FX RT V3 current publication audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/FX RT V3 unchanged Next RT binding audit.json':
            'RT T Register/FX RT V3 unchanged Next RT binding audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Human WA recurring glyph reading receipt.json':
            'WA Cable Routing/Human WA recurring glyph reading receipt.json',
        'tmp/ald-text/recovery-v3/Source derived independent reviews.json':
            'Manual verification/FX RT V3 source-derived independent reviews.json',
        'tmp/ald-text/recovery-v3/Published FX RT V3 family receipt.json':
            'Manual verification/Published FX RT V3 family receipt.json',
        'tmp/ald-text/recovery-v3/Completed V3 repository mirror receipt.json':
            'Manual verification/Completed FX RT V3 repository mirror receipt.json',
        'tmp/ald-text/recovery-v3/rt/Deferred RT381 source discrepancies.json':
            'RT T Register/Deferred RT381 source discrepancies.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/RT381 pending next-inventory reopenings.json':
            'RT T Register/RT381 pending next-inventory reopenings.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/WA verified human glyph closure.json':
            'WA Cable Routing/WA verified human glyph closure.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/Pending newly accepted XM015 questions.json':
            'XM Mixer/Pending newly accepted XM015 questions.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/Pending newly accepted AP751 AP762 AP763 questions.json':
            'AP Parallel Adder/Pending newly accepted AP751 AP762 AP763 questions.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/Pending newly accepted XM012 AP752 AP611 questions.json':
            'Manual verification/Pending newly accepted XM012 AP752 AP611 questions.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/Pending newly accepted XM013 questions.json':
            'XM Mixer/Pending newly accepted XM013 questions.json',
        'tmp/ald-text/xm/XM final coverage audit.json':
            'XM Mixer/XM final coverage audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/XM completed repository mirror receipt.json':
            'XM Mixer/XM completed repository mirror receipt.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/Pending newly accepted XM017 questions.json':
            'XM Mixer/Pending newly accepted XM017 questions.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/Pending newly accepted AP761 AP772 AP771 questions.json':
            'AP Parallel Adder/Pending newly accepted AP761 AP772 AP771 questions.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/AP accepted parity caption corrections audit.json':
            'AP Parallel Adder/AP accepted parity caption corrections audit.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/Pending newly accepted AP621 AP631 AP633 AP634 AP773 AP781 AP782 questions.json':
            'AP Parallel Adder/Pending newly accepted AP621 AP631 AP633 AP634 AP773 AP781 AP782 questions.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/Pending newly accepted RX001 RX002 RX051 RX081 questions.json':
            'RX ROS Address Register/Pending newly accepted RX001 RX002 RX051 RX081 questions.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/AP782 AP781 AQ4 reference recovery.json':
            'AP Parallel Adder/AP782 AP781 AQ4 reference recovery.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/RX101 coordinator mirror audit.json':
            'RX ROS Address Register/RX101 coordinator mirror audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/RX003 coordinator mirror audit.json':
            'RX ROS Address Register/RX003 coordinator mirror audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/RX091 coordinator source review audit.json':
            'RX ROS Address Register/RX091 superseded caption source review audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/RX091 comparative native diamond audit.json':
            'RX ROS Address Register/RX091 comparative native diamond audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/RX091 coordinator mirror audit.json':
            'RX ROS Address Register/RX091 coordinator mirror audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/RX completed repository mirror receipt.json':
            'RX ROS Address Register/RX completed repository mirror receipt.json',
        'tmp/ald-text/ald/repository-export/RX091 native diamond source review hold release.json':
            'RX ROS Address Register/RX091 native diamond source review hold release.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/Pending newly accepted AP783 AP791 AP792 questions.json':
            'AP Parallel Adder/Pending newly accepted AP783 AP791 AP792 questions.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/AP791 independent readable peer recoveries.json':
            'AP Parallel Adder/AP791 independent readable peer recoveries.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/Pending newly accepted AP637 AP639 questions.json':
            'AP Parallel Adder/Pending newly accepted AP637 AP639 questions.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/AP637 AP639 independent readable source recoveries.json':
            'AP Parallel Adder/AP637 AP639 independent readable source recoveries.json',
        'tmp/ald-text/ald/grid-verification/AP635 direct human approval verified.json':
            'AP Parallel Adder/AP635 direct human approval verified.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/AP635 coordinator mirror readiness audit.json':
            'AP Parallel Adder/AP635 coordinator mirror readiness audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/AP001 AP291 corrected current coordinator audit.json':
            'AP Parallel Adder/AP001 AP291 corrected current coordinator audit.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/Pending newly accepted AP793 questions.json':
            'AP Parallel Adder/Pending newly accepted AP793 questions.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/AP793 tentative physical-card cross-reference support.json':
            'AP Parallel Adder/AP793 tentative physical-card cross-reference support.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/AP793 AP801 AP811 AP813 coordinator mirror audit.json':
            'AP Parallel Adder/AP793 AP801 AP811 AP813 coordinator mirror audit.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/Pending newly accepted AP801 AP811 AP813 questions.json':
            'AP Parallel Adder/Pending newly accepted AP801 AP811 AP813 questions.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/AP801 AP811 AP813 independent recovery evidence.json':
            'AP Parallel Adder/AP801 AP811 AP813 independent recovery evidence.json',
        'tmp/ald-text/ald/repository-export/AP001 AP291 native literal source review findings.json':
            'AP Parallel Adder/AP001 AP291 native literal source review findings.json',
        'tmp/ald-text/ald/repository-export/AP001 native literal source review hold release.json':
            'AP Parallel Adder/AP001 native literal source review hold release.json',
        'tmp/ald-text/ald/repository-export/AP291 native literal source review hold release.json':
            'AP Parallel Adder/AP291 native literal source review hold release.json',
        'tmp/ald-text/ald/repository-export/AP001 literal correction release frozen audit.json':
            'AP Parallel Adder/AP001 literal correction release frozen audit.json',
        'tmp/ald-text/ald/repository-export/AP291 literal correction release frozen audit.json':
            'AP Parallel Adder/AP291 literal correction release frozen audit.json',
        'tmp/ald-text/ald/manual-verification/ap3-ap793-source-filename-correction/AP793 executed source filename correction receipt.json':
            'AP Parallel Adder/AP795 to AP793 source filename correction receipt.json',
        'tmp/ald-text/ald/manual-verification/ap3-ap793-source-filename-correction/AP793 prepared source filename correction.json':
            'AP Parallel Adder/AP795 to AP793 prepared source filename correction.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/AP795 AP793 independent source identity proof.json':
            'AP Parallel Adder/AP795 AP793 independent source identity proof.json',
        'tmp/ald-text/ald/wa_root/glyph_corner_correction/SE-DE glyph resolution receipt.json':
            'WA Cable Routing/SE-DE glyph resolution receipt.json',
        'tmp/ald-text/ald/wa_root/WA160_footer_recheck/final_public_review_WA160.json':
            'WA Cable Routing/WA160 corrected current native and preview review.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/Pending inventory after V3.json':
            'Manual verification/Pending inventory after V3.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/WA conditional pending questions.json':
            'WA Cable Routing/WA conditional pending questions.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/WA pending review notes.json':
            'WA Cable Routing/WA pending review notes.json',
        'tmp/ald-text/recovery-v2/rt/Published RT recovery receipt.json':
            'RT T Register/Published workbook recovery receipt.json',
        'tmp/ald-text/ald/manual-verification/source-derived-v3/Handoff preparation audit.json':
            'Manual verification/Workbook v3 handoff preparation audit.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/Pending newly accepted AP and XM questions.json':
            'Manual verification/Pending newly accepted AP and XM questions.json',
        'tmp/ald-text/ku/source-derived-review/Root reacceptance receipt.json':
            'KU MCW, Scan, Logout/Source-derived root reacceptance receipt.json',
        'tmp/ald-text/ald/repository-export/KU owner mirror reconciliation/Reconciliation receipt.json':
            'Manual verification/KU owner mirror reconciliation receipt.json',
        'tmp/ald-text/ald/repository-export/KU owner mirror reconciliation/KU review record reconciliation receipt.json':
            'KU MCW, Scan, Logout/KU review record reconciliation receipt.json',
        'tmp/ald-text/kt/recoveries-v2/Frozen recovery acceptance receipts.json':
            'KT Indicator Rollers and Scan Bus/Frozen workbook recovery acceptance receipts.json',
        'tmp/ald-text/kt/recoveries-v3/Frozen V3 recovery acceptance receipts.json':
            'KT Indicator Rollers and Scan Bus/Frozen workbook V3 recovery acceptance receipts.json',
        'tmp/ald-text/kt/recoveries-v2/KT201 independent native U correction proof.json':
            'KT Indicator Rollers and Scan Bus/KT201 independent native U correction proof.json',
        'tmp/ald-text/kt/root/KT verified printed references.json':
            'KT Indicator Rollers and Scan Bus/KT verified printed references.json',
        'ALD_Visual_Transcriptions/KT Indicator Rollers and Scan Bus/KT source-derived recoveries.txt':
            'KT Indicator Rollers and Scan Bus/KT source-derived recoveries.txt',
        'ALD_Visual_Transcriptions/KT Indicator Rollers and Scan Bus/KT source-derived recoveries.json':
            'KT Indicator Rollers and Scan Bus/KT source-derived recoveries.json',
        'ALD_Visual_Transcriptions/KT Indicator Rollers and Scan Bus/KT source-derived V3 recoveries.txt':
            'KT Indicator Rollers and Scan Bus/KT source-derived V3 recoveries.txt',
        'ALD_Visual_Transcriptions/KT Indicator Rollers and Scan Bus/KT source-derived V3 recoveries.json':
            'KT Indicator Rollers and Scan Bus/KT source-derived V3 recoveries.json',
        'tmp/ald-text/ald/manual-verification/source-derived-v2/Owner notification receipts.json':
            'Manual verification/Source-derived workbook v2 owner notification receipts.json',
        'tmp/ald-text/ald/manual-verification/source-derived-v2/Summary ledger.json':
            'Manual verification/Source-derived workbook v2 summary ledger.json',
        'tmp/ald-text/ald/manual-verification/source-derived-v2/Already applied source-derived records.json':
            'Manual verification/Previously illegible source-derived LS records.json',
        'tmp/ald-text/ald/manual-verification/cross-reference-review-2026-10-13/ap source filename correction executed audit.json':
            'AP Parallel Adder/AP745 title filename correction audit.json',
        'tmp/ald-text/rx/identity/RX912 to RX921 filename correction audit.json':
            'RX ROS Address Register/RX912 to RX921 filename correction audit.json',
        'tmp/ald-text/ald/ap3/AP2 to AP3 takeover handoff.json':
            'AP Parallel Adder/AP2 to AP3 takeover handoff.json',
        'tmp/ald-text/ald/ap3/AP2 stopped and AP3 sole ownership receipt.json':
            'AP Parallel Adder/AP2 stopped and AP3 sole ownership receipt.json',
        'tmp/ald-text/ald/manual-verification/ap3-source-filename-corrections/AP3 executed source filename corrections receipt.json':
            'AP Parallel Adder/AP751 AP752 source filename corrections receipt.json',
        'tmp/ald-text/ald/manual-verification/ap3-ap762-source-filename-correction/AP762 executed source filename correction receipt.json':
            'AP Parallel Adder/AP762 source filename correction receipt.json',
        'tmp/ald-text/ald/manual-verification/ap3-ap771-source-filename-correction/AP771 executed source filename correction receipt.json':
            'AP Parallel Adder/AP771 source filename correction receipt.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/WA160 focused native footer audit.json':
            'WA Cable Routing/WA160 focused native footer audit.json',
        'ALD_Visual_Transcriptions/ALD Diagrams/ZA column layout decisions.json':
            'ZA Programmed Grounds/ZA approved column layout decisions.json',
        'tmp/ald-text/ald/grid-verification/Printer grid specification.json':
            'Printer grid specification.json',
        'tmp/ald-text/ald/grid-verification/RT381 direct human approvals verified.json':
            'RT T Register/RT381 direct human approvals verified.json',
        'tmp/ald-text/ald/grid-verification/AP511 direct human approval verified.json':
            'AP Parallel Adder/AP511 direct human approval verified.json',
        'ALD_Visual_Transcriptions/KT Indicator Rollers and Scan Bus/KT unreadable print.txt':
            'KT Indicator Rollers and Scan Bus/KT unreadable print.txt',
        'ALD_Visual_Transcriptions/KT Indicator Rollers and Scan Bus/KT cross-page findings.txt':
            'KT Indicator Rollers and Scan Bus/KT cross-page findings.txt',
        'ALD_Visual_Transcriptions/KT Indicator Rollers and Scan Bus/KT package verification.json':
            'KT Indicator Rollers and Scan Bus/KT package verification.json',
        'ALD_Visual_Transcriptions/Allowed characters.json':
            'CAS allowed characters.json',
        'ALD_Visual_Transcriptions/ALD Diagrams/Allowed characters.json':
            'ALD allowed characters.json',
        'ALD_Visual_Transcriptions/CAS symbol reference.json':
            'CAS symbol reference.json',
        'ALD_Visual_Transcriptions/Character approval status.json':
            'Character approval status.json',
        'ALD_Visual_Transcriptions/ALD Diagrams/Confirmed filename corrections.json':
            'Confirmed filename corrections.json',
        'tmp/ald-text/ald/filename-corrections/A6611 catalogue correction audit.json':
            'A6 INDICES/A6611 catalogue correction audit.json',
        'tmp/ald-text/ald/filename-corrections/RB671 RB805 filename correction audit.json':
            'RB B Register/RB671 RB805 filename correction audit.json',
        'tmp/ald-text/ald/filename-corrections/RR181 filename correction audit.json':
            'RR R Register/RR181 filename correction audit.json',
        'tmp/ald-text/ald/filename-corrections/AP651 AP661 RT755 RT813 RT815 filename correction audit.json':
            'AP651 AP661 RT755 RT813 RT815 filename correction audit.json',
        'tmp/ald-text/ald/filename-corrections/KT594 to KT591 filename correction audit.json':
            'KT Indicator Rollers and Scan Bus/KT594 to KT591 filename correction audit.json',
        'tmp/ald-text/ald/filename-corrections/RT751 filename correction audit.json':
            'RT T Register/RT751 filename correction audit.json',
        'tmp/ald-text/ald/filename-corrections/RB807 filename correction audit.json':
            'RB B Register/RB807 filename correction audit.json',
        'tmp/ald-text/ald/filename-corrections/LS856 to LS861 filename correction audit.json':
            'LS LS Bus/LS856 to LS861 filename correction audit.json',
        'tmp/ald-text/ald/filename-corrections/XM903 to XM905 filename correction audit.json':
            'XM Mixer/XM903 to XM905 filename correction audit.json',
        'tmp/ald-text/ald/filename-corrections/XL031 printed title filename correction audit.json':
            'XL LM Register/XL031 printed title filename correction audit.json',
        'tmp/ald-text/ald/repository-export/LS023 prior export ownership recovery.json':
            'LS LS Bus/LS023 previous export ownership recovery.json',
        'tmp/ald-text/ald/repository-export/LS023 prior reviewed snapshot.json':
            'LS LS Bus/LS023 previous reviewed snapshot.json',
        'tmp/ald-text/ald/repository-export/Interrupted verified note ownership recovery receipt.json':
            'Manual verification/Interrupted note reconciliation receipt.json',
        'tmp/ald-text/ald/repository-export/Supplemental note descriptor recovery receipt.json':
            'Manual verification/Interrupted supplemental note tracking recovery receipt.json',
        'tmp/ald-text/ald/repository-export/Interrupted supplemental note history/AP physical copy check.txt':
            'AP Parallel Adder/summary history/AP physical copy check before interrupted export.txt',
        'tmp/ald-text/ald/repository-export/Interrupted supplemental note history/FX transcription notes.txt':
            'FX External Bus/summary history/FX transcription notes before interrupted export.txt',
        'tmp/ald-text/ald/repository-export/Interrupted supplemental note history/RT transcription notes.txt':
            'RT T Register/summary history/RT transcription notes before interrupted export.txt',
    }
    for relative, name in shared.items():
        path = workspace/relative
        if path.is_file():
            copy(path, repo/'notes'/name, 'Provenance or approved convention')
    caption_records = workspace/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/AP accepted parity caption immutable records'
    human_prefix_records = workspace/'tmp/ald-text/ald/manual-verification/human-c2a-prefix-correction'
    if human_prefix_records.is_dir():
        for path in sorted(human_prefix_records.rglob('*')):
            if path.is_file() and path.suffix.lower() in {'.json', '.txt', '.png'}:
                copy(path, repo/'notes/Manual verification/C2A human prefix correction'/path.relative_to(human_prefix_records),
                     'Human-confirmed endpoint correction, independent review, or preserved predecessor')
    wa_reference_proofs = workspace/'tmp/ald-text/ald/manual-verification/pending-inventory-after-v4'
    if wa_reference_proofs.is_dir():
        for path in sorted(wa_reference_proofs.glob('*.png')):
            copy(path, repo/'notes/A1 Socket Listing/WA140 WA150 reciprocal native proofs'/path.name,
                 'Native WA reciprocal endpoint and A1 physical socket evidence')
    literal_records = workspace/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/AP001 AP291 corrected current immutable records'
    if literal_records.is_dir():
        for path in sorted(literal_records.iterdir()):
            if path.is_file() and path.suffix.lower() in {'.json', '.txt', '.png'}:
                copy(path, repo/'notes/AP Parallel Adder/native literal correction history'/path.name,
                     'Frozen predecessor, exact correction, independent acceptance, or native source evidence')
    if caption_records.is_dir():
        for path in sorted(caption_records.glob('*.json')):
            copy(path, repo/'notes/AP Parallel Adder/accepted parity caption immutable records'/path.name,
                 'Frozen native caption acceptance and preserved predecessor receipt')
    rx091_history = workspace/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/RX091 superseded caption history'
    if rx091_history.is_dir():
        for path in sorted(rx091_history.iterdir()):
            if path.is_file():
                copy(path, repo/'notes/RX ROS Address Register/superseded caption history'/path.name,
                     'Superseded RX091 caption before exact native diamond correction')
    # Keep the immutable JSON receipt chains needed to interpret named audits
    # after the private working directories are no longer available.
    audit_root = workspace/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3'
    chain_map = {}
    selected_audit_pages = {(x['review_record'].replace('\\', '/'), x['page'])
                            for x in exported['exported']}
    selected_audit_pages.update((x['review_record'].replace('\\','/'),
                                Path(x['transcription_source']).name.split(' ',1)[0])
                               for x in exported['exported'])
    for relative in shared:
        audit_path = workspace/relative
        if audit_path.parent != audit_root or not audit_path.is_file():
            continue
        record = read_json(audit_path)
        if record.get('passed') is not True:
            continue
        for page in record.get('pages', []):
            # Single-page readiness reports may have a differently shaped
            # pages field; they are preserved records, not acceptance chains.
            if not isinstance(page, dict):
                continue
            if page.get('eligible') is not True:
                continue
            if (audit_path.relative_to(workspace).as_posix(), page.get('page')) not in selected_audit_pages:
                continue
            for key in ['root_acceptance', 'owner_receipt', 'legacy_ledger',
                        'independent_audit', 'independent_acceptance']:
                link = page.get(key)
                if not isinstance(link, dict) or not link.get('file'):
                    continue
                source = Path(link['file']).resolve()
                assert source.is_relative_to(workspace)
                raw = source.read_bytes()
                assert digest(raw) == link['sha256'], source
                destination = repo/'notes/Manual verification/immutable receipts'/(link['sha256'][:16]+' '+source.name)
                add(destination, raw, source, 'Immutable named independent acceptance chain')
                chain_map[str(source)] = {'repository_path': destination.relative_to(repo).as_posix(),
                                          'sha256': link['sha256']}
    add(repo/'notes/Manual verification/Immutable receipt locations.json',
        (json.dumps(chain_map, ensure_ascii=False, indent=2)+'\n').encode('utf-8'),
        audit_root, 'Portable mapping of original acceptance receipt paths')
    ku_reconciliation = workspace/'tmp/ald-text/ald/repository-export/KU owner mirror reconciliation/KU review record reconciliation receipt.json'
    if ku_reconciliation.is_file():
        for record in read_json(ku_reconciliation)['updates']:
            prior = Path(record['preserved_path'])
            assert prior.resolve().is_relative_to(workspace)
            assert digest(prior.read_bytes()) == record['current_owner_record_sha256']
            copy(prior, repo/'notes/KU MCW, Scan, Logout/metadata history'/prior.name,
                 'Preserved independently accepted owner review metadata before coordinator regeneration')
    # Question recoveries are proposals with independently readable evidence;
    # preserving them never edits or confers acceptance on a diagram quartet.
    for version in ['v2', 'v3']:
        recovery_root = workspace/'tmp/ald-text/ald/manual-verification'/('source-derived-'+version)
        for path in sorted(recovery_root.glob('*/Reviewed recoveries.json')):
            assert path.parent.name in folders, path
            copy(path, repo/'notes'/path.parent.name/('Source-derived workbook '+version+' recoveries.json'),
                 'Reviewed source-derived question recovery evidence; owner publication separate')
    add(repo/'notes/Reviewed export provenance.json', manifest_raw,
        audit/'last export manifest.json', 'Original reviewed export snapshot')

    # One lightweight review record per exported text, separate from its model.
    diagram_fields = {'nodes', 'nets', 'paths', 'wire_paths', 'wires',
                      'junctions', 'labels', 'text', 'cells', 'annotations',
                      'wire_shapes', 'connections', 'footer', 'records',
                      'sections', 'cards', 'connectors', 'geometry'}
    receipts = defaultdict(list)
    for entry in exported['exported']:
        text = Path(entry['transcription_source'])
        raw = (repo/Path(entry['destination']).relative_to(repo)).read_bytes()
        assert digest(raw) == entry['text_sha256'], str(text)
        folder = Path(entry['source_relative']).parent
        metadata = companion(text)
        document = read_json(metadata) if metadata else {}
        review = {key: value for key, value in document.items()
                  if key not in diagram_fields} if isinstance(document, dict) else {}
        record = {
            'text_file': Path(entry['destination']).relative_to(repo).as_posix(),
            'text_sha256': entry['text_sha256'],
            'reference_scan': entry['source_relative'],
            'original_scan_name': entry['original_scan_name'],
            'original_scan_timestamp': entry['scan_timestamp'],
            'source_scan_id': entry['source_scan_id'],
            'acceptance_record': entry['review_record'],
            'working_metadata_source': str(metadata) if metadata else None,
            'working_metadata_sha256': digest(metadata.read_bytes()) if metadata else None,
            'review_metadata_snapshot': review,
            'diagram_content_fields_kept_in_working_model':
                sorted(set(document) & diagram_fields) if isinstance(document, dict) else [],
            'scope': 'Review/provenance snapshot for the exported text; '
                     'diagram content models are imported separately.',
        }
        add(repo/'notes'/folder/(text.stem+' review record.json'),
            (json.dumps(record, ensure_ascii=False, indent=2)+'\n').encode('utf-8'),
            metadata or text, 'Page review and provenance')
        proof = workspace/entry['review_record']
        if proof.is_file():
            receipts[(str(proof), str(folder))].append(text.name.split(' ', 1)[0])

        # Keep exact human replies and before evidence for current accepted
        # physical-copy corrections. These page records are distinct from
        # diagram models and would otherwise be skipped by collection rules.
        page = text.name.split(' ', 1)[0]
        physical_candidates = [exports/'ALD Diagrams'/(page+' physical copy review.json'),
                               text.with_name(text.stem+' physical copy review.json')]
        for physical in dict.fromkeys(physical_candidates):
          if physical.is_file():
            confirmation = read_json(physical)
            confirmed_hash = confirmation.get('text_sha256') or confirmation.get('final_artifacts', {}).get('.txt', {}).get('sha256')
            if confirmed_hash == entry['text_sha256']:
                copy(physical, repo/'notes'/folder/physical.name,
                     'Current source-bound human physical-copy correction proof')
                before_artifacts = confirmation.get('before_source_and_quartet', {}).get('artifacts', []) + confirmation.get('before_artifacts', [])
                for item in before_artifacts:
                    prior = Path(item.get('snapshot_path', item.get('snapshot', '')))
                    assert prior.resolve().is_relative_to(workspace)
                    assert digest(prior.read_bytes()) == item['sha256'], str(prior)
                    copy(prior, repo/'notes'/folder/'physical-copy-history'/page/prior.name,
                         'Preserved before physical-copy artifact')
                readings = confirmation.get('original_readings_file', {})
                if readings.get('snapshot_path'):
                    prior = Path(readings['snapshot_path'])
                    assert prior.resolve().is_relative_to(workspace)
                    assert digest(prior.read_bytes()) == readings['sha256'], str(prior)
                    copy(prior, repo/'notes'/folder/'physical-copy-history'/'Original human readings.json',
                         'Preserved exact original human readings')

    for (source, folder), pages in receipts.items():
        path = Path(source)
        if len(pages) == 1:
            name = pages[0]+' acceptance receipt.json'
        else:
            name = path.name
            if not name.startswith(pages[0][:2]):
                name = pages[0][:2]+' '+name
        # Named coordinator audits are already preserved once in shared
        # provenance. Keep distinct same-named owner ledgers as separate
        # records rather than allowing either one to overwrite the other.
        shared_name = shared.get(path.relative_to(workspace).as_posix())
        if shared_name:
            destination = repo/'notes'/shared_name
        else:
            destination = repo/'notes'/folder/name
            relative = destination.relative_to(repo).as_posix()
            if relative in planned and planned[relative]['sha256'] != digest(path.read_bytes()):
                destination = repo/'notes'/folder/'acceptance receipts'/path.relative_to(workspace/'tmp/ald-text')
        copy(path, destination, 'Original acceptance receipt or ledger')

    # Preserve the exact human answer and predecessor evidence for AP001's
    # independently accepted one-cell board/socket correction.
    human_ap = workspace/'tmp/ald-text/ald/ap3/root/human-confirmed/AP001-22f1584ecc'
    human_ap_receipt = human_ap/'Human correction publication receipt.json'
    if human_ap_receipt.is_file():
        accepted = read_json(human_ap_receipt)
        ap_entry = next(e for e in exported['exported'] if e['page']=='AP001')
        assert accepted['passed'] and accepted['human_answer']=='B-E1K6'
        # Subsequent independently reviewed human fields may supersede the
        # current AP001 quartet. Preserve this exact first correction as
        # history, bound to its immutable private candidate bytes.
        human_manifest = read_json(human_ap/'Private correction manifest.json')
        next_human_receipt = read_json(workspace/'tmp/ald-text/ald/ap3/root/human-batch-v4-5796f6dd2e40/Bounded human batch publication receipt.json')
        assert next_human_receipt['passed'] is True
        for kind, artifact in accepted['current_quartet'].items():
            # Publication adds review annotations to the JSON and notes;
            # the next batch preserves those exact published predecessor
            # bytes rather than the earlier unannotated private candidates.
            preserved = next_human_receipt['pages']['AP001']['before_quartet'][kind]
            assert preserved['sha256']==artifact['sha256']
            assert digest(Path(preserved['path']).read_bytes())==artifact['sha256']
            source = Path(preserved['path'])
            copy(source,repo/'notes/AP Parallel Adder/Human confirmed AP001 socket/Published prior socket quartet'/source.name,
                 'Exact first human-confirmed socket publication before later human corrections')
        assert digest(Path(accepted['source']['path']).read_bytes())==accepted['source']['sha256']
        for source in sorted(human_ap.rglob('*')):
            if source.is_file() and source.suffix.lower() in {'.json','.txt','.png'}:
                copy(source, repo/'notes/AP Parallel Adder/Human confirmed AP001 socket'/source.relative_to(human_ap),
                     'Exact human socket answer, independent acceptance and preserved before/candidate artifacts')

    # Keep current field applications with their preserved full-source
    # predecessors and independently checked deltas. Never copy private
    # candidates until the matching guarded publication receipt exists.
    application_root = workspace/'tmp/ald-text/ald/manual-verification/resolved-text-application-v1/non-ap'
    for subdir, receipt_name in [('', 'First ten non-AP publication receipt.json'),
                                ('older-firm','Remaining firm canonical publication receipt.json')]:
        batch_root = application_root/subdir
        receipt_path = batch_root/receipt_name
        if not receipt_path.is_file():
            continue
        batch = read_json(receipt_path)
        assert batch['passed'] is True
        for item in batch['pages']:
            folder = Path(item['source']['path']).parent.name
            page_root = batch_root/item['page']
            for source in sorted(page_root.rglob('*')):
                if source.is_file() and source.suffix.lower() in {'.json','.txt','.png','.csv'}:
                    copy(source,repo/'notes'/folder/'Confirmed field correction history'/item['page']/source.relative_to(page_root),
                         'Preserved source acceptance, exact field proof and independently reviewed candidate history')
        for source in sorted(batch_root.glob('*')):
            if source.is_file() and source.suffix.lower() in {'.json','.txt','.png'}:
                copy(source,repo/'notes/Manual verification/Applied confirmed fields'/subdir/source.name,
                     'Guarded field application batch receipt or independent delta review')
    # Function-only human corrections reuse prior full-page native acceptance
    # and keep their exact independently inspected deltas as separate history.
    for subdir,receipt_name,label in [
        ('non-ap-OR-correction','Non-AP OR function canonical publication receipt.json','OR'),
        ('non-ap-supplemental-function-correction','Non-AP supplemental function canonical publication receipt.json','Supplemental')]:
        function_batch = workspace/'tmp/ald-text/ald/card-type-database'/subdir
        function_receipt = function_batch/receipt_name
        if not function_receipt.is_file():
            continue
        batch = read_json(function_receipt)
        assert batch['passed'] is True
        for page in batch['pages']:
            folder = Path(page['source']['path']).parent.name
            page_root = Path(page['independently_reviewed_candidate_quartet']['txt']['path']).parent.parent
            file_page = Path(page['current_quartet']['txt']['path']).name.split(' ',1)[0]
            assert page_root.resolve().is_relative_to(function_batch.resolve())
            assert page_root.is_dir()
            for source in sorted(page_root.rglob('*')):
                if source.is_file() and source.suffix.lower() in {'.json','.txt','.png'}:
                    copy(source,repo/'notes'/folder/'Human function correction history'/label/file_page/source.relative_to(page_root),
                         'Exact human function correction, independently reviewed delta and preserved source acceptance')
        for source in sorted(function_batch.glob('*')):
            if source.is_file() and source.suffix.lower() in {'.json','.txt','.png'}:
                copy(source,repo/'notes/Card types/Function correction history'/label/source.name,
                     'Human function correction batch publication or independent acceptance')
    for suffix in ['human-batch-v4-5796f6dd2e40','socket-high-followup-v1','definite-header-followup-v2','card-type-human-followup-v1','or-function-human-followup-v1','additional-function-human-followup-v1']:
        batch_root = workspace/'tmp/ald-text/ald/ap3/root'/suffix
        receipt_name = ('Bounded human batch publication receipt.json' if suffix.startswith('human')
                        else 'Definite header publication receipt.json' if suffix.startswith('definite')
                        else 'Card type human AP211 publication receipt.json' if suffix.startswith('card-type')
                        else 'OR function human publication receipt.json' if suffix.startswith('or-function')
                        else 'Additional function human publication receipt.json' if suffix.startswith('additional-function')
                        else 'Socket High followup publication receipt.json')
        receipt_path = batch_root/receipt_name
        if not receipt_path.exists() and suffix.startswith(('card-type','or-function','additional-function')):
            continue
        receipt = read_json(receipt_path)
        assert receipt['passed'] is True
        for page, item in receipt['pages'].items():
            for kind, artifact in item['before_quartet'].items():
                source = Path(artifact['path'])
                assert digest(source.read_bytes())==artifact['sha256']
                copy(source,repo/'notes/AP Parallel Adder/Confirmed field correction history'/suffix/page/'before accepted'/source.name,
                     'Exact published predecessor quartet before independently reviewed field corrections')
            frozen = item['frozen_independent_review']
            source = Path(frozen['path'])
            assert digest(source.read_bytes())==frozen['sha256']
            copy(source,repo/'notes/AP Parallel Adder/Confirmed field correction history'/suffix/page/'Frozen independent acceptance.json',
                 'Independent exact field-delta acceptance preserved before owner publication annotations')
        for source in sorted(batch_root.rglob('*')):
            if source.is_file() and source.suffix.lower() in {'.json','.txt','.png'}:
                copy(source,repo/'notes/AP Parallel Adder/Confirmed field correction history'/suffix/source.relative_to(batch_root),
                     'Exact human replies or independently reviewed source recoveries and superseded artifact history')
    v5_audit = read_json(workspace/'tmp/ald-text/ald/manual-verification/spreadsheet-v5/Workbook independent audit v5.json')
    assert v5_audit['passed'] is True and not v5_audit['failures']
    for key in ['workbook','manifest']:
        artifact = v5_audit[key]
        assert digest(Path(artifact['path']).read_bytes())==artifact['sha256']

    # Reviewed question deductions remain distinct from diagram publications.
    # Import them only after exact candidate/tool bindings and independent
    # native judgments have passed; the issued workbook remains unchanged.
    socket_work = workspace/'tmp/ald-text/ald/manual-verification/socket-function-recovery-v1'
    socket_audit = socket_work/'Independent final socket function audit.json'
    if socket_audit.is_file():
        review = read_json(socket_audit)
        assert review['passed'] is True and not review['failures']
        for key in ['candidate_file', 'builder_file', 'native_verdict_file']:
            item = review.get(key)
            if item:
                assert digest(Path(item['path']).read_bytes())==item['sha256'], key
        dataset = read_json(Path(review['candidate_file']['path']))
        assert {q['id'] for q in dataset['results'] if q['confidence']=='High'}==set(review['High_ids'])
        assert {q['id'] for q in dataset['results'] if q['confidence']=='Human confirmed'}==set(review['human_confirmed_ids'])
        for source in sorted(socket_work.rglob('*')):
            if not source.is_file() or '__pycache__' in source.parts:
                continue
            if source.name=='build_socket_function_recoveries.py':
                copy(source, repo/'tools/references'/source.name, 'Reusable physical socket, card-function and same-page candidate matching tool')
            elif source.suffix.lower() in {'.json','.txt','.png','.csv'}:
                copy(source, repo/'notes/Manual verification/Socket function reference checks'/source.relative_to(socket_work),
                     'Socket/function question deductions, independent native evidence and frozen inputs')

    # Collection-level reviews and inventories, rather than diagram data tables.
    selectors = ['review', 'validation', 'inventory', 'manifest', 'rename ledger',
                 'filename correction', 'acceptance ledger', 'printer grid',
                 'branch confirmation', 'unreadable', 'reconciliation',
                 'recovered fields', 'source corrections', 'comparison', 'checks']
    for path in sorted(exports.rglob('*')):
        if path.suffix.lower() not in {'.json', '.csv'} or not path.is_file():
            continue
        name = path.name.lower()
        if not any(word in name for word in selectors):
            continue
        # Page companions are represented by the filtered records above.
        token = path.name.split(' ', 1)[0]
        if path.suffix.lower()=='.json' and len(token) >= 5 and token[2:5].isdigit():
            continue
        parent = path.parent.name
        if parent in folders:
            folder = parent
        elif parent[:2] in by_family and parent not in {'ALD Diagrams', 'CAS Diagrams'}:
            folder = by_family[parent[:2]]
        elif path.name.startswith(('CAS ', 'A6 A7 A8 ')):
            folder = None
        elif path.name[:2] in by_family:
            folder = by_family[path.name[:2]]
        else:
            folder = None
        dest = repo/'notes'
        if folder:
            dest /= folder
        destination = dest/path.name
        if destination.relative_to(repo).as_posix() not in planned:
            copy(path, destination, 'Published collection review or inventory snapshot')

    # Preserve shared engines/checkers and their local Python dependencies;
    # exclude page-specific repair scripts and early OCR experiments.
    seed_names = [
        'a1_build_reference.py', 'a1_verify_complete.py', 'a678_canvas.py',
        'cas_reviewed_renderer.py', 'cas_characters.py', 'cas_local_grid.py',
        'cas_content_audit.py', 'cas_wire_qz_check.py', 'cas_export_package.py',
        'qq_renderer.py', 'qy_renderer.py', 'qz_package.py',
        'qz_reconcile.py', 'qz_reconciliation_report.py', 'compare_qz_emulator.py',
        'ce_grid_check.py', 'kc_grid_check.py', 'kx_grid_check.py', 'ra_grid_check.py',
        'ald/ap_batch_main/ald_page.py', 'ald/ap_batch_main/exact_grid_check.py',
        'ald/ap_batch_mid/core.py', 'ald/ap_batch_high/render_page.py',
        'ald/repository-export/export_reviewed.py',
    ]
    work = workspace/'tmp/ald-text'
    queue = [work/name for name in seed_names]
    tools = set()
    while queue:
        path = queue.pop()
        if path in tools or not path.is_file():
            continue
        tools.add(path)
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module.split('.')[0])
        for module in modules:
            for candidate in [path.parent/(module+'.py'), work/(module+'.py')]:
                if candidate.is_file():
                    queue.append(candidate)
                    break
    for path in sorted(tools):
        copy(path, repo/'tools/legacy'/path.relative_to(work),
             'Historical shared conversion/validation source; original workspace dependencies')
    copy(work/'cas_characters.py', repo/'tools/cas/cas_characters.py',
         'Reusable CAS glyph normalization helper')

    # Never silently replace a user's independently edited repository record.
    index_path = repo/'notes/Repository records manifest.json'
    old = read_json(index_path) if index_path.exists() else {}
    owned = {item['path']: item['sha256'] for item in old.get('files', [])}
    conflicts = []
    for relative, item in planned.items():
        path = repo/relative
        if path.exists() and digest(path.read_bytes()) not in {item['sha256'], owned.get(relative)}:
            conflicts.append(relative)
    assert not conflicts, 'Independent repository changes: '+str(conflicts)
    report = {'updated_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'Reviewed text export plus preserved provenance and tool snapshots',
              'reviewed_texts': len(exported['exported']),
              'historical_shared_tools': len(tools),
              'files': [{key: value for key, value in item.items() if key != '_raw'}
                        for item in planned.values()]}
    if args.write:
        for relative, item in planned.items():
            path = repo/relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists() or digest(path.read_bytes()) != item['sha256']:
                path.write_bytes(item['_raw'])
        # Include the published text/notes in the portable integrity inventory.
        managed = {item['path'] for item in report['files']}
        for branch in ['ALD', 'notes', 'json', 'csv', 'tools']:
            for path in (repo/branch).rglob('*'):
                if not path.is_file() or path==index_path or path.suffix.lower() not in {'.txt','.json','.csv','.py','.png'}:
                    continue
                relative = path.relative_to(repo).as_posix()
                if relative not in managed:
                    report['files'].append({'path': relative,
                        'sha256': digest(path.read_bytes()), 'role': 'Repository file'})
        index_path.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'planned_records_and_tools': len(planned),
                      'historical_shared_tools': len(tools),
                      'counts': dict(Counter(item['role'] for item in planned.values())),
                      'write': args.write}, ensure_ascii=False))


if __name__ == '__main__':
    main()
