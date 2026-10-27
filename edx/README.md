# EDX-Suporte: fork do RustDesk com a marca EDX

Este diretório transforma o código oficial do RustDesk em dois apps EDX:

| Perfil | App | Para quem | Comportamento |
|---|---|---|---|
| `suporte` | **EDX-Suporte** | cliente final | Executável portátil, só recebe conexões, sem instalação, configurações travadas em `remote.edxinfo.com.br` |
| `tecnico` | **EDX-Tecnico** | técnicos EDX | Conecta e recebe, pode instalar, servidor travado |

O código do upstream **não é editado no git**. A marca é aplicada no momento do
build por `edx/scripts/rebrand.py`, o que deixa a sincronização com novas
versões do RustDesk praticamente sem conflitos.

```
edx/
├── brand.json              ← tudo que é EDX: nome, servidor, chave, URLs, cores, perfis
├── assets/logo.png         ← logo de origem
├── assets/generated/       ← ícones prontos (gerados, versionados)
├── scripts/rebrand.py      ← aplica a marca (stdlib Python, sem dependências)
├── scripts/gen_icons.py    ← regenera os ícones quando o logo mudar (Pillow)
├── scripts/make_workflow.py← gera o CI a partir do workflow oficial
└── RELEASE_NOTES.md        ← texto padrão das releases
.github/workflows/
├── edx-build.yml           ← GERADO: jobs Windows/macOS/Linux do upstream + passo de marca
└── edx-release.yml         ← dispara o build, renomeia pacotes, publica fonte + licença
```

---

## 1. Montar o fork (uma vez)

```bash
# no GitHub: criar o fork público de rustdesk/rustdesk em <org>/edx-suporte
git clone --recurse-submodules https://github.com/<org>/edx-suporte.git
cd edx-suporte
git remote add upstream https://github.com/rustdesk/rustdesk.git
git checkout -b edx 1.4.9            # base: tag estável do upstream

# copiar este kit para a raiz do repositório (pastas edx/ e .github/workflows/edx-*.yml)
git add edx .github/workflows/edx-*.yml
git commit -m "EDX: kit de marca e CI"
git push -u origin edx
```

No GitHub, em **Settings → General**, defina `edx` como branch padrão.
Em **Actions**, desative os workflows do upstream (*Flutter Nightly Build*,
*Flutter Tag Build*, *CI*, *playground* etc.). Eles gastam minutos e publicam
binários com a marca original.

## 2. Preencher `brand.json`

| Campo | O que colocar |
|---|---|
| `public_key` | Conteúdo de `id_ed25519.pub` do hbbs (no Docker, fica no volume de dados, ex. `/root/id_ed25519.pub`). Alternativa: variável de repositório `EDX_RS_PUB_KEY` em *Settings → Secrets and variables → Actions → Variables* |
| `urls.source` / `urls.download` | URL real do fork e da página de releases |
| `urls.website` / `privacy` / `support` | Páginas da EDX que o app abre |
| `api_server` | Deixe vazio com o hbbs OSS. Preencha só se tiver Server Pro ou API compatível |

> O build **falha de propósito** se a chave pública não estiver configurada. Sem
> ela o cliente não valida o hbbs e a conexão fica sem a garantia de servidor
> autêntico. Confirme também que o hbbs recusa clientes sem chave (versões
> recentes já fazem isso por padrão; nas antigas, inicie com `-k _`).

## 3. Gerar uma versão

```bash
git tag edx-1.4.9-1        # <versão upstream>-<revisão EDX>
git push origin edx-1.4.9-1
```

O workflow `EDX release` compila (de 1 a 2 horas) e publica na release:

- `EDX-Suporte-1.4.9-x86_64.exe` e `-aarch64.exe`: portáteis Windows
- `EDX-Suporte-1.4.9-x86_64.dmg` e `-aarch64.dmg`: macOS
- `EDX-Suporte-1.4.9-x86_64.AppImage` e `-aarch64.AppImage`: Linux portátil
- `EDX-Suporte-…-source.tar.gz`: código-fonte correspondente, já com a marca aplicada
- `LICENCE.txt`, `EDX-NOTICE.md`, `SHA256SUMS.txt`

