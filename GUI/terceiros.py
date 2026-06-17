import asyncio
import os
import shutil
import re
from datetime import datetime

from playwright.async_api import async_playwright
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

SEU_USUARIO = os.getenv("SEU_USUARIO", "")
SUA_SENHA = os.getenv("SUA_SENHA", "")
CONTRATO_ALVO = "002/2021-52"

SESSION_FILE = "session_osinfo.json"

CAMINHO_TEMPORARIO = r"C:\temp_osinfo_stage"

# Caminhos Base dos Documentos
ANEXOI = r"Z:\PRESTAÇÃO DE CONTAS OS\VIVA RIO\OSINFO - DOCUMENTOS\CONTRATOS DE TERCEIROS\ANEXOS\DESPESAS COMPROMISSADAS - [ANEXO I]"
ANEXOII = r"Z:\PRESTAÇÃO DE CONTAS OS\VIVA RIO\OSINFO - DOCUMENTOS\CONTRATOS DE TERCEIROS\ANEXOS\DESPESAS VENCIDAS E NÃO PAGAS [ANEXO II]"
ANEXOIII = r"Z:\PRESTAÇÃO DE CONTAS OS\VIVA RIO\OSINFO - DOCUMENTOS\CONTRATOS DE TERCEIROS\ANEXOS\DESPESAS PAGAS - [ANEXO III]"
ANEXOIV_IVI = r"Z:\PRESTAÇÃO DE CONTAS OS\VIVA RIO\OSINFO - DOCUMENTOS\CONTRATOS DE TERCEIROS\ANEXOS\DEMONSTRATIVO FINANCEIRO ENTRE CONTRATOS OSINFO [ANEXO IV e IVI]"
ANEXOV_VI = r"Z:\PRESTAÇÃO DE CONTAS OS\VIVA RIO\OSINFO - DOCUMENTOS\CONTRATOS DE TERCEIROS\ANEXOS\DESPESAS RATEADAS OSINFO [ANEXO V e VI]"
ANEXOVII = r"Z:\PRESTAÇÃO DE CONTAS OS\VIVA RIO\OSINFO - DOCUMENTOS\CONTRATOS DE TERCEIROS\ANEXOS\DESPESA DE PESSOAL E PRV- [ANEXO VII]"
ANEXOIX = r"Z:\PRESTAÇÃO DE CONTAS OS\VIVA RIO\OSINFO - DOCUMENTOS\CONTRATOS DE TERCEIROS\ANEXOS\DECLARAÇÃO DE ATENDIMENTO A LGPD [ANEXO IX]"
ANEXOX = r"Z:\PRESTAÇÃO DE CONTAS OS\VIVA RIO\OSINFO - DOCUMENTOS\CONTRATOS DE TERCEIROS\ANEXOS\DECLARAÇÃO ATENDIMENTO CODESP- IN05-2025 [ANEXO X]"
CERTIDOES = r"Z:\PRESTAÇÃO DE CONTAS OS\VIVA RIO\OSINFO - DOCUMENTOS\CONTRATOS DE TERCEIROS\CERTIDOES"
DECLARACOES = r"Z:\PRESTAÇÃO DE CONTAS OS\VIVA RIO\OSINFO - DOCUMENTOS\CONTRATOS DE TERCEIROS\DECLARAÇÕES"
RHOS_RH_PROVISAO = r"Z:\PRESTAÇÃO DE CONTAS OS\VIVA RIO\OSINFO - DOCUMENTOS\CONTRATOS DE TERCEIROS\DEMONSTRATIVO DE PESSOAL CONTRATADO PELA O.S. [RHOS_RH_PROVISAO]"
DESP_FIXAS = r"Z:\PRESTAÇÃO DE CONTAS OS\VIVA RIO\OSINFO - DOCUMENTOS\CONTRATOS DE TERCEIROS\DESPESAS FIXAS"
GUIAPAGAMENTO = r"Z:\PRESTAÇÃO DE CONTAS OS\VIVA RIO\OSINFO - DOCUMENTOS\CONTRATOS DE TERCEIROS\GUIA PGMT PISO ENFERMAGEM"
BLOCOE = r"Z:\PRESTAÇÃO DE CONTAS OS\VIVA RIO\OSINFO - DOCUMENTOS\CONTRATOS DE TERCEIROS\RELATORIO DE ATIVIDADES [BLOCO E]"

MAPEAMENTO_GERAL = [
    (r"ANEXO\s*IV\s*E\s*IVI\b", ANEXOIV_IVI),
    (r"ANEXO\s*V\s*E\s*VI\b", ANEXOV_VI),
    (r"ANEXO\s*III\b", ANEXOIII),
    (r"ANEXO\s*VII\b", ANEXOVII),
    (r"ANEXO\s*IX\b", ANEXOIX),
    (r"ANEXO\s*VI\b", ANEXOV_VI),
    (r"ANEXO\s*IV\b", ANEXOIV_IVI),
    (r"ANEXO\s*V\b", ANEXOV_VI),
    (r"ANEXO\s*II\b", ANEXOII),
    (r"ANEXO\s*X\b", ANEXOX),
    (r"ANEXO\s*I\b", ANEXOI),
    (r"CERTID[OÕ]ES\b", CERTIDOES),
    (r"DECLARA[CÇ][OÕ]ES\b", DECLARACOES),
    (r"RHOS_RH_PROVISAO\b", RHOS_RH_PROVISAO),
    (r"DESP_FIXAS\b", DESP_FIXAS),
    (r"GUIAPAGAMENTO", GUIAPAGAMENTO),
    (r"BLOCO\s*E\b", BLOCOE),
]

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
    if texto.lower().endswith(".pdf"):
        texto = texto[:-4]
    return "".join(c for c in texto.strip() if c.isalnum() or c in (" ", "_", "-")).strip()


