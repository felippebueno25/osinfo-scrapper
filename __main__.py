import asyncio
import os
import shutil
import json
from datetime import datetime
from playwright.async_api import async_playwright

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.panel import Panel

# === CONFIGURAÇÕES ===
SEU_USUARIO = "fbueno"
SUA_SENHA = "310710"
CONTRATO_ALVO = "002/2021-52"
SESSION_FILE = "session_osinfo.json"
CHECKPOINT_FILE = "checkpoint.json"

# Organização de Pastas
BASE_Z = r"E:\PRESTAÇÃO DE CONTAS OS\OSINFO_DESPESAS_DOWNLOADS"
CAMINHO_TEMPORARIO = r"C:\temp_osinfo_stage"

console = Console()

MESES_PT = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
]

def sanitizar_nome(texto: str) -> str:
    return "".join(c for c in texto.strip() if c.isalnum() or c in (" ", "_", "-")).strip()

def solicitar_periodo() -> tuple[str, str, str]:
    ano_atual = datetime.now().year
    while True:
        mes_input = input(f"Mês para baixar (1-12) [4]: ").strip() or "4"
        if mes_input.isdigit() and 1 <= int(mes_input) <= 12:
            mes_num = int(mes_input)
            break
        console.print("[red]Mês inválido.[/red]")

    while True:
        ano_input = input(f"Ano para baixar [2026]: ").strip() or "2026"
        if ano_input.isdigit() and 2000 <= int(ano_input) <= ano_atual + 1:
            ano = ano_input
            break
    
    return ano, str(mes_num - 1), MESES_PT[mes_num - 1]

def carregar_checkpoint(ano, mes, rubrica) -> dict:
    default = {"item_index": 1}
    if not os.path.exists(CHECKPOINT_FILE): return default
    try:
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Ignoramos a page_index agora, pois é tudo na página 1
        if data.get("ano_alvo") == ano and data.get("mes_data_value") == mes and data.get("rubrica_filtro") == rubrica:
            return data
    except: pass
    return default

def salvar_checkpoint(i_idx, ano, mes, rubrica):
    # Salvamos page_index como 1 fixo caso o script volte a usar paginação no futuro
    payload = {
        "ano_alvo": ano, "mes_data_value": mes, "rubrica_filtro": rubrica,
        "despesa_index": 0, "page_index": 1, "item_index": i_idx
    }
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

