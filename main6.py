import asyncio
import os
import shutil
import csv
import json
import time
from datetime import datetime
from playwright.async_api import async_playwright

# === CONFIG ===
CONTRATO_ALVO = "002/2021-52"
CSV_DESPESAS = "gggg.csv"
SESSION_FILE = "session_osinfo.json"
CHECKPOINT_FILE = "checkpoint.json"

ANO_ALVO = "2026"
MES_DATA_VALUE = "2"

BASE_Z = r"Z:\PRESTAÇÃO DE CONTAS OS\OSINFO_DESPESAS_DOWNLOADS"
CAMINHO_FINAL = os.path.join(BASE_Z, "Março_2026")
CAMINHO_TEMP = r"C:\temp_osinfo_stage"


# === LOG ===
def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


# === CHECKPOINT ===
def salvar_checkpoint(indice):
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump({"indice": indice}, f)


def carregar_checkpoint():
    if not os.path.exists(CHECKPOINT_FILE):
        return 0
    with open(CHECKPOINT_FILE) as f:
        return json.load(f).get("indice", 0)


# === HEALTH CHECK ===
async def pagina_viva(page):
    try:
        await page.evaluate("1+1")
        return True
    except:
        return False


# === RECOVERY ===
async def recuperar(page):
    log("💀 Página travou — recuperando...")
    await page.screenshot(path="erro.png")

    await page.reload()
    await page.wait_for_load_state("domcontentloaded")

    await page.click('a[href="#SubMenu2"]')
    await page.wait_for_selector('#Despesa')

    await clicar_despesas(page)
    await selecionar_periodo(page)

    return page


# === CLICK DESPESAS RESILIENTE ===
async def clicar_despesas(page):
    for i in range(5):
        try:
            log(f"➡️ Abrindo Despesas ({i+1})")
            await page.click('#Despesa', timeout=30000)
            await page.wait_for_selector('#monthlyExpenses', timeout=60000)
            return
        except:
            if not await pagina_viva(page):
                page = await recuperar(page)
            await asyncio.sleep(3)
    raise Exception("Falha ao abrir Despesas")


# === PERÍODO ===
async def selecionar_periodo(page):
    await page.wait_for_selector('#monthlyExpenses', timeout=120000)
    await page.click('#monthlyExpenses')

    await page.wait_for_selector('#calendarYear')
    await page.locator('#calendarYear').select_option(ANO_ALVO)

    await page.click(f'button[data-value="{MES_DATA_VALUE}"]')

    await page.wait_for_load_state("networkidle")


# === ESPERA ROBUSTA ===
async def esperar_tabela(page):
    inicio = time.time()

    while True:
        try:
            await page.wait_for_selector('a[onclick*="showSelectedDocument"]', timeout=30000)
            return
        except:
            if time.time() - inicio > 180:
                raise Exception("Timeout tabela")
            log("⏳ aguardando tabela...")
            await asyncio.sleep(3)


# === MAIN ===
async def automate():
    os.makedirs(CAMINHO_FINAL, exist_ok=True)
    os.makedirs(CAMINHO_TEMP, exist_ok=True)

    with open(CSV_DESPESAS, encoding='utf-8') as f:
        lista = [row[0] for row in csv.reader(f) if row]

    start_index = carregar_checkpoint()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-gpu",
                "--disable-dev-shm-usage"
            ]
        )

        context = await browser.new_context(
            storage_state=SESSION_FILE,
            accept_downloads=True,
            viewport={'width': 1920, 'height': 1080}
        )

        page = await context.new_page()
        page.set_default_timeout(120000)

        await page.goto("https://osinfo.prefeitura.rio/pages/application-container.html")

        try:
            await page.click('#avisoRH .btn-secondary', timeout=3000)
        except:
            pass

        await page.click('a[href="#SubMenu2"]')
        await clicar_despesas(page)
        await selecionar_periodo(page)

        await esperar_tabela(page)

        total = 0

        for idx, termo in enumerate(lista[start_index:], start=start_index):
            salvar_checkpoint(idx)

            for tentativa in range(3):
                try:
                    log(f"🔎 {termo}")

                    await page.fill('#descricaoDespesa', '')
                    await page.fill('#descricaoDespesa', termo)
                    await page.keyboard.press("Enter")

                    await esperar_tabela(page)

                    links = await page.query_selector_all('a[onclick*="showSelectedDocument"]')

                    for link in links:
                        nome = (await link.inner_text()).strip()
                        nome = "".join(c for c in nome if c.isalnum() or c in (' ', '_', '-')) + ".pdf"

                        destino = os.path.join(CAMINHO_FINAL, nome)
                        temp = os.path.join(CAMINHO_TEMP, nome)

                        if os.path.exists(destino):
                            continue

                        await link.click()

                        async with page.expect_download(timeout=0) as d:
                            await page.click('#documentViewDownloadButton')

                        download = await d.value
                        await download.save_as(temp)
                        shutil.move(temp, destino)

                        total += 1
                        log(f"✅ {nome}")

                        await page.click('#documentViewBackButton')

                    break

                except Exception as e:
                    log(f"⚠ erro: {e}")

                    if not await pagina_viva(page):
                        page = await recuperar(page)

                    await asyncio.sleep(3)

        log(f"🏁 FINALIZADO: {total} arquivos")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(automate())