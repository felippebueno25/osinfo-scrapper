import asyncio
import os
import shutil
import re
import csv
import sys
import subprocess
import uuid
from datetime import datetime

from playwright._impl._driver import compute_driver_executable, get_driver_env
from playwright.async_api import async_playwright
try:
    from dotenv import load_dotenv
    load_dotenv()
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except Exception:
    pass

MESES_PT = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]

SEU_USUARIO = os.getenv("SEU_USUARIO", "fbueno")
SUA_SENHA = os.getenv("SUA_SENHA", "310710")
CONTRATO_ALVO = os.getenv("CONTRATO_ALVO", "002/2021-52")

SESSION_FILE = "session_osinfo.json"
CAMINHO_TEMPORARIO = r"C:\temp_osinfo_stage"

# Pasta oficial de destino na rede / disco
PASTA_OFICIAL_PADRAO = r"Z:\PRESTAÇÃO DE CONTAS OS\VIVA RIO\CONTRATOS DE TERCEIROS\CONTRATOS - AP 5.2\CONTRATOS NO OSINFO"

CAMINHO_AUTOR = r"C:\Users\CAP52\Downloads\codigo\sei-scrapper\osinfo-scrapper\OSINFO_DOWNLOADS_GERAL"
if os.path.exists(PASTA_OFICIAL_PADRAO):
    BASE_DOWNLOADS_GERAL = PASTA_OFICIAL_PADRAO
elif os.path.exists(r"C:\Users\CAP52\Downloads\codigo\sei-scrapper\osinfo-scrapper"):
    BASE_DOWNLOADS_GERAL = CAMINHO_AUTOR
else:
    BASE_DOWNLOADS_GERAL = os.path.join(os.getcwd(), "OSINFO_DOWNLOADS_GERAL")

TABELA_CONTRATOS = "supplierContractTable"
BOTAO_FILTROS = "#supplierContractTableColumnFilterButton"
FILTRO_MES = 'input.columnSearch[id="3"]'
FILTRO_ANO = 'input.columnSearch[id="4"]'
FILTRO_CONTRATO = 'input.columnSearch[id="7"]'
FILTRO_ARQUIVO = 'input.columnSearch[id="17"]'


def sanitizar_nome(texto: str) -> str:
    """Sanitiza strings para nomes de pastas, removendo caracteres inválidos no Windows."""
    if not texto:
        return ""
    if texto.lower().endswith(".pdf"):
        texto = texto[:-4]
    texto = texto.replace("/", "-").replace("\\", "-")
    sanitizado = re.sub(r'[<>:"|?*]', "", texto).strip()
    sanitizado = re.sub(r'\s+', " ", sanitizado)
    return sanitizado


def sanitizar_nome_arquivo_original(texto: str, fallback: str = "documento.pdf") -> str:
    """Sanitiza o nome original do arquivo preservando a extensão .pdf e removendo caracteres proibidos."""
    if not texto:
        return fallback
    texto = texto.strip().replace("/", "-").replace("\\", "-").replace(":", "-")
    sanitizado = re.sub(r'[<>"|?*]', "", texto).strip()
    sanitizado = re.sub(r'\s+', " ", sanitizado)
    if not sanitizado or sanitizado.lower() == ".pdf":
        return fallback
    if not sanitizado.lower().endswith(".pdf"):
        sanitizado = f"{sanitizado}.pdf"
    return sanitizado


