#!/usr/bin/env python3
# Licença: GNU AGPL-3.0, a mesma do RustDesk. © EDX Tecnologia em Informação Ltda.
"""Aplica a identidade EDX sobre o código-fonte upstream do RustDesk.

Roda na raiz do repositório (o fork), antes do build:

    python3 edx/scripts/rebrand.py --flavor suporte      # app do cliente
    python3 edx/scripts/rebrand.py --flavor tecnico      # app dos técnicos
    python3 edx/scripts/rebrand.py --check               # só verifica âncoras
    python3 edx/scripts/rebrand.py --reset --flavor tecnico   # troca de flavor local

Princípios:
  * O código upstream fica intocado no git; a marca é aplicada no momento do
    build (local ou CI). Isso inclui o submódulo libs/hbb_common.
  * Cada alteração tem uma âncora exata. Se o upstream mudar e a âncora sumir,
    o script PARA com erro em vez de gerar um binário meio-rebrandeado.
  * Idempotente: rodar duas vezes não duplica nada.
  * Avisos de copyright do upstream são preservados (exigência da AGPL-3.0,
    seção 5). Somente a MARCA "RustDesk" sai da interface.

Somente biblioteca padrão do Python 3.8+ (e git, para --reset).
"""
import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

# Console do Windows (cp1252) não tem ✔/✘; sem isso o print derruba o script.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

EDX = Path(__file__).resolve().parents[1]
ROOT = EDX.parent
GEN = EDX / "assets" / "generated"
KEY_PLACEHOLDER = "COLE_AQUI"


class Anchor(Exception):
    pass


class Patcher:
    def __init__(self, check_only=False):
        self.check_only = check_only
        self.changed = []
        self.skipped = []
        self.errors = []

    def _read(self, rel):
        p = ROOT / rel
        if not p.is_file():
            raise Anchor(f"arquivo não encontrado: {rel}")
        # newline="" preserva CRLF (checkout no Windows com core.autocrlf)
        with open(p, encoding="utf-8", newline="") as fh:
            return p, fh.read()

    def _write(self, p, text):
        if not self.check_only:
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)

    def literal(self, rel, old, new, count=1, label=None):
        """Troca texto exato. count=None aceita qualquer quantidade >= 1."""
        label = label or old.strip().splitlines()[0][:60]
        try:
            p, s = self._read(rel)
            if "\r\n" in s:
                old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
            if new and new in s:
                # já aplicado (vale também quando 'new' contém 'old')
                self.skipped.append((rel, label))
                return
            n = s.count(old)
            if n == 0:
                raise Anchor(f"âncora não encontrada em {rel}: {label!r}")
            if count is not None and n != count:
                raise Anchor(f"esperava {count} ocorrência(s) em {rel}, achei {n}: {label!r}")
            self._write(p, s.replace(old, new))
            self.changed.append((rel, label, n))
        except Anchor as e:
            self.errors.append(str(e))

    def regex(self, rel, pattern, repl, min_count=1, max_count=None, label=None, flags=0,
              done_marker=None):
        label = label or pattern[:60]
        try:
            p, s = self._read(rel)
            new_s, n = re.subn(pattern, repl, s, flags=flags)
            if n == 0:
                if done_marker and done_marker in s:
                    self.skipped.append((rel, label))
                    return
                if min_count == 0:
                    return
                raise Anchor(f"padrão não encontrado em {rel}: {label!r}")
            if n < min_count or (max_count is not None and n > max_count):
                raise Anchor(f"{rel}: {n} ocorrência(s) fora do esperado para {label!r}")
            if new_s != s:
                self._write(p, new_s)
                self.changed.append((rel, label, n))
            else:
                self.skipped.append((rel, label))
        except Anchor as e:
            self.errors.append(str(e))

    def regex_tree(self, base, glob, pattern, repl, label):
        total = 0
        for p in sorted((ROOT / base).rglob(glob)):
            with open(p, encoding="utf-8", newline="") as fh:
                s = fh.read()
            new_s, n = re.subn(pattern, repl, s)
            if n:
                self._write(p, new_s)
                total += n
        if total:
            self.changed.append((f"{base}/**/{glob}", label, total))

    def copy(self, src_name, dest_rel):
        src = GEN / src_name
        if not src.is_file():
            self.errors.append(f"ícone não gerado: {src_name} (rode gen_icons.py)")
            return
        dest = ROOT / dest_rel
        if not dest.parent.is_dir():
            self.errors.append(f"destino inexistente: {dest_rel}")
            return
        if not self.check_only:
            shutil.copyfile(src, dest)
        self.changed.append((dest_rel, f"ícone ← {src_name}", 1))

    def write_new(self, rel, text):
        if not self.check_only:
            (ROOT / rel).write_text(text, encoding="utf-8")
        self.changed.append((rel, "arquivo gerado", 1))