async def automate_osinfo():
    ano_alvo, mes_data_value, nome_mes_pasta = solicitar_periodo()
    rubrica_filtro = input("Rubrica para filtrar (Enter = todas): ").strip()
    caminho_final = os.path.join(BASE_Z, f"{nome_mes_pasta}_{ano_alvo}")
    
    os.makedirs(caminho_final, exist_ok=True)
    os.makedirs(CAMINHO_TEMPORARIO, exist_ok=True)

    arquivos_existentes = {f for f in os.listdir(caminho_final) if f.lower().endswith(".pdf")}
    checkpoint = carregar_checkpoint(ano_alvo, mes_data_value, rubrica_filtro)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        ctx_args = {
            "accept_downloads": True,
            "viewport": {"width": 1280, "height": 720}
        }
        if os.path.exists(SESSION_FILE):
            ctx_args["storage_state"] = SESSION_FILE
            console.print("[green]✅ Estado de sessão carregado.[/green]")

        context = await browser.new_context(**ctx_args)
        page = await context.new_page()
        page.set_default_timeout(60000) # Aumenta timeout geral para 60s
        
        await page.goto("https://osinfo.prefeitura.rio/pages/application-container.html")

        # --- NAVEGAÇÃO INICIAL ---
        try:
            await page.click("#avisoRH .btn-secondary", timeout=5000)
        except: pass

        await page.click('a[href="#SubMenu2"]')
        await page.wait_for_selector("#Despesa", state="visible")
        await page.click("#Despesa")

        # --- FILTROS ---
        console.print(f"[bold blue]⏳ Configurando filtros para {nome_mes_pasta}/{ano_alvo}...[/bold blue]")
        await page.click("#monthlyExpenses")
        await page.locator("#calendarYear").select_option(ano_alvo)
        await page.click(f'button[data-value="{mes_data_value}"]')
        await asyncio.sleep(3)

        if not await page.locator("#numeroContrato").is_visible():
            await page.click("#expensesTableColumnFilterButton")
        
        await page.fill("#numeroContrato", CONTRATO_ALVO)
        if rubrica_filtro:
            await page.fill("#descricaoDespesa", rubrica_filtro)
        await page.keyboard.press("Enter")
        
        await page.wait_for_selector("#expensesTable_processing", state="hidden", timeout=30000)
        await asyncio.sleep(2)

        # --- O GOLPE MESTRE: MOSTRAR TODOS ---
        console.print("[bold yellow]🚀 Solicitando TODOS os registros ao servidor (-1). Isso pode levar alguns minutos...[/bold yellow]")
        
        # O seletor padrão do DataTables para quantidade é name="[id_da_tabela]_length"
        seletor_quantidade = 'select[name="expensesTable_length"]'
        
        # Injeta o valor -1 e dispara o evento de mudança para forçar o DataTables a atualizar
        await page.evaluate(f"""(sel) => {{
            const dropdown = document.querySelector(sel);
            if (dropdown) {{
                dropdown.value = "-1";
                dropdown.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}
        }}""", seletor_quantidade)

        # Espera MASSIVA: Até 3 minutos para a prefeitura retornar a tabela gigante
        try:
            await page.wait_for_selector("#expensesTable_processing", state="hidden", timeout=180000)
            console.print("[bold green]✅ Lista massiva carregada com sucesso![/bold green]")
        except Exception:
            console.print("[red]⚠️ Timeout esperando a lista massiva. O servidor pode ter engasgado, mas vamos tentar continuar...[/red]")

        await asyncio.sleep(3) # Tempo extra pro DOM renderizar os milhares de nós HTML

        # --- LOOP ÚNICO E CONTÍNUO ---
        links = await page.query_selector_all('a[onclick*="showSelectedDocument"]')
        total_links = len(links)
        
        if total_links == 0:
            console.print("[bold red]❌ Nenhum link encontrado. Verifique os filtros ou se a tabela carregou.[/bold red]")
            await browser.close()
            return

        item_inicio = checkpoint.get("item_index", 1)
        
        console.print(f"\n[bold cyan]📊 Encontrados {total_links} itens no total. Retomando do item {item_inicio}...[/bold cyan]")

        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), 
                        BarColumn(), TaskProgressColumn(), console=console) as progress:
            
            task = progress.add_task("[cyan]Baixando Lote Único", total=total_links)
            progress.update(task, completed=item_inicio-1)

            # Iteramos apenas os itens que faltam, ignorando os do começo
            for idx in range(item_inicio - 1, total_links):
                link = links[idx]
                texto = (await link.inner_text()).strip()
                nome_final = f"{sanitizar_nome(texto)}.pdf"

                if nome_final in arquivos_existentes:
                    progress.update(task, advance=1, description=f"[grey50]Pulo: {nome_final[:20]}[/grey50]")
                else:
                    try:
                        # 1. Clique BRUTO via JavaScript (ignora a lentidão do DOM pesado)
                        await link.evaluate("el => el.click()")
                        
                        # 2. Timeout curto: Se o modal não abrir em 8s, o link tá quebrado
                        await page.wait_for_selector("#documentViewDownloadButton", state="visible", timeout=8000)
                        
                        # 3. Timeout restrito pro download
                        async with page.expect_download(timeout=15000) as dl_info:
                            # Clica no botão de download
                            await page.evaluate("document.querySelector('#documentViewDownloadButton').click()")
                        
                        download = await dl_info.value
                        path_local = os.path.join(CAMINHO_TEMPORARIO, nome_final)
                        await download.save_as(path_local)
                        shutil.move(path_local, os.path.join(caminho_final, nome_final))
                        
                        arquivos_existentes.add(nome_final)
                        progress.update(task, advance=1, description=f"[green]Baixado: {nome_final[:20]}[/green]")
                        
                        # Fecha o modal suavemente
                        await page.evaluate("document.querySelector('#documentViewBackButton')?.click()")
                        await page.wait_for_selector("#documentView", state="hidden", timeout=5000)

                    except Exception as e:
                        # SE DER ERRO OU TRAVAR, ELE CAI AQUI!
                        progress.update(task, advance=1, description=f"[red]Pulou Erro: {nome_final[:15]}[/red]")
                        
                        # Procedimento agressivo de limpeza de tela para não travar o próximo
                        try:
                            await page.evaluate("document.querySelector('#documentViewBackButton')?.click()")
                            await page.keyboard.press("Escape")
                            await page.wait_for_selector("#documentView", state="hidden", timeout=3000)
                        except:
                            pass # Se não fechar, engole o erro e segue em frente
                        
                        await asyncio.sleep(1) # Micro-pausa pro DOM respirar

                # Salva o checkpoint no item atual
                salvar_checkpoint(idx + 2, ano_alvo, mes_data_value, rubrica_filtro)


        console.print(f"\n[bold green]🏁 Processo concluído para {nome_mes_pasta}![/bold green]")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(automate_osinfo())