#!/usr/bin/env python3
# Licença: GNU AGPL-3.0, a mesma do RustDesk. © EDX Tecnologia em Informação Ltda.
"""Gera .github/workflows/edx-build.yml a partir do workflow oficial do upstream.

Por que gerar em vez de escrever à mão: o build do upstream (Flutter com engine
customizada, vcpkg fixado, patches de Flutter, drivers) é complexo e muda a cada
versão. Copiamos os jobs dele sem reinventar nada e só acrescentamos:

  1. passo "Apply EDX branding" logo após cada checkout;
  2. nome do .app do macOS vindo do brand.json;
  3. apenas os jobs Windows x64/arm64, macOS e Linux (deb + AppImage).

Rode de novo sempre que sincronizar com uma nova versão do upstream:

    python3 edx/scripts/make_workflow.py
"""
import re
import sys
from pathlib import Path

# Console do Windows (cp1252) não tem ✔/✘; sem isso o print derruba o script.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / ".github/workflows/flutter-build.yml"
DST = ROOT / ".github/workflows/edx-build.yml"

KEEP = [
    "generate-bridge",
    "build-RustDeskTempTopMostWindow",
    "build-for-windows-flutter",
    "build-for-macOS",
    "build-rustdesk-linux",
    "build-appimage",
]

BRANDING_STEP = """\
{ind}- name: Apply EDX branding
{ind}  shell: bash
{ind}  env:
{ind}    EDX_RS_PUB_KEY: ${{{{ vars.EDX_RS_PUB_KEY }}}}
{ind}  run: |
{ind}    python3 edx/scripts/rebrand.py --flavor "${{{{ inputs.flavor }}}}"
{ind}    echo "EDX_APP=$(python3 -c "import json;b=json.load(open('edx/brand.json',encoding='utf-8'));print(b['flavors']['${{{{ inputs.flavor }}}}']['app_name'])")" >> "$GITHUB_ENV"

"""


def split_jobs(text):
    head, sep, body = text.partition("\njobs:\n")
    if not sep:
        sys.exit("formato inesperado: bloco 'jobs:' não encontrado")
    jobs, order, cur = {}, [], None
    for line in body.splitlines(keepends=True):
        m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if m:
            cur = m.group(1)
            order.append(cur)
            jobs[cur] = []
        if cur:
            jobs[cur].append(line)
    return head, order, {k: "".join(v) for k, v in jobs.items()}


def add_branding(job_text):
    lines = job_text.splitlines(keepends=True)
    out, i, n = [], 0, 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        m = re.match(r"^(\s*)- name: Checkout source code\s*$", line)
        if m:
            ind = m.group(1)
            i += 1
            # copia o restante do passo de checkout
            while i < len(lines) and not re.match(rf"^{re.escape(ind)}- ", lines[i]) \
                    and (lines[i].startswith(ind + " ") or not lines[i].strip()):
                out.append(lines[i])
                i += 1
            if out and out[-1].strip():
                out.append("\n")
            out.append(BRANDING_STEP.format(ind=ind))
            n += 1
            continue
        i += 1
    return "".join(out), n


def main():
    text = SRC.read_text(encoding="utf-8")
    head, order, jobs = split_jobs(text)
    missing = [j for j in KEEP if j not in jobs]
    if missing:
        sys.exit(f"jobs não encontrados no upstream: {missing}")

    head = re.sub(r"(?m)^name: .*$", "name: EDX build (gerado de flutter-build.yml)", head, count=1)
    head = head.replace(
        "    inputs:\n",
        "    inputs:\n"
        "      flavor:\n"
        "        type: string\n"
        "        default: \"suporte\"\n", 1)
    head = ("# ARQUIVO GERADO por edx/scripts/make_workflow.py a partir do workflow do\n"
            "# upstream. Não edite à mão: regenere após cada sincronização.\n") + head

    out_jobs, total = [], 0
    for name in order:
        if name not in KEEP:
            continue
        body = jobs[name]
        needs = re.findall(r"needs:\s*\[([^\]]*)\]", body)
        for group in needs:
            for dep in [d.strip() for d in group.split(",") if d.strip()]:
                if dep not in KEEP:
                    sys.exit(f"{name} depende de {dep}, que não está em KEEP")
        if name == "build-for-macOS":
            body = body.replace("RustDesk.app", "${{ env.EDX_APP }}.app")
        body, n = add_branding(body)
        total += n
        out_jobs.append(body)

    if total < 4:
        sys.exit(f"só {total} checkouts receberam o passo de marca; revise o upstream")

    DST.write_text(head + "\njobs:\n" + "".join(out_jobs), encoding="utf-8")
    print(f"gerado {DST.relative_to(ROOT)}: {len(out_jobs)} jobs, passo de marca em {total} checkouts")


if __name__ == "__main__":
    main()
