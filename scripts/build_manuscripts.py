"""Compile both manuscripts with XeLaTeX/BibTeX and retain public PDFs."""
from pathlib import Path
import shutil
import subprocess

def main():
    root=Path(__file__).resolve().parents[1]
    folder=root/"manuscripts"
    build=folder/"build"
    build.mkdir(exist_ok=True)
    # latexmk runs BibTeX inside the build directory. Copy its explicit input.
    shutil.copyfile(folder/"references_verified.bib",build/"references_verified.bib")
    for lang in ("en","zh"):
        stem="failure_attribution_"+lang
        proc=subprocess.run(["latexmk","-g","-xelatex","-interaction=nonstopmode",
                             "-halt-on-error","-outdir=build",stem+".tex"],cwd=folder,
                            stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (build/(stem+"_command.log")).write_bytes(proc.stdout)
        if proc.returncode: raise SystemExit(f"Compilation failed; inspect manuscripts/build/{stem}_command.log")
        log=(build/(stem+".log")).read_text(encoding="utf-8",errors="replace")
        if "undefined" in log or "Missing character:" in log:
            raise SystemExit("Unresolved references or missing glyphs in "+stem)
        shutil.copyfile(build/(stem+".pdf"),folder/(stem+".pdf"))
        print(stem+".pdf compiled")

if __name__=="__main__": main()