def rust_str(s):
    return json.dumps(s, ensure_ascii=False)


def dart_str(s):
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'").replace("$", "\\$") + "'"


def gen_branding_rs(brand, flavor_name, flavor):
    lines = [
        "// EDX Tecnologia: parâmetros de marca aplicados em tempo de execução.",
        "// Gerado por edx/scripts/rebrand.py. Não editar à mão; altere edx/brand.json.",
        "//",
        "// Este arquivo é uma modificação do RustDesk (AGPL-3.0). Ver EDX-NOTICE.md.",
        "#![allow(dead_code)]",
        "use hbb_common::config;",
        "",
        f"pub const FLAVOR: &str = {rust_str(flavor_name)};",
        f"pub const SOURCE_URL: &str = {rust_str(brand['urls']['source'])};",
        "",
        "pub fn apply() {",
        "    {",
        "        let mut hard = config::HARD_SETTINGS.write().unwrap();",
    ]
    for k, v in flavor.get("hard", {}).items():
        lines.append(f"        hard.insert({rust_str(k)}.to_owned(), {rust_str(v)}.to_owned());")
    lines += [
        "    }",
        "    {",
        "        let mut builtin = config::BUILTIN_SETTINGS.write().unwrap();",
    ]
    for k, v in flavor.get("builtin", {}).items():
        lines.append(f"        builtin.insert({rust_str(k)}.to_owned(), {rust_str(v)}.to_owned());")
    lines += ["    }", "}", ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--flavor", default="suporte")
    ap.add_argument("--check", action="store_true", help="só valida as âncoras, não grava")
    ap.add_argument("--allow-missing-key", action="store_true",
                    help="permite build sem chave pública (apenas testes locais)")
    ap.add_argument("--reset", action="store_true",
                    help="restaura os arquivos do upstream antes de aplicar (troca de flavor local). "
                         "Descarta alterações não commitadas fora de edx/!")
    args = ap.parse_args()
    if args.reset and not args.check:
        reset_upstream()

    brand = json.loads((EDX / "brand.json").read_text(encoding="utf-8"))
    if args.flavor not in brand["flavors"]:
        sys.exit(f"flavor desconhecido: {args.flavor} (opções: {', '.join(brand['flavors'])})")
    flavor = brand["flavors"][args.flavor]
    app = flavor["app_name"]
    if not re.fullmatch(r"[A-Za-z0-9-]+", app):
        sys.exit(f"app_name '{app}' inválido: use só letras, números e hífen")

    key = os.environ.get("EDX_RS_PUB_KEY") or brand["public_key"]
    server = os.environ.get("EDX_RENDEZVOUS_SERVER") or brand["rendezvous_server"]
    if KEY_PLACEHOLDER in key:
        if not args.allow_missing_key and not args.check:
            if os.environ.get("GITHUB_ACTIONS"):
                print("::error title=EDX rebrand::chave pública do hbbs ausente "
                      "(variável de repositório EDX_RS_PUB_KEY ou edx/brand.json)")
            sys.exit("ERRO: public_key não configurada em edx/brand.json "
                     "(ou variável EDX_RS_PUB_KEY). Sem ela o app não confia no hbbs.")
        key = ""

    company = brand["company"]
    company_ascii = brand["company_ascii"]
    upstream = brand["upstream_copyright"]
    urls = brand["urls"]
    org = brand["org_id"]
    bundle = f"{org}.{app.lower().replace('-', '')}"
    color = brand["colors"]["primary"].lstrip("#").upper()
    from datetime import date
    year = date.today().year

    P = Patcher(check_only=args.check)

    # ------------------------------------------------------------------
    # 1. Núcleo Rust (libs/hbb_common é submódulo: patch só no build)
    # ------------------------------------------------------------------
    cfg = "libs/hbb_common/src/config.rs"
    P.regex(cfg, r'(pub static ref APP_NAME: RwLock<String> = RwLock::new\()"[^"]*"(\.to_owned\(\)\);)',
            rf'\1{rust_str(app)}\2', 1, 1, "APP_NAME")
    P.regex(cfg, r'(pub static ref ORG: RwLock<String> = RwLock::new\()"[^"]*"(\.to_owned\(\)\);)',
            rf'\1{rust_str(org)}\2', 1, 1, "ORG (macOS)")
    P.regex(cfg, r'pub const RENDEZVOUS_SERVERS: &\[&str\] = &\[[^\]]*\];',
            f'pub const RENDEZVOUS_SERVERS: &[&str] = &[{rust_str(server)}];', 1, 1, "RENDEZVOUS_SERVERS")
    P.regex(cfg, r'pub const RS_PUB_KEY: &str = "[^"]*";',
            f'pub const RS_PUB_KEY: &str = {rust_str(key)};', 1, 1, "RS_PUB_KEY")

    common = "src/common.rs"
    P.literal(common, '    "https://admin.rustdesk.com".to_owned()\n}',
              f'    {rust_str(brand["api_server"])}.to_owned() // EDX: servidor de API padrão\n}}', 1,
              "API server padrão")
    P.literal(common, "pub fn load_custom_client() {\n",
              "pub fn load_custom_client() {\n    crate::edx_branding::apply();\n", 1,
              "hook edx_branding::apply()")
    P.literal("src/lib.rs", "/// cbindgen:ignore\npub mod common;\n",
              "/// cbindgen:ignore\npub mod common;\nmod edx_branding;\n", 1, "mod edx_branding")
    P.write_new("src/edx_branding.rs", gen_branding_rs(brand, args.flavor, flavor))
    P.regex("src/client.rs", r'https://rustdesk\.com/docs/[^"]*', urls["support"], 1, None,
            "links de documentação", done_marker=urls["support"])

    # ------------------------------------------------------------------
    # 2. Interface Flutter
    # ------------------------------------------------------------------
    fl = "flutter/lib"
    P.regex_tree(fl, "*.dart", r"https://rustdesk\.com/privacy\.html", urls["privacy"], "URL privacidade")
    P.regex_tree(fl, "*.dart", r"https://rustdesk\.com/docs/[^'\"\s]*", urls["support"], "URLs documentação")
    P.regex_tree(fl, "*.dart", r"https://rustdesk\.com/download", urls["download"], "URL download")
    P.regex_tree(fl, "*.dart", r"https://rustdesk\.com/pricing", urls["website"], "URL preços")
    P.regex_tree(fl, "*.dart", r"https://rustdesk\.com/?(?=['\"])", urls["website"], "URL site")
    P.regex_tree(fl, "*.dart", r"(Text\(\s*)'rustdesk\.com'", r"\1" + dart_str(urls["website"].split("//")[1]),
                 "texto rustdesk.com (mobile)")

    tab = "flutter/lib/desktop/widgets/tabbar_widget.dart"
    P.regex(tab, r'(const Text\(\s*)"RustDesk"', rf'\1"{app}"', 1, 1, "título da barra de abas",
            done_marker=f'"{app}"')

    about = "flutter/lib/desktop/pages/desktop_setting_page.dart"
    P.literal(about,
              "'Copyright © ${DateTime.now().toString().substring(0, 4)} Purslane Tech Pte. Ltd.\\n$license',",
              "'© ${DateTime.now().toString().substring(0, 4)} " + company.replace("'", "\\'") +
              "\\nSoftware livre sob a licença GNU AGPL-3.0, sem garantia de qualquer tipo."
              "\\nDerivado de trabalho Copyright © " + upstream +
              "\\nCódigo-fonte: " + urls["source"] + "\\n$license',",
              1, "aviso de copyright (Sobre)")
    P.literal(about, "translate('Slogan_tip'),", dart_str(brand["tagline"]) + ",", 1, "slogan (Sobre)")
    P.literal(about, "decoration: const BoxDecoration(color: Color(0xFF2c8cff)),",
              f"decoration: const BoxDecoration(color: Color(0xFF{color})),", 1, "cor do cartão Sobre")
    # link explícito para o código-fonte (AGPL §6/§13), logo após "Website"
    P.literal(about,
              "                  child: Text(\n                    translate('Website'),\n"
              "                    style: linkStyle,\n                  ).marginSymmetric(vertical: 4.0)),\n",
              "                  child: Text(\n                    translate('Website'),\n"
              "                    style: linkStyle,\n                  ).marginSymmetric(vertical: 4.0)),\n"
              "              InkWell(\n                  onTap: () {\n"
              f"                    launchUrlString({dart_str(urls['source'])});\n"
              "                  },\n                  child: Text(\n"
              "                    'Código-fonte e licença (AGPL-3.0)',\n"
              "                    style: linkStyle,\n                  ).marginSymmetric(vertical: 4.0)),\n",
              1, "link código-fonte (Sobre)")

    # ------------------------------------------------------------------
    # 3. Metadados por sistema operacional
    # ------------------------------------------------------------------
    rc = "flutter/windows/runner/Runner.rc"
    for field, value in [("CompanyName", company),
                         ("FileDescription", f"{app} - {brand['tagline']}"),
                         ("LegalCopyright", f"© {year} {company}. Partes © {upstream} (AGPL-3.0)."),
                         ("ProductName", app)]:
        P.regex(rc, rf'(VALUE "{field}", )"[^"]*"', rf'\1"{value}"', 1, 1, f"Runner.rc {field}")

    for toml in ["Cargo.toml", "libs/portable/Cargo.toml"]:
        P.regex(toml, r'(?m)^LegalCopyright = "[^"]*"',
                f'LegalCopyright = "(c) {year} {company_ascii}. Portions (c) {upstream} (AGPL-3.0)."',
                1, 1, f"{toml} LegalCopyright")
        P.regex(toml, r'(?m)^ProductName = "[^"]*"', f'ProductName = "{app}"', 1, 1, f"{toml} ProductName")
        P.regex(toml, r'(?m)^FileDescription = "[^"]*"', f'FileDescription = "{app}"', 1, 1,
                f"{toml} FileDescription")

    # pasta de extração do executável portátil (%LOCALAPPDATA%\<app>)
    P.regex("libs/portable/src/main.rs", r'const APP_PREFIX: &str = "[^"]*";',
            f'const APP_PREFIX: &str = "{app.lower()}";', 1, 1, "pasta do portátil")

    xc = "flutter/macos/Runner/Configs/AppInfo.xcconfig"
    P.regex(xc, r"(?m)^PRODUCT_NAME = [^\r\n]*", f"PRODUCT_NAME = {app}", 1, 1, "macOS PRODUCT_NAME")
    P.regex(xc, r"(?m)^PRODUCT_BUNDLE_IDENTIFIER = [^\r\n]*", f"PRODUCT_BUNDLE_IDENTIFIER = {bundle}", 1, 1,
            "macOS bundle id")
    P.regex(xc, r"(?m)^PRODUCT_COPYRIGHT = [^\r\n]*",
            f"PRODUCT_COPYRIGHT = © {year} {company}. Partes © {upstream} (AGPL-3.0).", 1, 1,
            "macOS copyright")
    P.regex("flutter/macos/Runner/Info.plist", r"(<key>CFBundleURLSchemes</key>\s*<array>\s*<string>)rustdesk(</string>)",
            rf"\g<1>{app.lower()}\2", 1, 1, "esquema de URL (macOS)", done_marker=f"<string>{app.lower()}</string>")
    # nome do .app usado pelo build.py e pelo script de distribuição
    P.regex("build.py", r"(Products/Release/|--icon |--hide-extension )RustDesk\.app", rf"\g<1>{app}.app",
            3, None, "build.py: nome do .app (Flutter)", done_marker=f"Release/{app}.app")
    P.regex("res/osx-dist.sh", r"RustDesk\.app", f"{app}.app", 1, None, "osx-dist.sh: nome do .app",
            done_marker=f"{app}.app")
    P.regex("build.py", r'--volname \\"RustDesk Installer\\"', f'--volname \\\\"{app}\\\\"', 1, 1,
            "build.py volume DMG", done_marker=f'--volname \\"{app}\\"')

    P.regex("flutter/linux/my_application.cc", r'gtk_window_set_title\(window, "rustdesk"\)',
            f'gtk_window_set_title(window, "{app}")', 1, None, "título da janela (Linux)",
            done_marker=f'"{app}"')
    for desk in ["res/rustdesk.desktop", "res/rustdesk-link.desktop"]:
        P.regex(desk, r"(?m)^Name=RustDesk(?=\r?$)", f"Name={app}", 0, 1, f"{desk} Name")
    P.regex("res/rustdesk-link.desktop", r"x-scheme-handler/rustdesk;", f"x-scheme-handler/{app.lower()};",
            1, 1, "esquema de URL (Linux)", done_marker=f"x-scheme-handler/{app.lower()};")
    P.regex("res/rustdesk.desktop", r"(?m)^Comment=[^\r\n]*", f"Comment={brand['tagline']}", 1, 1,
            "Linux .desktop Comment")

    # ------------------------------------------------------------------
    # 4. Ícones e logos
    # ------------------------------------------------------------------
    for src, dst in [
        ("icon.png", "res/icon.png"),
        ("32x32.png", "res/32x32.png"),
        ("64x64.png", "res/64x64.png"),
        ("128x128.png", "res/128x128.png"),
        ("128x128@2x.png", "res/128x128@2x.png"),
        ("mac-icon.png", "res/mac-icon.png"),
        ("mac-tray-dark-x2.png", "res/mac-tray-dark-x2.png"),
        ("mac-tray-light-x2.png", "res/mac-tray-light-x2.png"),
        ("icon.ico", "res/icon.ico"),
        ("tray-icon.ico", "res/tray-icon.ico"),
        ("scalable.svg", "res/scalable.svg"),
        ("app_icon.ico", "flutter/windows/runner/resources/app_icon.ico"),
        ("AppIcon.icns", "flutter/macos/Runner/AppIcon.icns"),
        ("icon.svg", "flutter/assets/icon.svg"),
        ("flutter-icon.png", "flutter/assets/icon.png"),
        ("logo.png", "flutter/assets/logo.png"),
        ("logo_light.png", "flutter/assets/logo_light.png"),
        ("logo_dark.png", "flutter/assets/logo_dark.png"),
    ]:
        P.copy(src, dst)

    # ------------------------------------------------------------------
    # 5. Aviso legal distribuído junto com o código modificado
    # ------------------------------------------------------------------
    if not args.check and not P.errors:
        write_notice(brand, args.flavor, app, P.changed)

    # ------------------------------------------------------------------
    print(f"\n== EDX rebrand  flavor={args.flavor}  app={app}  servidor={server}"
          f"  chave={'OK' if key else 'AUSENTE (teste)'}  {'(somente verificação)' if args.check else ''}")
    for rel, label, n in P.changed:
        print(f"  ✔ {rel:55s} {label} ({n})")
    for rel, label in P.skipped:
        print(f"  · {rel:55s} {label} (já aplicado)")
    if P.errors:
        print("\n== FALHAS (o upstream mudou? ajuste a âncora em rebrand.py):")
        for e in P.errors:
            print(f"  ✘ {e}")
        if os.environ.get("GITHUB_ACTIONS"):
            # aparece no resumo da execução, sem precisar abrir o log
            for e in P.errors[:10]:
                print(f"::error title=EDX rebrand::{e}")
        sys.exit(1)

    if not args.check:
        audit(app)


def upstream_version():
    m = re.search(r'(?m)^version = "([^"]+)"', (ROOT / "Cargo.toml").read_text(encoding="utf-8"))
    return m.group(1) if m else "desconhecida"


def write_notice(brand, flavor, app, changed):
    """Aviso de modificação exigido pela AGPL-3.0 §5(a): o que mudou e quando."""
    from datetime import datetime, timezone
    files = sorted({rel for rel, _, _ in changed})
    body = [
        f"# Aviso de modificação: {app}",
        "",
        f"Este programa é uma versão modificada do RustDesk {upstream_version()},",
        f"Copyright © {brand['upstream_copyright']}, distribuído sob a GNU Affero",
        "General Public License v3.0 (arquivo LICENCE na raiz deste repositório).",
        "",
        f"Modificado por {brand['company']} em "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}, perfil `{flavor}`.",
        "As modificações (marca, servidor padrão, ícones, opções travadas) são",
        "aplicadas pelo script `edx/scripts/rebrand.py` a partir de `edx/brand.json`,",
        "ambos incluídos neste repositório e também licenciados sob AGPL-3.0.",
        "",
        f"Código-fonte correspondente: {brand['urls']['source']}",
        "",
        "Este programa é distribuído SEM QUALQUER GARANTIA, nem mesmo a garantia",
        "implícita de COMERCIALIZAÇÃO ou ADEQUAÇÃO A UM PROPÓSITO ESPECÍFICO.",
        "",
        "## Arquivos alterados neste build",
        "",
    ] + [f"- `{f}`" for f in files] + [""]
    with open(ROOT / "EDX-NOTICE.md", "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(body))


GENERATED_FILES = [
    "src/edx_branding.rs", "EDX-NOTICE.md", "flutter/assets/icon.png",
    "flutter/assets/logo.png", "flutter/assets/logo_light.png", "flutter/assets/logo_dark.png",
]


def reset_upstream():
    import subprocess
    print("== --reset: restaurando arquivos do upstream (edx/ e workflows edx-* preservados)")
    subprocess.run(["git", "checkout", "--", ".", ":(exclude)edx", ":(exclude).github/workflows/edx-*"],
                   cwd=ROOT, check=True)
    sub = ROOT / "libs" / "hbb_common"
    if (sub / ".git").exists():
        subprocess.run(["git", "checkout", "--", "."], cwd=sub, check=True)
    for rel in GENERATED_FILES:
        f = ROOT / rel
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=ROOT,
                                 capture_output=True).returncode == 0
        if f.exists() and not tracked:
            f.unlink()


def audit(app):
    """Lista o que ainda mostra 'RustDesk' em arquivos que chegam ao usuário final."""
    hits = []
    targets = [
        ("flutter/lib/desktop", "*.dart"),
        ("flutter/windows/runner", "*.rc"),
        ("flutter/macos/Runner/Configs", "*.xcconfig"),
        ("res", "*.desktop"),
    ]
    for base, glob in targets:
        for p in (ROOT / base).rglob(glob):
            for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                t = line.strip()
                if "RustDesk" in t and not t.startswith(("//", "#", "*")) and "translate(" not in t \
                        and "RustDeskMultiWindowManager" not in t and "isRustDeskIdd" not in t \
                        and "RustDeskVirtualDisplays" not in t:
                    hits.append(f"{p.relative_to(ROOT)}:{i}: {t[:100]}")
    print(f"\n== Auditoria de marca visível: {len(hits)} ocorrência(s) restante(s)")
    for h in hits[:40]:
        print("  ?", h)
    print("  (textos passados por translate() trocam 'RustDesk' pelo nome do app automaticamente)")


if __name__ == "__main__":
    main()