def obter_pasta_mes(pasta_base: str, ano_alvo: str, mes_data_value: str, nome_mes_pasta: str = "") -> str:
    """Localiza ou constrói a pasta do mês no padrão 'XX. Mês Ano' (ex: '08. Agosto 2026') sob pasta_base/ano."""
    pasta_ano = os.path.join(pasta_base, str(ano_alvo))
    mes_2d = str(mes_data_value).zfill(2)
    prefixo_mes = f"{mes_2d}."

    if os.path.exists(pasta_ano):
        try:
            for item in os.listdir(pasta_ano):
                caminho_item = os.path.join(pasta_ano, item)
                if os.path.isdir(caminho_item) and item.strip().startswith(prefixo_mes):
                    return caminho_item
        except Exception:
            pass

    if not nome_mes_pasta:
        mes_idx = int(mes_data_value) - 1
        nome_mes_pasta = MESES_PT[mes_idx] if 0 <= mes_idx < len(MESES_PT) else mes_2d

    nome_pasta_mes = f"{mes_2d}. {nome_mes_pasta} {ano_alvo}"
    return os.path.join(pasta_ano, nome_pasta_mes)



async def preparar_contexto(page, ano_alvo: str, mes_data_value: str, contrato_alvo: str, log_callback) -> None:
    log_callback("Acessando portal da OSINFO...")
    await page.goto("https://osinfo.prefeitura.rio/pages/application-container.html", timeout=90000)

    try:
        await page.click("#avisoRH .btn-secondary", timeout=8000)
    except Exception:
        pass

    log_callback("Navegando pelos menus...")
    await page.click('a[href="#SubMenu2"]')
    await page.click('a[href="#SubSubMenu3"]')
    await page.wait_for_selector("#CtrTerce", state="visible", timeout=60000)
    await page.click("#CtrTerce")

    # Aguarda a tabela estar pronta antes de interagir com o calendário
    await asyncio.sleep(2)

    log_callback(f"Configurando filtros: Ano {ano_alvo}, Mês {mes_data_value}, Contrato {contrato_alvo}...")

    # 1. Calendário Superior (#monthlySupplierContract)
    # NOTA: O portal carrega com o mês/ano da sessão anterior. Para evitar que o mês
    # antigo persista, usamos getData() diretamente via JS com ano e mês corretos,
    # e verificamos em seguida se o widget realmente mudou.
    mes_idx = int(mes_data_value) - 1  # 0-indexed: Janeiro=0, Agosto=7
    nome_mes = MESES_PT[mes_idx]

    try:
        btn_cal = page.locator("#monthlySupplierContract").first
        if await btn_cal.count():
            # Lê o texto atual do botão (estado da sessão anterior)
            texto_atual = (await btn_cal.inner_text()).strip()
            log_callback(f"Calendário atual (sessão anterior): '{texto_atual}'")

            # Usa chamada JS direta a getData() com ano e mês corretos
            # Isso evita a sequência click → select_option → click_mes que pode
            # ser interrompida pelo auto-refresh do portal ao trocar o ano
            log_callback(f"Selecionando mês via JS: getData({mes_idx}, {ano_alvo}, ...)")
            await page.evaluate(
                "([m, a]) => getData(m, parseInt(a), monthlySupplierContract)",
                [mes_idx, ano_alvo]
            )

            # Aguarda a tabela processar
            await asyncio.sleep(2)
            try:
                await page.wait_for_selector(f"#{TABELA_CONTRATOS}_processing", state="hidden", timeout=60000)
            except Exception:
                pass

            # Verificação: confirma que o botão reflete o mês/ano esperados
            texto_novo = (await btn_cal.inner_text()).strip()
            esperado_mes = nome_mes
            if esperado_mes.lower() in texto_novo.lower() and str(ano_alvo) in texto_novo:
                log_callback(f"Calendário confirmado: '{texto_novo}'")
            else:
                log_callback(f"Aviso: Calendário mostra '{texto_novo}', esperado '{nome_mes} {ano_alvo}'. Tentando novamente...")
                # Tentativa 2: abre o picker e clica no botão do mês manualmente
                await btn_cal.click()
                await asyncio.sleep(1)
                ano_select = page.locator("#calendarYear").first
                if await ano_select.count():
                    await ano_select.select_option(str(ano_alvo))
                    await asyncio.sleep(0.5)
                btn_mes = page.locator(f'button[data-value="{mes_idx}"]').first
                if await btn_mes.count() and await btn_mes.is_visible():
                    await btn_mes.click()
                    await asyncio.sleep(2)
                    try:
                        await page.wait_for_selector(f"#{TABELA_CONTRATOS}_processing", state="hidden", timeout=30000)
                    except Exception:
                        pass
                    texto_final = (await btn_cal.inner_text()).strip()
                    log_callback(f"Calendário após retry: '{texto_final}'")
    except Exception as e:
        log_callback(f"Aviso ao interagir com calendário superior: {e}")

    # 2. Filtros de Coluna da Tabela
    # Garante que o painel de filtros está aberto
    try:
        filtros_visiveis = await page.locator(FILTRO_MES).first.is_visible()
        if not filtros_visiveis:
            await page.click(BOTAO_FILTROS)
            await asyncio.sleep(0.5)
    except Exception:
        await page.click(BOTAO_FILTROS)
        await asyncio.sleep(0.5)

    mes_locator = page.locator(FILTRO_MES).first
    ano_locator = page.locator(FILTRO_ANO).first
    contrato_locator = page.locator(FILTRO_CONTRATO).first
    campo_arquivo = page.locator(FILTRO_ARQUIVO).first

    # Limpa todos os campos antes de preencher (evita resíduo da execução anterior)
    for loc in [mes_locator, ano_locator, contrato_locator, campo_arquivo]:
        try:
            if await loc.count():
                await loc.fill("")
        except Exception:
            pass

    if await mes_locator.count():
        await mes_locator.fill(mes_data_value)
    if await ano_locator.count():
        await ano_locator.fill(ano_alvo)
    if contrato_alvo and await contrato_locator.count():
        await contrato_locator.fill(contrato_alvo)
    # Filtro de arquivo fica vazio para trazer todos
    if await campo_arquivo.count():
        await campo_arquivo.fill("")

    await page.keyboard.press("Enter")
    await page.wait_for_selector(f"#{TABELA_CONTRATOS}_processing", state="hidden", timeout=60000)
    await asyncio.sleep(2)


