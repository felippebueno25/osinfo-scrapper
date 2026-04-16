import asyncio
import os
import shutil
import csv
from datetime import datetime
from playwright.async_api import async_playwright

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.panel import Panel

# === CONFIGURAÇÕES ===
SEU_USUARIO = "fbueno"
SUA_SENHA = "310710"
CONTRATO_ALVO = "002/2021-52"
CSV_DESPESAS = "gggg.csv"  
SESSION_FILE = "session_osinfo.json"

# Configuração do Período Alvo
ANO_ALVO = "2026"
MES_DATA_VALUE = "0" # 0=Janeiro, 1=Fevereiro, etc.
NOME_MES_PASTA = "Janeiro" 

# Organização de Pastas
BASE_Z = r"Z:\PRESTAÇÃO DE CONTAS OS\OSINFO_DESPESAS_DOWNLOADS"
CAMINHO_FINAL = os.path.join(BASE_Z, f"{NOME_MES_PASTA}_{ANO_ALVO}")
CAMINHO_TEMPORARIO = r"C:\temp_osinfo_stage"

console = Console()

async def automate_osinfo():
    console.print(Panel.fit(f"[bold cyan]OSINFO BATCH PROCESSOR[/bold cyan]\n[white]Período:[/white] [yellow]{NOME_MES_PASTA}/{ANO_ALVO}[/yellow]\n[white]Dataset:[/white] [green]{CSV_DESPESAS}[/green]", border_style="blue"))

    for caminho in [CAMINHO_FINAL, CAMINHO_TEMPORARIO]:
        os.makedirs(caminho, exist_ok=True)

    lista_despesas = []
    try:
        with open(CSV_DESPESAS, mode='r', encoding='utf-8') as f:
            reader = csv.reader(f)
            lista_despesas = [linha[0] for linha in reader if linha]
        console.print(f"[yellow]✔ {len(lista_despesas)} despesas carregadas do CSV.[/yellow]")
    except Exception as e:
        console.print(f"[bold red]❌ Erro ao ler CSV:[/bold red] {e}")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=200)
        
        if os.path.exists(SESSION_FILE):
            context = await browser.new_context(storage_state=SESSION_FILE, accept_downloads=True)
        else:
            context = await browser.new_context(accept_downloads=True)
            page = await context.new_page()
            await page.goto("https://osinfo.prefeitura.rio/")
            await page.fill('#user', SEU_USUARIO)
            await page.fill('#password', SUA_SENHA)
            await page.click('#signinButton')
            await page.wait_for_load_state("networkidle")
            await context.storage_state(path=SESSION_FILE)

        page = await context.new_page()
        await page.goto("https://osinfo.prefeitura.rio/pages/application-container.html")

        try: await page.click('#avisoRH .btn-secondary', timeout=3000)
        except: pass

        await page.click('a[href="#SubMenu2"]') 
        await page.wait_for_selector('#Despesa', state="visible")
        await page.click('#Despesa') 

        # --- 1. FILTRO DE COMPETÊNCIA ---
        console.print(f"[bold blue]📅 Ajustando período para {NOME_MES_PASTA}/{ANO_ALVO}...[/bold blue]")
        try:
            # NOVIDADE: Abre o menu/popover do calendário primeiro!
            await page.wait_for_selector('#monthlyExpenses', state="visible")
            await page.click('#monthlyExpenses')
            await asyncio.sleep(1) # Aguarda a animação do calendário abrir
            
            # Com o calendário aberto, seleciona o Ano
            await page.locator('#calendarYear').select_option(ANO_ALVO, force=True)
            await asyncio.sleep(1) 
            
            # Clica no botão do Mês
            seletor_botao_mes = f'button[data-value="{MES_DATA_VALUE}"]'
            await page.wait_for_selector(seletor_botao_mes, state="visible")
            await page.click(seletor_botao_mes)
            
            # O clique no mês fecha o calendário e dispara a busca de dados
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(4) 
        except Exception as e:
            console.print(f"[bold red]⚠️ Erro ao mudar o período:[/bold red] {e}")
            # Se der erro, tentamos clicar na tela para fechar o calendário
            await page.keyboard.press("Escape")
        # ---------------------------------------
        
        # --- 2. FILTRO DE CONTRATO (Protegido) ---
        # Verifica se o campo está na tela. Se não estiver, clica no botão de filtro.
        if not await page.locator('#numeroContrato').is_visible():
            await page.wait_for_selector('#expensesTableColumnFilterButton')
            await page.click('#expensesTableColumnFilterButton')
            await asyncio.sleep(1)

        await page.fill('#numeroContrato', CONTRATO_ALVO)
        await page.keyboard.press("Enter")
        await asyncio.sleep(3)

        total_baixado = 0
        
        # --- 3. LOOP DE DESPESAS DO CSV ---
        for despesa_termo in lista_despesas:
            console.print(f"\n[bold magenta]🔎 Filtrando despesa:[/bold magenta] {despesa_termo}")
            
            # Garantia Dupla: Se a tabela recarregou e fechou o filtro, abre de novo
            if not await page.locator('#descricaoDespesa').is_visible():
                await page.click('#expensesTableColumnFilterButton')
                await asyncio.sleep(1)

            await page.fill('#descricaoDespesa', '') 
            await page.fill('#descricaoDespesa', despesa_termo)
            await page.keyboard.press("Enter")
            await asyncio.sleep(4) 

            links = await page.query_selector_all('a[onclick*="showSelectedDocument"]')
            
            if not links:
                console.print(f"[grey50]ℹ Nenhuma linha encontrada para '{despesa_termo}'[/grey50]")
                continue

            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TaskProgressColumn(), console=console) as progress:
                task = progress.add_task(f"[cyan]Baixando...", total=len(links))

                for link in links:
                    texto_link = (await link.inner_text()).strip()
                    nome_limpo = "".join([c for c in texto_link if c.isalnum() or c in (' ', '_', '-')]).strip()
                    nome_final = f"{nome_limpo}.pdf"
                    
                    caminho_z = os.path.join(CAMINHO_FINAL, nome_final)
                    caminho_local = os.path.join(CAMINHO_TEMPORARIO, nome_final)

                    if os.path.exists(caminho_z):
                        progress.update(task, advance=1, description=f"[grey50]⏩ SKIP: {nome_limpo[:20]}...[/grey50]")
                        continue

                    try:
                        await link.click()
                        await page.wait_for_selector('#documentViewDownloadButton', state="visible", timeout=15000)

                        async with page.expect_download(timeout=0) as download_info:
                            await page.click('#documentViewDownloadButton')
                        
                        download = await download_info.value
                        await download.save_as(caminho_local)
                        shutil.move(caminho_local, caminho_z)
                        
                        total_baixado += 1
                        progress.update(task, advance=1, description=f"[green]✅ {nome_limpo[:20]}...[/green]")
                        
                        await page.click('#documentViewBackButton')
                        await page.wait_for_selector('#documentView', state="hidden")
                    except:
                        await page.keyboard.press("Escape")
                        progress.update(task, advance=1)

        console.print(f"\n[bold green]🏁 Processamento concluído! {total_baixado} arquivos gravados em {NOME_MES_PASTA}/{ANO_ALVO}.[/bold green]")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(automate_osinfo())