Para o app dos técnicos: aba **Actions → EDX release → Run workflow → flavor
`tecnico`**. No perfil `suporte`, instaladores (.msi, .deb, .rpm) são removidos
da release; no `tecnico`, ficam.

As releases saem como *pre-release*. Teste e promova manualmente.

### Link permanente ("sempre a última versão")

Os portáteis saem com nome fixo, sem versão (`EDX-Suporte-x86_64.exe`,
`EDX-Suporte-aarch64.dmg` etc.). Depois de testar, edite a release e marque
**Set as the latest release**. A partir daí, estes links apontam sempre para ela:

| Sistema | Link |
|---|---|
| Windows x64 | `https://github.com/edxtec/edx-suporte/releases/latest/download/EDX-Suporte-x86_64.exe` |
| Windows ARM | `…/releases/latest/download/EDX-Suporte-aarch64.exe` |
| macOS Intel | `…/releases/latest/download/EDX-Suporte-x86_64.dmg` |
| macOS Apple Silicon | `…/releases/latest/download/EDX-Suporte-aarch64.dmg` |
| Linux x64 / ARM | `…/releases/latest/download/EDX-Suporte-x86_64.AppImage` / `-aarch64.AppImage` |

Releases do perfil `tecnico` devem ficar sempre como *pre-release*: o GitHub tem
um único "latest" por repositório.

### Cópia local e atalho (Windows)

Com o bloco `windows_self_install` do perfil em `brand.json`, ao abrir o `.exe`
baixado ele se copia para `%LOCALAPPDATA%\EDX-RustDesk\EDX-Suporte.exe` e cria
o atalho **EDX Suporte Remoto** na Área de Trabalho (respeitando Área de Trabalho
redirecionada para o OneDrive). Sem admin, sem registro, sem serviço: o app continua
portátil. Abrir a versão nova baixada substitui a cópia; se a cópia antiga estiver
aberta, a substituição falha em silêncio e acontece na próxima vez.

## 4. Atualizar para uma nova versão do RustDesk

```bash
git fetch upstream --tags
git merge 1.4.10                     # conflitos são raros: o kit não toca o upstream
git submodule update --init --recursive
python3 edx/scripts/rebrand.py --check          # confere as âncoras
python3 edx/scripts/make_workflow.py            # regenera edx-build.yml
git add -A && git commit -m "EDX: base 1.4.10"
git tag edx-1.4.10-1 && git push origin edx --tags
```

Se o `--check` acusar `✘ âncora não encontrada`, o upstream mudou aquele trecho.
Ajuste o padrão correspondente em `rebrand.py`. O script nunca gera um binário
com marca pela metade.

## 5. Build local (opcional)

```bash
python3 edx/scripts/rebrand.py --flavor suporte                  # aplica a marca
python3 edx/scripts/rebrand.py --reset --flavor tecnico          # troca de perfil
python3 build.py --flutter --portable                            # ver docs do upstream
```

`--reset` restaura os arquivos do upstream antes de aplicar e descarta
alterações não commitadas fora de `edx/`.

## 6. Elevação de privilégios

Nada a configurar: o RustDesk portátil no Windows já traz o botão **Elevar**
(UAC) na janela de conexão do cliente, e o técnico pode **Solicitar elevação**
pela barra de ferramentas. No macOS não existe elevação; o usuário concede
*Gravação de Tela* e *Acessibilidade* nos Ajustes. No Linux, Wayland exige
confirmação do usuário a cada sessão.

## 7. Assinatura de código (Windows: Certum)

