import asyncio
import os
import shutil
from pathlib import Path
from playwright.async_api import async_playwright

# Bibliotecas para a interface visual
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.panel import Panel
from rich.live import Live

# === CONFIGURAÇÕES GLOBAIS ===
SEU_USUARIO = "fbueno"
SUA_SENHA = "310710"
CONTRATO_ALVO = "002/2021-52"
SESSION_FILE = "session_osinfo.json"

# Caminhos (Utilizando r"" para segurança no Windows)
CAMINHO_FINAL = r"Z:\PRESTAÇÃO DE CONTAS OS\OSINFO_DESPESAS_DOWNLOADS"
CAMINHO_TEMPORARIO = r"C:\temp_osinfo_stage"

console = Console()

async def automate_osinfo():
    console.print(Panel.fit("[bold cyan]OSINFO SCRAPER v3.0[/bold cyan]\n[white]Integrando Deduplicação, Cache Local e Interface Rich[/white]", border_style="blue"))

    # 1. Validação de Diretórios
    for caminho in [CAMINHO_FINAL, CAMINHO_TEMPORARIO]:
        if not os.path.exists(caminho):
            try:
                os.makedirs(caminho)
            except Exception as e:
                console.print(f"[bold red]❌ Erro crítico de acesso:[/bold red] {caminho} - {e}")
                return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=200)
        
        # Gestão de Sessão
        if os.path.exists(SESSION_FILE):
            console.print("[yellow]🔄 Sessão ativa encontrada. Pulando login...[/yellow]")
            context = await browser.new_context(storage_state=SESSION_FILE, accept_downloads=True)
        else:
            console.print("[cyan]🔑 Iniciando nova autenticação...[/cyan]")
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

        # Limpeza de Modais iniciais
        try: await page.click('#avisoRH .btn-secondary', timeout=3000)
        except: pass

        # Navegação e Filtro
        console.print("[bold blue]📂 Navegando para Financeiro > Despesas...[/bold blue]")
        await page.click('a[href="#SubMenu2"]') 
        await page.wait_for_selector('#Despesa', state="visible")
        await page.click('#Despesa') 
        await page.wait_for_selector('#expensesTableColumnFilterButton')
        await page.click('#expensesTableColumnFilterButton')
        await page.fill('#numeroContrato', CONTRATO_ALVO)
        await page.keyboard.press("Enter")
        
        # Expansão da Tabela (1000 registros)
        try:
            await page.select_option('select[name="expensesTable_length"]', '1000')
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(4)
        except: pass

        tem_proxima_pagina = True
        total_novos = 0
        total_pular = 0

        # --- LOOP DE PAGINAÇÃO E DOWNLOADS ---
        while tem_proxima_pagina:
            links = await page.query_selector_all('a[onclick*="showSelectedDocument"]')
            
            # Criando a barra de progresso para a página atual
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=40),
                TaskProgressColumn(),
                TimeRemainingColumn(),
                console=console
            ) as progress:
                
                task_id = progress.add_task(f"[cyan]Processando {len(links)} registros...", total=len(links))

                for link in links:
                    texto_link = (await link.inner_text()).strip()
                    nome_limpo = "".join([c for c in texto_link if c.isalnum() or c in (' ', '_', '-')]).strip()
                    nome_final = f"{nome_limpo}.pdf"
                    
                    caminho_z = os.path.join(CAMINHO_FINAL, nome_final)
                    caminho_local = os.path.join(CAMINHO_TEMPORARIO, nome_final)

                    # Deduplicação
                    if os.path.exists(caminho_z):
                        total_pular += 1
                        progress.update(task_id, advance=1, description=f"[grey50]⏩ SKIP: {nome_limpo[:30]}...[/grey50]")
                        continue

                    try:
                        progress.update(task_id, description=f"[bold green]📥 Baixando: {nome_limpo[:30]}...[/bold green]")
                        await link.click()
                        await page.wait_for_selector('#documentViewDownloadButton', state="visible", timeout=15000)

                        # Download sem limite de tempo (Infinite Timeout)
                        async with page.expect_download(timeout=0) as download_info:
                            await page.click('#documentViewDownloadButton')
                        
                        download = await download_info.value
                        await download.save_as(caminho_local)
                        
                        # Movimentação Local -> Z:
                        shutil.move(caminho_local, caminho_z)
                        
                        total_novos += 1
                        progress.update(task_id, advance=1)

                        await page.click('#documentViewBackButton')
                        await page.wait_for_selector('#documentView', state="hidden")

                    except Exception as e:
                        console.print(f"[bold red]❌ Falha no item {nome_limpo}:[/bold red] {str(e)[:50]}")
                        await page.keyboard.press("Escape")
                        progress.update(task_id, advance=1)

            # Próxima Página
            botao_proximo = await page.query_selector('#expensesTable_paginate li.active + li:not(.disabled) a')
            if botao_proximo:
                console.print("[bold yellow]➡️ Próxima página detectada. Carregando...[/bold yellow]")
                await botao_proximo.click()
                await asyncio.sleep(5)
                await page.wait_for_load_state("networkidle")
            else:
                tem_proxima_pagina = False

        # --- RESUMO FINAL ---
        resumo = Table(title="Resumo da Operação", title_style="bold magenta")
        resumo.add_column("Categoria", style="cyan")
        resumo.add_column("Quantidade", justify="right", style="green")
        resumo.add_row("Novos arquivos no Z:", str(total_novos))
        resumo.add_row("Ignorados (Já existiam):", str(total_pular))
        resumo.add_row("Total processado:", str(total_novos + total_pular))
        
        console.print("\n", resumo)
        console.print("[bold green]🏁 Processo finalizado com sucesso![/bold green]")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(automate_osinfo())