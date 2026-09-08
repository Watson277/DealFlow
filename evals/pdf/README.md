# PDF extraction evaluation

This directory contains page-aligned reference text for PDF extraction evaluation.

The `report-native-147` dataset is built from `report.pdf` with an extractor that is
independent of the application's PyMuPDF pipeline. The source PDF has a broken TeX
font-to-Unicode map for numbers, Latin text, and punctuation, so the builder repairs
the affected CMR10/CMR12 text with the TeX OT1 character map.

Run the builder:

```powershell
python evals/pdf/build_native_ground_truth.py `
  --pdf "E:\study2\贵州\report.pdf" `
  --output "evals\pdf\ground_truth\report-native-147" `
  --expected-pages 147 `
  --verified-blank-pages 90 112 132 144 `
  --spot-checked-pages 1 2 5 20 50 51 90 112 132 140 144 147
```

Dataset files:

- `ground-truth.jsonl`: canonical page-aligned records used by evaluators.
- `ground-truth.txt`: plain-text pages separated by explicit page markers.
- `ground-truth.md`: human-readable review copy.
- `review.csv`: page review queue and structural warning flags.
- `manifest.json`: source checksum, scope, normalization, and quality status.

CER comparison must use each JSONL record's `text` field after Unicode NFKC
normalization and removal of all Unicode whitespace. Running headers, page numbers,
and text that exists only inside raster figures are outside this dataset's scope.

The initial output is a silver ground truth. Pages flagged in `review.csv`, especially
those containing formulas, must be checked against rendered pages before promoting the
dataset version from `silver` to `gold`.