async def carregar_todos_os_registros(page, log_callback) -> None:
    log_callback("Solicitando carga massiva de registros ao servidor (-1)...")
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
        await page.wait_for_selector(f"#{TABELA_CONTRATOS}_processing", state="hidden", timeout=300000)
        log_callback("Lista massiva de registros carregada com sucesso.")
    except Exception:
        log_callback("Aviso: Timeout esperando a lista massiva. Continuando com a lista disponível...")

    await asyncio.sleep(3)


async def tentar_exportar_csv_nativo(page, pasta_destino: str, log_callback) -> str:
    """Tenta clicar no botão nativo de exportar CSV do DataTables."""
    log_callback("Verificando se existe botão nativo de exportação para CSV...")
    
    seletor_csv = "button.buttons-csv, .dt-button.buttons-csv, button:has-text('CSV'), a:has-text('CSV')"
    botao_csv = page.locator(seletor_csv).first

    if await botao_csv.count() and await botao_csv.is_visible():
        try:
            log_callback("Botão CSV nativo encontrado! Iniciando download do CSV...")
            path_csv = os.path.join(pasta_destino, "tabela_osinfo_nativo.csv")
            
            async with page.expect_download(timeout=30000) as dl_info:
                await botao_csv.click()
            
            download = await dl_info.value
            await download.save_as(path_csv)
            log_callback(f"✅ CSV nativo baixado com sucesso: {os.path.basename(path_csv)}")
            return path_csv
        except Exception as e:
            log_callback(f"Aviso: Não foi possível obter o CSV nativo por download ({e}).")

    return ""


