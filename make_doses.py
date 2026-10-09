import pathlib
s = pathlib.Path("efficiency-layer.md").read_text()
base = s[: s.index("## 6. 10x review")].rstrip() + "\n"
d = pathlib.Path("layers"); d.mkdir(exist_ok=True)
(d / "tenx-0.md").write_text(base)
(d / "tenx-1-light.md").write_text(base + """
## 6. 10x review (light)
- Once, after the first version that passes the tests, in at most 50 words: "How could this be done 10x better or cheaper?" Adopt only if switching costs less than keeping the current version.
""")
(d / "tenx-2-default.md").write_text(s)
(d / "tenx-3-heavy.md").write_text(base + """
## 6. 10x review (heavy)
- Before the first edit, after the first passing version, and after every 10 tool calls: in up to 600 words, answer "How could this be done 10x better or 10x cheaper, not 10% better?" List up to 5 ideas and evaluate each.
- Adopt an idea only if switching costs less than finishing the current approach.
""")
print("dose layers written")
