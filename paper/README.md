# paper/ — P4 technical report

The LaTeX source of the technical report on P0–P3. Plan and rules: [`docs/p4-plan.md`](../docs/p4-plan.md).

## Licence

The text and figures in this folder are licensed under the
[Creative Commons Attribution 4.0 International licence (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/).
The code elsewhere in this repository remains under the Apache License 2.0.

## Building

```bash
python tools/p4_numbers.py          # writes paper/numbers.tex from committed results (P4.1)
tectonic paper/main.tex             # Tectonic 0.17.0; the first build downloads its TeX bundle
```

Every number in the report is a macro from `numbers.tex`, and a test checks that each one still matches its source file.
Figures are made by scripts only.