async def extrair_registros_dom(page, log_callback) -> list[dict]:
    rows_data = await page.evaluate(
        """(tabela_id) => {
            let dataRows = [];
            try {
                if (window.$ && $.fn && $.fn.DataTable) {
                    const dt = $(`#${tabela_id}`).DataTable();
                    const rawRows = dt.rows({ search: 'applied' }).data().toArray();
                    
                    // Filtra apenas registros reais que possuem o HTML do link da imagem do contrato
                    const validRows = rawRows.filter(r => r.imagem_contrato && r.imagem_contrato.includes('<a'));

                    dataRows = validRows.map((r, index) => {
                        const tempDiv = document.createElement('div');
                        tempDiv.innerHTML = r.imagem_contrato || '';
                        const linkEl = tempDiv.querySelector('a');
                        const linkText = linkEl ? linkEl.innerText.trim() : '';

                        return {
                            linha: index + 1,
                            mes: r.ref_mes ? String(r.ref_mes) : '',
                            ano: r.ref_ano ? String(r.ref_ano) : '',
                            nome: r.razao_social || r.companyName || '',
                            servico: r.servico || '',
                            texto_link: linkText,
                            tem_link: !!linkEl
                        };
                    });
                }
            } catch (e) {
                console.error("DataTables API error:", e);
            }

            if (dataRows.length > 0) return dataRows;

            // Fallback caso a API do DataTables não retorne dados
            const table = document.querySelector(`#${tabela_id}`);
            if (!table) return [];

            const thElements = Array.from(table.querySelectorAll('thead tr:first-child th'));
            const headerTexts = thElements.map(th => {
                const titleSpan = th.querySelector('.columnHeaderTitle');
                return titleSpan ? titleSpan.innerText.trim() : th.innerText.trim();
            });

            const tbody = table.querySelector('tbody');
            if (!tbody) return [];

            const rows = Array.from(tbody.querySelectorAll('tr')).filter(tr => !tr.querySelector('.dataTables_empty'));
            return rows.map((tr, index) => {
                const tds = Array.from(tr.querySelectorAll('td'));

                let mes = '';
                let ano = '';
                let nome = '';
                let servico = '';

                tds.forEach((td, i) => {
                    const rawHeader = headerTexts[i] || '';
                    const hText = rawHeader.toLowerCase().normalize("NFD").replace(/[\\u0300-\\u036f]/g, "").trim();
                    const val = td.innerText ? td.innerText.trim() : '';

                    if (hText === 'mes') {
                        mes = val;
                    } else if (hText === 'ano') {
                        ano = val;
                    } else if (hText.includes('nome') && !hText.includes('arquivo')) {
                        nome = val;
                    } else if (hText.includes('servico')) {
                        servico = val;
                    }
                });

                const linkEl = tr.querySelector('a[onclick*="showSelectedDocument"]');
                const linkText = linkEl ? linkEl.innerText.trim() : '';

                return {
                    linha: index + 1,
                    mes: mes,
                    ano: ano,
                    nome: nome,
                    servico: servico,
                    texto_link: linkText,
                    tem_link: !!linkEl
                };
            });
        }""",
        TABELA_CONTRATOS,
    )

    log_callback(f"✅ Tabela lida com sucesso: {len(rows_data)} registros válidos identificados com Nome e Serviço.")
    return rows_data


async def fechar_modal_documento(page) -> None:
    """Garante o fechamento do modal de documento (#supplierContractDocumentView) e limpa backdrops."""
    try:
        await page.evaluate("""() => {
            const btnBack = document.querySelector('#supplierContractDocumentViewBackButton') ||
                            document.querySelector('#supplierContractDocumentView button.close') ||
                            document.querySelector('#supplierContractDocumentView .btn');
            if (btnBack) btnBack.click();

            if (window.$ && $('#supplierContractDocumentView').modal) {
                try { $('#supplierContractDocumentView').modal('hide'); } catch(e){}
            }

            document.querySelectorAll('.modal-backdrop').forEach(el => el.remove());
            document.body.classList.remove('modal-open');
        }""")
        await page.keyboard.press("Escape")
        await asyncio.sleep(1)
    except Exception:
        pass


