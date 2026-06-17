import asyncio
import os
import shutil
import re
from datetime import datetime
import sys
import subprocess

import os
from playwright._impl._driver import compute_driver_executable, get_driver_env

from playwright.async_api import async_playwright

MESES_PT = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]

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
    (r"CERTID[OÕ]ES", CERTIDOES),
    (r"DECLARA[CÇ][OÕ]ES", DECLARACOES),
    (r"RHOS_RH_PROVISAO", RHOS_RH_PROVISAO),
    (r"DESP_FIXAS", DESP_FIXAS),
    (r"GUIAPAGAMENTO", GUIAPAGAMENTO),
    (r"BLOCO\s*E", BLOCOE),
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


async def preparar_contexto(page, ano_alvo: str, mes_data_value: str, contrato_alvo: str, log_callback) -> None:
    log_callback("Acessando portal da OSINFO...")
    await page.goto("https://osinfo.prefeitura.rio/pages/application-container.html")

    try:
        await page.click("#avisoRH .btn-secondary", timeout=5000)
    except Exception:
        pass

    log_callback("Navegando pelos menus...")
    await page.click('a[href="#SubMenu2"]')
    await page.click('a[href="#SubSubMenu3"]')
    await page.wait_for_selector("#CtrTerce", state="visible")
    await page.click("#CtrTerce")

    log_callback(f"Configurando filtros: Ano {ano_alvo}, Mês {mes_data_value}, Contrato {contrato_alvo}...")
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


async def carregar_todos_os_registros(page, log_callback) -> None:
    log_callback("Solicitando carga massiva de registros ao servidor...")
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
        log_callback("Lista carregada com sucesso.")
    except Exception:
        log_callback("Aviso: Timeout esperando a lista. Continuando mesmo assim...")

    await asyncio.sleep(3)


async def baixar_termo(page, termo: str, caminho_base: str, ano_alvo: str, mes_alvo: str, log_callback) -> None:
    pasta_padrao_termo = os.path.join(caminho_base, termo)
    campo_arquivo = page.locator(FILTRO_ARQUIVO).first

    if await campo_arquivo.count() and not await campo_arquivo.is_visible():
        await page.click(BOTAO_FILTROS)

    if await campo_arquivo.count():
        await campo_arquivo.fill(termo)
        await campo_arquivo.press("Enter")
    else:
        log_callback(f"ERRO: Campo de busca não encontrado para {termo}.")
        return

    await page.wait_for_selector(f"#{TABELA_CONTRATOS}_processing", state="hidden", timeout=30000)
    await asyncio.sleep(2)
    
    await carregar_todos_os_registros(page, log_callback)

    links = await page.query_selector_all('a[onclick*="showSelectedDocument"]')
    total_links = len(links)
    
    if total_links == 0:
        log_callback(f"\n[Termo: {termo}] - Nenhum arquivo encontrado.")
        return

    log_callback(f"\n[Termo: {termo}] - {total_links} itens encontrados. Processando...")

    for idx in range(total_links):
        link = links[idx]
        texto = (await link.inner_text()).strip()
        nome_final = f"{sanitizar_nome(texto)}.pdf"

        pasta_destino = descobrir_pasta_destino(nome_final, pasta_padrao_termo, ano_alvo, mes_alvo)
        caminho_final_arquivo = os.path.join(pasta_destino, nome_final)

        if os.path.exists(caminho_final_arquivo):
            log_callback(f"  ⏭ Pulo: {nome_final[:40]} (Já existe)")
        else:
            try:
                try:
                    await link.click(force=True, timeout=5000)
                except:
                    await page.evaluate("(el) => el.click()", link)

                pdf_locator = page.locator("iframe, embed").last
                await pdf_locator.wait_for(state="attached", timeout=15000)
                await asyncio.sleep(2)

                pdf_src = await pdf_locator.get_attribute("src")
                if not pdf_src:
                    raise RuntimeError("Link src vazio no iframe.")

                path_local = os.path.join(CAMINHO_TEMPORARIO, nome_final)

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
                
                # Feedback visual de sucesso
                log_callback(f"  ✅ Baixado: {nome_final[:40]}")

                try:
                    await page.evaluate("document.querySelector('button[class*=\"close\"], button[id*=\"back\"], button[id*=\"Back\"]')?.click()")
                    await page.keyboard.press("Escape")
                    await asyncio.sleep(1)
                except:
                    pass

            except Exception as e:
                # Feedback visual de erro
                log_callback(f"  ❌ Erro: Falha ao baixar {nome_final[:30]} ({str(e)})")
                await page.keyboard.press("Escape")
                await asyncio.sleep(1)


async def automate_osinfo(ano_alvo: str, mes_data_value: str, nome_mes_pasta: str, contrato_alvo: str, log_callback):
    # Caminho fallback (rede) para documentos não mapeados
    BASE_Z_FALLBACK = r"Z:\PRESTAÇÃO DE CONTAS OS\VIVA RIO\OSINFO - DOCUMENTOS\CONTRATOS DE TERCEIROS\OUTROS"
    caminho_final = os.path.join(BASE_Z_FALLBACK, f"{nome_mes_pasta}_{ano_alvo}")

    os.makedirs(caminho_final, exist_ok=True)
    os.makedirs(CAMINHO_TEMPORARIO, exist_ok=True)

    # --- NOVO BLOCO: Instalação Automática do Chromium (CORRIGIDO) ---
    log_callback("Verificando motor do navegador (Playwright)...")
    try:
        # Acessa os binários internos do Playwright diretamente, evitando o loop do .exe
        driver_executable, driver_cli = compute_driver_executable()
        env = get_driver_env()
        
        # Flag exclusiva do Windows para impedir travamentos no modo --noconsole
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
        log_callback("O robô tentará rodar mesmo assim, mas pode falhar se for a primeira vez neste PC.")
    
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)

        ctx_args = {
            "accept_downloads": True,
            "viewport": {"width": 1280, "height": 720},
        }
        if os.path.exists(SESSION_FILE):
            ctx_args["storage_state"] = SESSION_FILE
            log_callback("Estado de sessão anterior carregado.")

        context = await browser.new_context(**ctx_args)
        page = await context.new_page()
        page.set_default_timeout(60000)

        await preparar_contexto(page, ano_alvo, mes_data_value, contrato_alvo, log_callback)

        for termo in TERMOS_ARQUIVOS:
            await baixar_termo(page, termo, caminho_final, ano_alvo, mes_data_value, log_callback)

        await browser.close()