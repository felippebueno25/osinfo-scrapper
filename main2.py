import asyncio
import os
import shutil
from playwright.async_api import async_playwright

# === CONFIGURAÇÕES ===
SEU_USUARIO = "fbueno"
SUA_SENHA = "310710"
CONTRATO_ALVO = "002/2021-52"
SESSION_FILE = "session_osinfo.json"

# Caminhos de Destino e Cache
CAMINHO_FINAL = r"Z:\PRESTAÇÃO DE CONTAS OS\OSINFO_DESPESAS_DOWNLOADS"
CAMINHO_TEMPORARIO = r"C:\temp_osinfo_stage" # Ponte de segurança

async def automate_osinfo():
    # Validação de Diretórios
    for caminho in [CAMINHO_FINAL, CAMINHO_TEMPORARIO]:
        if not os.path.exists(caminho):
            try:
                os.makedirs(caminho)
                print(f"📁 Pasta verificada/criada: {caminho}")
            except Exception as e:
                print(f"❌ Erro ao acessar {caminho}: {e}")
                return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=300)
        
        # Gestão de Sessão
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

        # 1. Limpeza de Interface
        try: await page.click('#avisoRH .btn-secondary', timeout=5000)
        except: pass

        # 2. Navegação e Filtro
        print("📂 Acessando Despesas...")
        await page.click('a[href="#SubMenu2"]') 
        await page.wait_for_selector('#Despesa', state="visible")
        await page.click('#Despesa') 
        await page.wait_for_selector('#expensesTableColumnFilterButton')
        await page.click('#expensesTableColumnFilterButton')
        await page.fill('#numeroContrato', CONTRATO_ALVO)
        await page.keyboard.press("Enter")
        
        # 3. Ajuste de Volume (1000 linhas)
        try:
            await page.select_option('select[name="expensesTable_length"]', '1000')
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(5)
        except: pass

        # 4. Loop de Paginação e Captura
        tem_proxima_pagina = True
        total_baixado = 0

        while tem_proxima_pagina:
            links = await page.query_selector_all('a[onclick*="showSelectedDocument"]')
            print(f"🔍 Localizados {len(links)} links nesta página.")

            for link in links:
                texto_link = (await link.inner_text()).strip()
                nome_limpo = "".join([c for c in texto_link if c.isalnum() or c in (' ', '_', '-')]).strip()
                nome_final = f"{nome_limpo}.pdf"
                
                caminho_z = os.path.join(CAMINHO_FINAL, nome_final)
                caminho_local = os.path.join(CAMINHO_TEMPORARIO, nome_final)

                # Deduplicação: Verifica se já está no Z:
                if os.path.exists(caminho_z):
                    continue

                try:
                    await link.click()
                    await page.wait_for_selector('#documentViewDownloadButton', state="visible", timeout=15000)

                    # Download sem limite de tempo (Infinite Timeout)
                    async with page.expect_download(timeout=0) as download_info:
                        await page.click('#documentViewDownloadButton')
                    
                    download = await download_info.value
                    
                    # PASSO 1: Salva no C: (Estágio)
                    await download.save_as(caminho_local)
                    
                    # PASSO 2: Move para o Z: (Migração segura)
                    shutil.move(caminho_local, caminho_z)
                    
                    print(f"✅ Sucesso: {nome_final} (Salvo no Drive Z)")
                    total_baixado += 1

                    await page.click('#documentViewBackButton')
                    await page.wait_for_selector('#documentView', state="hidden")

                except Exception as e:
                    print(f"❌ Erro em {nome_limpo}: {e}")
                    await page.keyboard.press("Escape")

            # --- LÓGICA DE PAGINAÇÃO ---
            # Busca o próximo botão numérico após o 'active' ou o botão 'Next'
            # O seletor abaixo foca no item de lista adjacente ao ativo
            botao_proximo = await page.query_selector('#expensesTable_paginate li.active + li:not(.disabled) a')
            
            if botao_proximo:
                print("➡️ Avançando para a próxima página de resultados...")
                await botao_proximo.click()
                await asyncio.sleep(5) # Aguarda renderização da nova página
                await page.wait_for_load_state("networkidle")
            else:
                print("🏁 Todas as páginas foram processadas.")
                tem_proxima_pagina = False

        print(f"\n🚀 Operação finalizada. Total de arquivos no Drive Z: {total_baixado}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(automate_osinfo())