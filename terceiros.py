import asyncio
import os
import shutil
from datetime import datetime
from typing import Any

from playwright.async_api import async_playwright
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

SEU_USUARIO = os.getenv("SEU_USUARIO", "")
SUA_SENHA = os.getenv("SUA_SENHA", "")
CONTRATO_ALVO = os.getenv("CONTRATO_ALVO", "").strip()

SESSION_FILE = "session_osinfo.json"

BASE_Z = r"C:\Users\CAP52\Downloads\codigo\sei-scrapper\osinfo-scrapper\OSINFO_CONTRATOS_TERCEIROS_DOWNLOADS"
CAMINHO_TEMPORARIO = r"C:\temp_osinfo_stage"

TERMOS_ARQUIVOS = [
    "ANEXO",
    "DECLARACOES",
    "CERTIDOES",
    "DESP_FIXAS",
    "RHOS_RH_PROVISAO",
    "GUIAPAGAMENTO",
    "BLOCOE",
]

TABELA_CONTRATOS = "supplierContractTable"
BOTAO_FILTROS = "#supplierContractTableColumnFilterButton"
FILTRO_MES = 'input.columnSearch[id="3"]'
FILTRO_ANO = 'input.columnSearch[id="4"]'
FILTRO_CONTRATO = 'input.columnSearch[id="7"]'
FILTRO_ARQUIVO = 'input.columnSearch[id="17"]'

console = Console()

MESES_PT = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]


def sanitizar_nome(texto: str) -> str:
    return "".join(c for c in texto.strip() if c.isalnum() or c in (" ", "_", "-")).strip()


def solicitar_periodo() -> tuple[str, str, str]:
    ano_atual = datetime.now().year
    while True:
        mes_input = input("Mês para baixar (1-12) [4]: ").strip() or "4"
        if mes_input.isdigit() and 1 <= int(mes_input) <= 12:
            mes_num = int(mes_input)
            break
        console.print("[red]Mês inválido.[/red]")

    while True:
        ano_input = input("Ano para baixar [2026]: ").strip() or "2026"
        if ano_input.isdigit() and 2000 <= int(ano_input) <= ano_atual + 1:
            ano = ano_input
            break
        console.print("[red]Ano inválido.[/red]")

    return ano, str(mes_num), MESES_PT[mes_num - 1]


async def preparar_contexto(page, ano_alvo: str, mes_data_value: str, contrato_alvo: str) -> None:
    await page.goto("https://osinfo.prefeitura.rio/pages/application-container.html")

    try:
        await page.click("#avisoRH .btn-secondary", timeout=5000)
    except Exception:
        pass

    await page.click('a[href="#SubMenu2"]')
    await page.click('a[href="#SubSubMenu3"]')
    await page.wait_for_selector("#CtrTerce", state="visible")
    await page.click("#CtrTerce")

    console.print(f"[bold blue]⏳ Configurando filtros para {ano_alvo}/{mes_data_value}...[/bold blue]")
    await page.click(BOTAO_FILTROS)

    mes_locator = page.locator(FILTRO_MES).first
    ano_locator = page.locator(FILTRO_ANO).first
    contrato_locator = page.locator(FILTRO_CONTRATO).first

    if await mes_locator.count():
        await mes_locator.fill(mes_data_value)
    if await ano_locator.count():
        await ano_locator.fill(ano_alvo)
    if contrato_alvo and await contrato_locator.count():
        await contrato_locator.fill(contrato_alvo)

    await page.keyboard.press("Enter")

    await page.wait_for_selector(f"#{TABELA_CONTRATOS}_processing", state="hidden", timeout=30000)
    await asyncio.sleep(2)


async def carregar_todos_os_registros(page) -> None:
    console.print("[bold yellow]🚀 Solicitando TODOS os registros ao servidor (-1)...[/bold yellow]")
    seletor_quantidade = f'select[name="{TABELA_CONTRATOS}_length"]'

    await page.evaluate(
        """(sel) => {
            const dropdown = document.querySelector(sel);
            if (dropdown) {
                dropdown.value = "-1";
                dropdown.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }""",
        seletor_quantidade,
    )

    try:
        await page.wait_for_selector(f"#{TABELA_CONTRATOS}_processing", state="hidden", timeout=180000)
        console.print("[bold green]✅ Lista carregada com sucesso![/bold green]")
    except Exception:
        console.print("[red]⚠️ Timeout esperando a lista massiva. Continuando mesmo assim...[/red]")

    await asyncio.sleep(3)