def descobrir_pasta_destino(nome_arquivo: str, pasta_padrao: str, ano: str, mes: str) -> str:
    nome_upper = nome_arquivo.upper()
    mes_formatado = str(mes).zfill(2)

    for padrao, caminho_base in MAPEAMENTO_GERAL:
        if re.search(padrao, nome_upper):
            if caminho_base == GUIAPAGAMENTO:
                caminho_final = os.path.join(caminho_base, ano, mes_formatado)
            else:
                caminho_final = os.path.join(caminho_base, ano)
            
            os.makedirs(caminho_final, exist_ok=True)
            return caminho_final
            
    os.makedirs(pasta_padrao, exist_ok=True)
    return pasta_padrao


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

    console.print(f"[bold blue]⏳ Configurando filtros para {ano_alvo}/{mes_data_value}, Contrato: {contrato_alvo}[/bold blue]")
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


async def baixar_termo(page, termo: str, caminho_base: str, ano_alvo: str, mes_alvo: str) -> None:
    pasta_padrao_termo = os.path.join(caminho_base, termo)
    campo_arquivo = page.locator(FILTRO_ARQUIVO).first

    if await campo_arquivo.count() and not await campo_arquivo.is_visible():
        await page.click(BOTAO_FILTROS)

    if await campo_arquivo.count():
        await campo_arquivo.fill(termo)
        await campo_arquivo.press("Enter")
    else:
        console.print(f"[red]Campo de busca não encontrado para {termo}.[/red]")
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
    console.print(f"\n[bold cyan]📊 {termo}: {total_links} itens. Processando...[/bold cyan]")

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TaskProgressColumn(), console=console) as progress:
        task = progress.add_task(f"[cyan]Baixando {termo}", total=total_links)
        progress.update(task, completed=item_inicio - 1)

        for idx in range(item_inicio - 1, total_links):
            link = links[idx]
            texto = (await link.inner_text()).strip()
            nome_final = f"{sanitizar_nome(texto)}.pdf"

            pasta_destino = descobrir_pasta_destino(nome_final, pasta_padrao_termo, ano_alvo, mes_alvo)
            caminho_final_arquivo = os.path.join(pasta_destino, nome_final)

            if os.path.exists(caminho_final_arquivo):
                progress.update(task, advance=1, description=f"[grey50]Já existe: {nome_final[:20]}[/grey50]")
            else:
                try:
                    console.print(f"[dim]⚡ [1/4] Disparando clique: {nome_final[:15]}...[/dim]")
                    try:
                        await link.click(force=True, timeout=5000)
                    except:
                        await page.evaluate("(el) => el.click()", link)

                    console.print(f"[dim]⚡ [2/4] Caçando iframe do PDF...[/dim]")
                    pdf_locator = page.locator("iframe, embed").last
                    await pdf_locator.wait_for(state="attached", timeout=15000)
                    await asyncio.sleep(2)

                    console.print("[dim]🔧 [3/4] Extraindo URL...[/dim]")
                    pdf_src = await pdf_locator.get_attribute("src")
                    if not pdf_src:
                        raise RuntimeError("Link src vazio no iframe.")

                    path_local = os.path.join(CAMINHO_TEMPORARIO, nome_final)

                    console.print("[dim]⬇️ [4/4] Download via Fetch...[/dim]")
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

                    shutil.move(path_local, caminho_final_arquivo)
                    progress.update(task, advance=1, description=f"[green]Baixado: {nome_final[:20]}[/green]")

                    try:
                        await page.evaluate("document.querySelector('button[class*=\"close\"], button[id*=\"back\"], button[id*=\"Back\"]')?.click()")
                        await page.keyboard.press("Escape")
                        await asyncio.sleep(1)
                    except:
                        pass

                except Exception as e:
                    console.print(f"[bold red]❌ Erro: {str(e)}[/bold red]")
                    progress.update(task, advance=1, description=f"[red]Falha: {nome_final[:15]}[/red]")
                    await page.keyboard.press("Escape")
                    await asyncio.sleep(1)


async def automate_osinfo(ano_alvo: str, mes_data_value: str, nome_mes_pasta: str):
    contrato_alvo = CONTRATO_ALVO
    
    # Caminho fallback (rede) para documentos não mapeados
    BASE_Z_FALLBACK = r"Z:\PRESTAÇÃO DE CONTAS OS\VIVA RIO\OSINFO - DOCUMENTOS\CONTRATOS DE TERCEIROS\OUTROS"
    caminho_final = os.path.join(BASE_Z_FALLBACK, f"{nome_mes_pasta}_{ano_alvo}")

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
            await baixar_termo(page, termo, caminho_final, ano_alvo, mes_data_value)

        console.print(f"\n[bold green]🏁 Processo concluído para {nome_mes_pasta}![/bold green]")
        await browser.close()