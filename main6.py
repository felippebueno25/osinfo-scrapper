import asyncio
import os
import shutil
import csv
from playwright.async_api import async_playwright

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.panel import Panel

# === CONFIGURAÇÕES ===
SEU_USUARIO = "fbueno"
SUA_SENHA = "310710"
CONTRATO_ALVO = "002/2021-52"
CSV_DESPESAS = "rubricas.csv"
SESSION_FILE = "session_osinfo.json"

# Configuração do Período Alvo
ANO_ALVO = "2026"
MES_DATA_VALUE = "2"      # 0=Janeiro, 1=Fevereiro, 2=Março ...
NOME_MES_PASTA = "Março"

# Organização de Pastas
BASE_Z = r"E:\PRESTAÇÃO DE CONTAS OS\OSINFO_DESPESAS_DOWNLOADS"
CAMINHO_FINAL = os.path.join(BASE_Z, f"{NOME_MES_PASTA}_{ANO_ALVO}")
CAMINHO_TEMPORARIO = r"C:\temp_osinfo_stage"

console = Console()


def sanitizar_nome(texto: str) -> str:
    """Normaliza o texto do link para nome de arquivo seguro."""
    return "".join(c for c in texto.strip() if c.isalnum() or c in (" ", "_", "-")).strip()


