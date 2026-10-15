# SY22-2798-2: source-bound ALD notation review

Source: `D:/Reference Materials/IBM 360/SY22-2798-2_LogicBlocks_AutomatedLogicDiagrams_SLT,SLD,ASLT,MST_TO_Oct71.pdf`, SHA-256 `e3214d20d24a698beb464766df8acabcee20c5f4ea298c3e4b95407a455f84f7`, sixth edition (October 1971), 86 PDF pages. The file is image-only; claims below were checked against rendered page images in this directory. PDF page numbers are one-based; printed section page numbers are also supplied.

## Scope

PDF p. 2 (Preface) says the manual covers SLT, SLD, ASLT, and MST. PDF p. 21 / printed 2-1 says Chapter 2's block descriptions apply to all ALD forms and concern *logical function*, not circuit schematics. PDF p. 41 / printed 3-1 says ALDs use the same logic symbols and page formats across technologies, then describes the SLT design automation program and the engineering ALD. Thus the notation is relevant to the IBM 360 SLT sheets, while examples of packaging or timing for other families should not be transferred automatically.

## Function and suffix

- PDF p. 46 / printed 3-7, **Information Inside the Block, Line 1**: line 1 starts with the logical function, e.g. `A`, `OR`, `N`, `FF`. A function followed by a space and suffix carries *additional information* about that function. Listed DOT examples include `A OR`, `OR A`, `N OR`, and `OR WL`. The first function remains the primary function, as the user previously directed.
- PDF p. 27 / printed 2-7, **DOT OR and DOT AND**, Figure 2-30: outputs of basic blocks may be connected externally to make DOT OR or DOT AND. A suffix `A` or `OR` is placed to the right of the primary function to identify this participation. `WL` means the output participates in both forms of wired logic. The figure depicts `OR A`, `A A`, `N A`, and `OR WL`; the separate junction pseudo-blocks are `A DOT` and `OR DOT`. Therefore `A OR` is not a second on-card OR gate by itself.
- PDF p. 26 / printed 2-6, **Multiple Block Configurations**: `FL`, `FF`, and `PH` are suffixed onto blocks participating in flip-latch, flip-flop, and polarity-hold arrangements, respectively. Again, the suffix describes a multiblock role.
- PDF p. 46 / printed 3-7: a leading asterisk before the function indicates the input positions are fixed by physical card makeup. A trailing asterisk at position 6 marks a special block. PDF p. 48 / printed 3-9 separately defines an asterisk *on an input or output wire* as a connection leaving the board. These are different uses of the same printed glyph and should be separate structured attributes.
- PDF p. 22 / printed 2-2: `N` is the inverter function, with either input or output polarity marking as shown in Figure 2-8. The page also shows four `AR` polarity variants in Figure 2-9. A side `N` on an `AR` block denotes the negative pulse/shift variant, not a second primary function.

## Shape, polarity and identity

- PDF p. 21 / printed 2-1, Figures 2-2 through 2-6, expressly draws the same positive-AND or positive-OR behavior using an `A` block or an `OR` block with changed polarity indicators. A bare input/output count is therefore insufficient to infer that one of two function labels is a misreading.
- PDF p. 48 / printed 3-9, **Wedges**: a wedge at the point a line joins a block identifies the line's least-positive (active) potential. It applies at inputs or outputs. Treat it as an explicitly printed polarity indicator; do not mechanically translate every wedge into an independent gate inversion. PDF p. 49 / printed 3-10 separately defines `P`/`N` in the side for capacitive shift, `X` for a nonlogic feedthrough/voltage line, and `K` for certain nonlogic tied outputs.
- PDF p. 47 / printed 3-8, **Line 4**: the first four positions are card code; the last two characters are *portion* and *subportion*. Blocks internally interconnected on the card share a portion; each block within that portion has its own subportion character. For example, `4633K4` and `4633K8` are two different subportions of the same `4633K` portion, supporting the user's correction to the sparse-shape review. Keep their observations distinct.
- PDF p. 47 / printed 3-8, Figure 3-7: circuit number classification `T` denotes SLT/SLD 30 ns and `U` denotes SLT/SLD 5–12 ns. This `T` is part of the circuit-number classification on line 3; it does not define a suffix such as `R T0` in the line-1 function. Do not conflate the two. The chapter pages reviewed did not establish what `T0`–`T3` mean after `R`.

## Card-type database implications

Preserve the literal line-1 text, then parse separately: primary function; additional suffix tokens; leading fixed-input asterisk; trailing special-block asterisk; per-pin/line polarity wedges; side annotations; and full four-digit card code, portion, and subportion. Shape comparison should include polarity, electrical role, and subportion, and should treat a discordant primary name as a *review prompt* rather than an automatic correction. The manual supports the user's judgment that many of the sparse-shape cases are legitimate variants. It does not decide the remaining literal readings of the 17 source crops; those require the original sheet and card context.

No canonical ALD text, repository file, or card database was changed by this review.
