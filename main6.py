import asyncio
import os
import shutil
import csv
from playwright.async_api import async_playwright

# === CONFIG ===
SEU_USUARIO = "fbueno"
SUA_SENHA = "310710"
CONTRATO_ALVO = "002/2021-52"
CSV_DESPESAS = "rubricas.csv"
SESSION_FILE = "session_osinfo.json"

ANO_ALVO = "2026"
MES_DATA_VALUE = "2"
NOME_MES_PASTA = "Março"

BASE_Z = r"E:\PRESTAÇÃO DE CONTAS OS\OSINFO_DESPESAS_DOWNLOADS"
CAMINHO_FINAL = os.path.join(BASE_Z, f"{NOME_MES_PASTA}_{ANO_ALVO}")
CAMINHO_TEMP = r"C:\temp_osinfo_stage"


# === HELPERS ===

async def garantir_filtro_visivel(page, campo_selector, botao_selector):
    campo = page.locator(campo_selector)
    botao = page.locator(botao_selector)

    if await campo.is_visible():
        return

    if await botao.count() > 0:
        await botao.click()
        await campo.wait_for(state="visible", timeout=5000)
        return

    raise Exception(f"Filtro não encontrado: {campo_selector}")


async def esperar_tabela(page):
    await page.wait_for_selector('#expensesTable', timeout=20000)
    await page.wait_for_selector('#expensesTable tbody tr', timeout=20000)


# === MAIN ===

async def automate_osinfo():
    os.makedirs(CAMINHO_FINAL, exist_ok=True)
    os.makedirs(CAMINHO_TEMP, exist_ok=True)

    # carregar CSV
    with open(CSV_DESPESAS, encoding='utf-8') as f:
        lista = [row[0] for row in csv.reader(f) if row]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)

        if os.path.exists(SESSION_FILE):
            context = await browser.new_context(
                storage_state=SESSION_FILE,
                accept_downloads=True,
                viewport={'width': 1920, 'height': 1080}
            )
        else:
            context = await browser.new_context(
                accept_downloads=True,
                viewport={'width': 1920, 'height': 1080}
            )

        page = await context.new_page()

        # --- NAVEGAÇÃO ---
        await page.goto("https://osinfo.prefeitura.rio/pages/application-container.html")

        try:
            await page.click('#avisoRH .btn-secondary', timeout=3000)
        except:
            pass

        await page.click('a[href="#SubMenu2"]')
        await page.wait_for_selector('#Despesa', timeout=15000)
        await page.click('#Despesa')

        await esperar_tabela(page)

        # --- PERÍODO ---
        await page.click('#monthlyExpenses')
        await page.wait_for_selector('#calendarYear')

        await page.locator('#calendarYear').select_option(ANO_ALVO)

        seletor_mes = f'button[data-value="{MES_DATA_VALUE}"]'
        await page.click(seletor_mes)

        await page.wait_for_load_state("networkidle")
        await esperar_tabela(page)

        # --- CONTRATO ---
        await garantir_filtro_visivel(
            page,
            '#numeroContrato',
            '#expensesTableColumnFilterButton'
        )

        await page.fill('#numeroContrato', CONTRATO_ALVO)
        await page.keyboard.press("Enter")

        await page.wait_for_load_state("networkidle")
        await esperar_tabela(page)

        total = 0

        # --- LOOP CSV ---
        for termo in lista:
            print(f"\n🔎 {termo}")

            await garantir_filtro_visivel(
                page,
                '#descricaoDespesa',
                '#expensesTableColumnFilterButton'
            )

            await page.fill('#descricaoDespesa', '')
            await page.fill('#descricaoDespesa', termo)
            await page.keyboard.press("Enter")

            await page.wait_for_load_state("networkidle")
            await esperar_tabela(page)

            while True:
                links = await page.query_selector_all('a[onclick*="showSelectedDocument"]')

                if not links:
                    break

                for link in links:
                    nome = (await link.inner_text()).strip()
                    nome = "".join(c for c in nome if c.isalnum() or c in (' ', '_', '-'))
                    nome += ".pdf"

                    destino = os.path.join(CAMINHO_FINAL, nome)
                    temp = os.path.join(CAMINHO_TEMP, nome)

                    if os.path.exists(destino):
                        continue

                    try:
                        await link.click()

                        await page.wait_for_selector(
                            '#documentViewDownloadButton',
                            timeout=15000
                        )

                        async with page.expect_download() as d:
                            await page.click('#documentViewDownloadButton')

                        download = await d.value
                        await download.save_as(temp)
                        shutil.move(temp, destino)

                        total += 1
                        print(f"✅ {nome}")

                        await page.click('#documentViewBackButton')
                        await page.wait_for_selector('#documentView', state="hidden")

                    except Exception as e:
                        print(f"⚠ erro: {e}")
                        await page.keyboard.press("Escape")

                # paginação
                next_btn = await page.query_selector(
                    '#expensesTable_paginate li.active + li:not(.disabled) a'
                )

                if next_btn:
                    await next_btn.click()
                    await page.wait_for_load_state("networkidle")
                    await esperar_tabela(page)
                else:
                    break

        print(f"\n🏁 FINALIZADO: {total} arquivos baixados")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(automate_osinfo())