O job `finalize` assina os `.exe` antes do `SHA256SUMS` e do upload, usando o
certificado **Certum Standard Code Signing in the Cloud** e a ferramenta
[`ssign`](https://github.com/Le-Syl21/ssign) (MIT, independente da Certum).

1. Em **Settings → Environments**, crie o ambiente `signing` e marque
   **Required reviewers** (você). Nenhuma release é assinada sem sua aprovação.
2. Nesse ambiente, crie os *secrets*:
   - `CERTUM_EMAIL`: e-mail da conta SimplySign
   - `CERTUM_OTP`: semente TOTP (base32) ou a URI `otpauth://` do QR de ativação do SimplySign
3. Sem esses secrets, o passo é pulado com um aviso e o `.exe` sai sem assinatura.

A semente TOTP dá poder de assinar em nome da EDX: guarde-a só no secret e, se
vazar, gere um novo QR no SimplySign.

### Alternativa sem custo: CA interna da EDX

O passo "CA interna EDX" assina com um certificado emitido pela CA da EDX
(`edx/scripts/sign_internal.sh`, via `osslsigncode`, com carimbo de tempo).
A assinatura só é **reconhecida onde a raiz EDX está distribuída** (GPO/Intune);
nos demais computadores o Windows mostra "Fornecedor desconhecido", como sem
assinatura. Se a Certum também estiver configurada, a assinatura interna entra
aninhada e as duas valem.

1. Na CA (AD CS), emita um certificado com o modelo **Assinatura de Código**
   (EKU *Code Signing*), assunto `EDX Tecnologia em Informação Ltda`, validade de
   1 ano, e **dedicado a este app**.
2. Exporte como `.pfx` **com a chave privada e a cadeia completa**.
3. Em PowerShell: `[Convert]::ToBase64String([IO.File]::ReadAllBytes("edx-cs.pfx")) | Set-Clipboard`
4. No ambiente `signing`, crie os secrets `EDX_SIGN_PFX_B64` (o texto copiado) e
   `EDX_SIGN_PFX_PASS` (a senha do `.pfx`). Apague o `.pfx` exportado.
5. Se o certificado foi emitido por uma **CA intermediária** (que não está na GPO),
   crie no mesmo ambiente a *variável* `EDX_SIGN_CHAIN` com o PEM da intermediária
   (`-----BEGIN CERTIFICATE-----` … `-----END CERTIFICATE-----`). Ela é embutida em
   cada assinatura; sem ela o Windows não fecha a cadeia até a raiz.

Quem obtiver esse `.pfx` consegue assinar programas que serão confiáveis em
**todas** as máquinas que recebem a raiz EDX por GPO/Intune. Por isso: certificado
exclusivo, validade curta, revisores obrigatórios no ambiente `signing` e
revogação imediata na CA em caso de vazamento.

**macOS**: exige conta Apple Developer (Developer ID + notarização); fica para depois.

## 8. Licença: o que este fork cumpre e por quê

O RustDesk é AGPL-3.0. Distribuir um binário modificado é permitido, desde que:

| Exigência | Como o fork atende |
|---|---|
| Código-fonte para quem recebe o binário (§6) | Fork público + tarball do fonte exato publicado na mesma release do binário |
| Aviso de que o código foi modificado, com data (§5a) | `EDX-NOTICE.md`, gerado a cada build com a lista de arquivos alterados |
| Mesma licença para a obra derivada (§5c) | `LICENCE` mantida; o kit `edx/` também é AGPL-3.0 |
| Avisos legais na interface (§5d) | Tela *Sobre*: copyright EDX, "Derivado de trabalho © Purslane Tech Pte. Ltd.", ausência de garantia e link para o código-fonte |
| Cópia da licença junto do executável (§4) | `LICENCE.txt` em cada release |

A **marca** "RustDesk" sai de toda a interface, como pedido. O **copyright** da
Purslane Tech não pode sair e fica na tela Sobre e nos metadados do executável.
Remover avisos de copyright violaria a licença, e com ela o direito de
distribuir o fork.

Não é aconselhamento jurídico. Para uso comercial em escala, vale uma revisão
por advogado de propriedade intelectual.

## 9. Limitações conhecidas

- Identificadores internos continuam com o nome original: a biblioteca `librustdesk`, o executável `rustdesk.exe` dentro do pacote portátil (aparece em *Gerenciador de Tarefas → Detalhes*; a aba *Processos* mostra "EDX-Suporte"), o auxiliar `RuntimeBroker_rustdesk.exe` e os caminhos internos do AppImage. Renomeá-los mexe em dezenas de pontos do upstream e aumenta o custo de cada atualização.
- O ícone é derivado do logo horizontal. Em 16 e 24 px a marca fica pequena. Com um símbolo quadrado da EDX, basta trocar `assets/logo.png` (ou adaptar `gen_icons.py`) e rodar `python3 edx/scripts/gen_icons.py`.
- Textos de ajuda ligados ao "RustDesk Server Pro" permanecem; só aparecem em recursos do Pro, que não se aplicam ao hbbs OSS.