async def baixar_todos_arquivos_unicos(page, pasta_base: str, ano_alvo: str, mes_data_value: str, nome_mes_pasta: str, log_callback, abort_event=None) -> None:
    # 1. Carrega todos os registros (-1)
    await carregar_todos_os_registros(page, log_callback)

    # 2. Resolve a pasta do mês no padrão 'XX. Mês Ano' (ex: '08. Agosto 2026')
    pasta_destino_padrao = obter_pasta_mes(pasta_base, ano_alvo, mes_data_value, nome_mes_pasta)
    os.makedirs(pasta_destino_padrao, exist_ok=True)
    log_callback(f"📁 Pasta de destino para o período: '{pasta_destino_padrao}'")

    # 3. Tenta exportar o CSV nativo (para auditoria)
    await tentar_exportar_csv_nativo(page, pasta_destino_padrao, log_callback)

    # 4. Extrai dados das colunas com retentativa automática caso o AJAX do DataTables esteja lento
    max_tentativas = 4
    rows_dom = []
    links = []

    for tentativa in range(1, max_tentativas + 1):
        rows_dom = await extrair_registros_dom(page, log_callback)
        links = await page.query_selector_all('a[onclick*="showSelectedDocument"]')

        if len(links) > 0 and len(rows_dom) > 0:
            break

        if tentativa < max_tentativas:
            log_callback(f"⏳ Resposta do OSINFO pendente... Aguardando sincronização (tentativa {tentativa}/{max_tentativas})...")
            try:
                await page.wait_for_selector(f"#{TABELA_CONTRATOS}_processing", state="hidden", timeout=10000)
            except Exception:
                pass
            await asyncio.sleep(3)

    total_links_dom = len(links)

    if total_links_dom == 0:
        log_callback("Nenhum arquivo encontrado para o filtro informado.")
        return

    log_callback(f"\n📊 Total de links encontrados na tabela: {total_links_dom}")

    # 6. Processa cada item criando uma pasta para o fornecedor com a nomenclatura adotada: Nome (Serviço)
    # e preservando o nome original do arquivo (OS_264_...pdf)
    vistos = set()
    itens_unicos = []

    for idx, item in enumerate(rows_dom):
        if idx >= total_links_dom:
            break

        link = links[idx]

        # Sanitização de ano e mês
        raw_ano = re.sub(r'\D', '', str(item.get("ano", "")))
        ano_item = raw_ano if len(raw_ano) == 4 else ano_alvo

        raw_mes = re.sub(r'\D', '', str(item.get("mes", "")))
        mes_item = raw_mes if raw_mes and 1 <= int(raw_mes) <= 12 else mes_data_value
        mes_2d = str(mes_item).zfill(2)

        nome_bruto = item.get("nome", "").strip()
        servico_bruto = item.get("servico", "").strip()
        texto_link = item.get("texto_link", "").strip()

        nome_limpo = sanitizar_nome(nome_bruto)
        servico_limpo = sanitizar_nome(servico_bruto)

        if nome_limpo and servico_limpo:
            nome_pasta_fornecedor = f"{nome_limpo} ({servico_limpo})"
        elif nome_limpo:
            nome_pasta_fornecedor = nome_limpo
        elif servico_limpo:
            nome_pasta_fornecedor = servico_limpo
        else:
            nome_pasta_fornecedor = sanitizar_nome(texto_link) or f"documento_{idx+1}"

        nome_arquivo_original = sanitizar_nome_arquivo_original(texto_link, fallback=f"documento_{idx+1}.pdf")

        # Define a pasta do fornecedor dentro da pasta do mês
        pasta_fornecedor = os.path.join(pasta_destino_padrao, nome_pasta_fornecedor)

        # Desduplica por (pasta_fornecedor, nome_arquivo_original)
        # Permitindo que múltiplos documentos distintos do mesmo fornecedor sejam baixados para a mesma pasta
        chave_unica = (pasta_fornecedor.lower(), nome_arquivo_original.lower())

        if chave_unica not in vistos:
            vistos.add(chave_unica)
            itens_unicos.append({
                "index": idx + 1,
                "link": link,
                "ano": ano_item,
                "mes": mes_2d,
                "nome": nome_bruto,
                "servico": servico_bruto,
                "pasta_fornecedor_nome": nome_pasta_fornecedor,
                "pasta_destino": pasta_fornecedor,
                "nome_arquivo_original": nome_arquivo_original
            })

    total_unicos = len(itens_unicos)
    log_callback(f"🔎 Filtragem concluída: {total_unicos} arquivos únicos identificados de {total_links_dom} registros.")

    # 7. Salva a relação desduplicada em CSV para auditoria
    path_csv_unicos = os.path.join(pasta_destino_padrao, "lista_arquivos_unicos.csv")
    with open(path_csv_unicos, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Index", "Ano", "Mes", "Nome_Empresa", "Servico", "Pasta_Fornecedor", "Nome_Arquivo_Original"])
        for u in itens_unicos:
            writer.writerow([
                u["index"],
                u["ano"],
                u["mes"],
                u["nome"],
                u["servico"],
                u["pasta_fornecedor_nome"],
                u["nome_arquivo_original"]
            ])

    log_callback(f"📄 Relação de arquivos únicos salva em '{path_csv_unicos}'.\n")

    # 8. Download Sequencial dos Arquivos Únicos
    temp_run_dir = os.path.join(CAMINHO_TEMPORARIO, uuid.uuid4().hex)
    os.makedirs(temp_run_dir, exist_ok=True)

    for idx, u in enumerate(itens_unicos, 1):
        # Verifica abortar antes de cada download
        if abort_event is not None and abort_event.is_set():
            log_callback(f"\n⛔ Execução abortada pelo usuário após {idx - 1}/{total_unicos} arquivos.")
            return

        nome_arquivo = u["nome_arquivo_original"]
        pasta = u["pasta_destino"]
        link = u["link"]
        os.makedirs(pasta, exist_ok=True)

        caminho_final_arquivo = os.path.join(pasta, nome_arquivo)

        # Pula se o arquivo já existir na pasta com conteúdo (> 0 bytes)
        if os.path.exists(caminho_final_arquivo) and os.path.getsize(caminho_final_arquivo) > 0:
            log_callback(f"[{idx}/{total_unicos}] ⏭ Pulo: {u['pasta_fornecedor_nome'][:35]} / {nome_arquivo[:30]} (Já existe)")
        else:
            try:
                log_callback(f"[{idx}/{total_unicos}] ⬇️ Baixando: {u['pasta_fornecedor_nome'][:35]} -> {nome_arquivo[:30]}")

                try:
                    await link.click(force=True, timeout=10000)
                except Exception:
                    await page.evaluate("(el) => el.click()", link)

                pdf_locator = page.locator("iframe, embed").last
                await pdf_locator.wait_for(state="attached", timeout=30000)
                await asyncio.sleep(2)

                pdf_src = await pdf_locator.get_attribute("src")
                if not pdf_src:
                    raise RuntimeError("Link src vazio no iframe do documento.")

                path_local = os.path.join(temp_run_dir, nome_arquivo)

                async with page.expect_download(timeout=60000) as dl_info:
                    await page.evaluate("""async ([url, filename]) => {
                        const response = await fetch(url);
                        const blob = await response.blob();
                        const a = document.createElement('a');
                        a.href = URL.createObjectURL(blob);
                        a.download = filename;
                        document.body.appendChild(a);
                        a.click();
                        a.remove();
                    }""", [pdf_src, nome_arquivo])

                download = await dl_info.value
                await download.save_as(path_local)

                shutil.move(path_local, caminho_final_arquivo)
                log_callback(f"[{idx}/{total_unicos}] ✅ Salvo: {u['pasta_fornecedor_nome'][:30]} / {nome_arquivo[:30]}")

            except Exception as e:
                log_callback(f"[{idx}/{total_unicos}] ❌ Erro ao baixar {nome_arquivo[:30]}: {e}")
            finally:
                # Garante que o modal de visualização do documento seja SEMPRE fechado
                await fechar_modal_documento(page)


def obter_caminho_session() -> str:
    """Procura session_osinfo.json no diretório atual, no _MEIPASS do PyInstaller ou nas pastas do projeto."""
    candidatos = [
        os.path.join(os.getcwd(), "session_osinfo.json"),
        os.path.join(getattr(sys, '_MEIPASS', ''), "session_osinfo.json"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "session_osinfo.json"),
        r"C:\Users\CAP52\Downloads\codigo\sei-scrapper\osinfo-scrapper\session_osinfo.json",
        r"C:\Users\CAP52\Downloads\codigo\sei-scrapper\osinfo-scrapper\GUI_Geral\session_osinfo.json"
    ]
    for c in candidatos:
        if c and os.path.exists(c):
            return c
    return "session_osinfo.json"


async def automate_osinfo(
    ano_alvo: str,
    mes_data_value: str,
    nome_mes_pasta: str,
    contrato_alvo: str,
    log_callback,
    pasta_base: str = PASTA_OFICIAL_PADRAO,
    headless: bool = True,
    abort_event=None,
):
    """Executa o robô OSINFO. Caso abort_event (threading.Event) seja sinalizado, encerra a execução."""

    def checar_abort():
        if abort_event is not None and abort_event.is_set():
            raise InterruptedError("Execução abortada pelo usuário.")

    # Limpa o diretório temporário antes de cada execução para evitar
    # que arquivos de execuções anteriores causem movimentação errada
    if os.path.exists(CAMINHO_TEMPORARIO):
        shutil.rmtree(CAMINHO_TEMPORARIO, ignore_errors=True)
    os.makedirs(CAMINHO_TEMPORARIO, exist_ok=True)

    checar_abort()

    log_callback("Verificando motor do navegador (Playwright)...")
    try:
        caminho_navegadores = os.path.join(os.path.expanduser("~"), "AppData", "Local", "ms-playwright")
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = caminho_navegadores

        driver_executable, driver_cli = compute_driver_executable()
        env = get_driver_env()
        env["PLAYWRIGHT_BROWSERS_PATH"] = caminho_navegadores

        creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

        subprocess.check_call(
            [driver_executable, driver_cli, "install", "chromium"],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags
        )
        log_callback("Motor do navegador pronto.")
    except Exception as e:
        log_callback(f"Aviso: Houve uma falha ao verificar/instalar o motor: {e}")

    checar_abort()

    async with async_playwright() as p:
        modo_txt = "oculto (headless)" if headless else "visível (janela aberta)"
        log_callback(f"Iniciando navegador em modo {modo_txt}...")
        browser = await p.chromium.launch(headless=headless)

        ctx_args = {
            "accept_downloads": True,
            "viewport": {"width": 1280, "height": 720},
        }

        session_path = obter_caminho_session()
        if os.path.exists(session_path):
            ctx_args["storage_state"] = session_path
            log_callback(f"Estado de sessão anterior carregado de '{os.path.basename(session_path)}'.")
        else:
            log_callback("Aviso: session_osinfo.json não encontrado.")

        context = await browser.new_context(**ctx_args)
        page = await context.new_page()
        page.set_default_timeout(120000)

        try:
            checar_abort()
            await preparar_contexto(page, ano_alvo, mes_data_value, contrato_alvo, log_callback)
            checar_abort()
            await baixar_todos_arquivos_unicos(
                page, pasta_base, ano_alvo, mes_data_value, nome_mes_pasta, log_callback,
                abort_event=abort_event
            )
        except InterruptedError as e:
            log_callback(f"\n⛔ {e}")
        finally:
            await browser.close()