async def baixar_termo(page, termo: str, caminho_base: str) -> None:
    pasta_termo = os.path.join(caminho_base, termo)
    os.makedirs(pasta_termo, exist_ok=True)

    arquivos_existentes = {f for f in os.listdir(pasta_termo) if f.lower().endswith(".pdf")}
    campo_arquivo = page.locator(FILTRO_ARQUIVO).first

    if await campo_arquivo.count() and not await campo_arquivo.is_visible():
        await page.click(BOTAO_FILTROS)

    if await campo_arquivo.count():
        await campo_arquivo.fill(termo)
        await campo_arquivo.press("Enter")
    else:
        console.print(f"[red]Campo de busca do arquivo não encontrado para o termo {termo}.[/red]")
        return

    await page.wait_for_selector(f"#{TABELA_CONTRATOS}_processing", state="hidden", timeout=30000)
    await asyncio.sleep(2)
    await carregar_todos_os_registros(page)

    links = await page.query_selector_all('a[onclick*="showSelectedDocument"]')
    total_links = len(links)
    if total_links == 0:
        console.print(f"[bold yellow]Nenhum arquivo encontrado para {termo}.[/bold yellow]")
        return

    item_inicio = 1
    console.print(f"\n[bold cyan]📊 {termo}: encontrados {total_links} itens. Iniciando processamento...[/bold cyan]")

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TaskProgressColumn(), console=console) as progress:
        task = progress.add_task(f"[cyan]Baixando {termo}", total=total_links)
        progress.update(task, completed=item_inicio - 1)

        for idx in range(item_inicio - 1, total_links):
            link = links[idx]
            texto = (await link.inner_text()).strip()
            nome_final = f"{sanitizar_nome(texto)}.pdf"

            if nome_final in arquivos_existentes:
                progress.update(task, advance=1, description=f"[grey50]Pulo: {nome_final[:20]}[/grey50]")
            else:
                try:
                    console.print(f"[dim]⚡ [1/4] Disparando clique no arquivo: {nome_final[:15]}...[/dim]")
                    
                    # Vamos forçar o clique nativo do Playwright. Se falhar, tentamos o via JS.
                    try:
                        await link.click(force=True, timeout=5000)
                    except:
                        await page.evaluate("(el) => el.click()", link)

                    console.print(f"[dim]⚡ [2/4] Caçando o iframe/embed do PDF no DOM...[/dim]")
                    
                    # A MÁGICA AQUI: Não dependemos mais do "#documentView".
                    # Pegamos o último iframe ou embed que aparecer na página.
                    pdf_locator = page.locator("iframe, embed").last
                    
                    # Aguarda a tag existir no HTML, mesmo que invisível
                    await pdf_locator.wait_for(state="attached", timeout=15000)
                    await asyncio.sleep(2)  # Tempo vital para o navegador preencher o atributo 'src'

                    console.print("[dim]🔧 [3/4] Extraindo URL de origem...[/dim]")
                    
                    pdf_src = await pdf_locator.get_attribute("src")

                    if not pdf_src:
                        raise RuntimeError("O visualizador foi encontrado, mas o link (src) estava vazio.")

                    path_local = os.path.join(CAMINHO_TEMPORARIO, nome_final)

                    console.print("[dim]⬇️ [4/4] Executando download silencioso via Fetch...[/dim]")
                    async with page.expect_download(timeout=30000) as dl_info:
                        await page.evaluate("""async ([url, filename]) => {
                            const response = await fetch(url);
                            const blob = await response.blob();
                            const a = document.createElement('a');
                            a.href = URL.createObjectURL(blob);
                            a.download = filename;
                            document.body.appendChild(a);
                            a.click();
                            a.remove();
                        }""", [pdf_src, nome_final])

                    download = await dl_info.value
                    await download.save_as(path_local)

                    shutil.move(path_local, os.path.join(pasta_termo, nome_final))

                    arquivos_existentes.add(nome_final)
                    progress.update(task, advance=1, description=f"[green]Baixado: {nome_final[:20]}[/green]")

                    # Tentativa genérica de fechar o modal pressionando 'Esc' ou clicando fora
                    try:
                        await page.evaluate("document.querySelector('button[class*=\"close\"], button[id*=\"back\"], button[id*=\"Back\"]')?.click()")
                        await page.keyboard.press("Escape")
                        await asyncio.sleep(1)
                    except:
                        pass

                except Exception as e:
                    console.print(f"[bold red]❌ Erro: {str(e)}[/bold red]")
                    progress.update(task, advance=1, description=f"[red]Pulou: {nome_final[:15]}[/red]")
                    await page.keyboard.press("Escape")
                    await asyncio.sleep(1)


async def automate_osinfo():
    ano_alvo, mes_data_value, nome_mes_pasta = solicitar_periodo()
    contrato_alvo = CONTRATO_ALVO
    caminho_final = os.path.join(BASE_Z, f"{nome_mes_pasta}_{ano_alvo}")

    os.makedirs(caminho_final, exist_ok=True)
    os.makedirs(CAMINHO_TEMPORARIO, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)

        ctx_args = {
            "accept_downloads": True,
            "viewport": {"width": 1280, "height": 720},
        }
        if os.path.exists(SESSION_FILE):
            ctx_args["storage_state"] = SESSION_FILE
            console.print("[green]✅ Estado de sessão carregado.[/green]")

        context = await browser.new_context(**ctx_args)
        page = await context.new_page()
        page.set_default_timeout(60000)

        await preparar_contexto(page, ano_alvo, mes_data_value, contrato_alvo)

        for termo in TERMOS_ARQUIVOS:
            console.print(f"\n[bold magenta]🔎 Buscando arquivos com o termo {termo}...[/bold magenta]")
            await baixar_termo(page, termo, caminho_final)

        console.print(f"\n[bold green]🏁 Processo concluído para {nome_mes_pasta}![/bold green]")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(automate_osinfo())