async def automate_osinfo():
    console.print(Panel.fit(
        f"[bold cyan]OSINFO BATCH PROCESSOR[/bold cyan]\n"
        f"[white]Período:[/white] [yellow]{NOME_MES_PASTA}/{ANO_ALVO}[/yellow]\n"
        f"[white]Dataset:[/white] [green]{CSV_DESPESAS}[/green]",
        border_style="blue"
    ))

    # Garante existência das pastas
    for caminho in [CAMINHO_FINAL, CAMINHO_TEMPORARIO]:
        os.makedirs(caminho, exist_ok=True)

    # ── PRÉ-INDEXAÇÃO EM MEMÓRIA ──────────────────────────────────────────────
    # Carrega UMA VEZ todos os PDFs já presentes no destino.
    # Checagens futuras serão O(1) em memória, sem syscall por arquivo.
    arquivos_existentes: set[str] = {
        f for f in os.listdir(CAMINHO_FINAL) if f.lower().endswith(".pdf")
    }
    console.print(
        f"[cyan]📂 {len(arquivos_existentes)} PDFs já existentes indexados em memória.[/cyan]"
    )
    # ─────────────────────────────────────────────────────────────────────────

    # Leitura do CSV de despesas
    lista_despesas: list[str] = []
    try:
        with open(CSV_DESPESAS, mode="r", encoding="utf-8") as f:
            lista_despesas = [linha[0] for linha in csv.reader(f) if linha]
        console.print(f"[yellow]✔ {len(lista_despesas)} despesas carregadas do CSV.[/yellow]")
    except Exception as e:
        console.print(f"[bold red]❌ Erro ao ler CSV:[/bold red] {e}")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=200)

        # Gestão de Sessão
        ctx_kwargs = dict(accept_downloads=True, viewport={"width": 1920, "height": 1080})
        if os.path.exists(SESSION_FILE):
            context = await browser.new_context(storage_state=SESSION_FILE, **ctx_kwargs)
        else:
            context = await browser.new_context(**ctx_kwargs)
            _login_page = await context.new_page()
            # ... lógica de login aqui se necessário ...

        page = await context.new_page()
        await page.goto("https://osinfo.prefeitura.rio/pages/application-container.html")

        # Fecha aviso inicial se existir
        try:
            await page.click("#avisoRH .btn-secondary", timeout=3000)
        except Exception:
            pass

        # Navega até a seção de Despesas
        await page.click('a[href="#SubMenu2"]')
        await page.wait_for_selector("#Despesa", state="visible")
        await page.click("#Despesa")

        # ── 1. FILTRO DE COMPETÊNCIA ─────────────────────────────────────────
        console.print(f"[bold blue]📅 Ajustando período para {NOME_MES_PASTA}/{ANO_ALVO}...[/bold blue]")
        try:
            await page.wait_for_selector("#monthlyExpenses", state="visible")
            await page.click("#monthlyExpenses")
            await asyncio.sleep(1)

            await page.locator("#calendarYear").select_option(ANO_ALVO, force=True)
            await asyncio.sleep(1)

            seletor_mes = f'button[data-value="{MES_DATA_VALUE}"]'
            await page.wait_for_selector(seletor_mes, state="visible")
            await page.click(seletor_mes)

            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(4)
        except Exception as e:
            console.print(f"[bold red]⚠️ Erro ao mudar o período:[/bold red] {e}")
            await page.keyboard.press("Escape")
        # ─────────────────────────────────────────────────────────────────────

        # ── 2. FILTRO DE CONTRATO ────────────────────────────────────────────
        if not await page.locator("#numeroContrato").is_visible():
            await page.wait_for_selector("#expensesTableColumnFilterButton")
            await page.click("#expensesTableColumnFilterButton")
            await asyncio.sleep(1)

        await page.fill("#numeroContrato", CONTRATO_ALVO)
        await page.keyboard.press("Enter")
        await asyncio.sleep(3)
        # ─────────────────────────────────────────────────────────────────────

        total_baixado = 0
        total_pulado = 0

        # ── 3. LOOP PRINCIPAL DE DESPESAS ────────────────────────────────────
        for despesa_termo in lista_despesas:
            console.print(f"\n[bold magenta]🔎 Filtrando despesa:[/bold magenta] {despesa_termo}")

            if not await page.locator("#descricaoDespesa").is_visible():
                await page.click("#expensesTableColumnFilterButton")
                await asyncio.sleep(1)

            await page.fill("#descricaoDespesa", "")
            await page.fill("#descricaoDespesa", despesa_termo)
            await page.keyboard.press("Enter")
            await asyncio.sleep(4)

            tem_proxima_pagina = True

            while tem_proxima_pagina:
                links = await page.query_selector_all('a[onclick*="showSelectedDocument"]')

                if not links:
                    console.print(
                        f"[grey50]ℹ Nenhuma linha encontrada para '{despesa_termo}'.[/grey50]"
                    )
                    break

                # ── SKIP DE PÁGINA INTEIRA ────────────────────────────────
                # Pré-resolve todos os nomes da página antes de abrir qualquer doc.
                itens_pagina: list[tuple] = []
                for link in links:
                    texto = (await link.inner_text()).strip()
                    nome_limpo = sanitizar_nome(texto)
                    nome_final = f"{nome_limpo}.pdf"
                    itens_pagina.append((link, nome_limpo, nome_final))

                pendentes = [
                    (lk, nl, nf) for lk, nl, nf in itens_pagina
                    if nf not in arquivos_existentes
                ]

                pulados_pagina = len(itens_pagina) - len(pendentes)
                total_pulado += pulados_pagina

                if not pendentes:
                    console.print(
                        f"[grey50]⏩ Página inteira já baixada "
                        f"({len(itens_pagina)} arquivos). Avançando...[/grey50]"
                    )
                else:
                    if pulados_pagina:
                        console.print(
                            f"[grey50]⏩ {pulados_pagina} arquivo(s) pulados nesta página.[/grey50]"
                        )

                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        BarColumn(),
                        TaskProgressColumn(),
                        console=console,
                    ) as progress:
                        task = progress.add_task("[cyan]Baixando...", total=len(pendentes))

                        for link, nome_limpo, nome_final in pendentes:
                            caminho_z = os.path.join(CAMINHO_FINAL, nome_final)
                            caminho_local = os.path.join(CAMINHO_TEMPORARIO, nome_final)

                            try:
                                await link.click()
                                await page.wait_for_selector(
                                    "#documentViewDownloadButton", state="visible", timeout=15000
                                )

                                async with page.expect_download(timeout=0) as dl_info:
                                    await page.click("#documentViewDownloadButton")

                                download = await dl_info.value
                                await download.save_as(caminho_local)
                                shutil.move(caminho_local, caminho_z)

                                # ── Atualiza o índice em memória imediatamente ──
                                arquivos_existentes.add(nome_final)

                                total_baixado += 1
                                progress.update(
                                    task,
                                    advance=1,
                                    description=f"[green]✅ {nome_limpo[:25]}[/green]",
                                )

                                await page.click("#documentViewBackButton")
                                await page.wait_for_selector("#documentView", state="hidden")

                            except Exception:
                                await page.keyboard.press("Escape")
                                progress.update(
                                    task,
                                    advance=1,
                                    description=f"[red]❌ ERRO: {nome_limpo[:25]}[/red]",
                                )
                # ─────────────────────────────────────────────────────────────

                # Verifica próxima página de resultados desta despesa
                botao_proximo = await page.query_selector(
                    "#expensesTable_paginate li.active + li:not(.disabled) a"
                )
                if botao_proximo:
                    console.print(
                        f"[bold yellow]➡️  Próxima página — {despesa_termo}...[/bold yellow]"
                    )
                    await botao_proximo.click()
                    await asyncio.sleep(4)
                    await page.wait_for_load_state("networkidle")
                else:
                    tem_proxima_pagina = False
        # ─────────────────────────────────────────────────────────────────────

        console.print(
            f"\n[bold green]🏁 Concluído! "
            f"{total_baixado} baixados · {total_pulado} pulados · "
            f"destino: {NOME_MES_PASTA}/{ANO_ALVO}[/bold green]"
        )
        await browser.close()


if __name__ == "__main__":
    asyncio.run(automate_osinfo())
