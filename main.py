import asyncio
import os
from playwright.async_api import async_playwright

# Configurações
LOGIN_URL = "https://osinfo.prefeitura.rio/"
SESSION_FILE = "session_osinfo.json"
CONTRATO_ALVO = "002/2021-52"
SEU_USUARIO = "fbueno"
SUA_SENHA = "310710"

async def automate_osinfo():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False) # Mantenha False para validar
        
        # Carrega sessão se existir, senão faz login
        if os.path.exists(SESSION_FILE):
            context = await browser.new_context(storage_state=SESSION_FILE, accept_downloads=True)
        else:
            context = await browser.new_context(accept_downloads=True)
            page = await context.new_page()
            await page.goto(LOGIN_URL)
            await page.fill('#user', SEU_USUARIO)
            await page.fill('#password', SUA_SENHA)
            await page.click('#signinButton')
            await page.wait_for_load_state("networkidle")
            await context.storage_state(path=SESSION_FILE)

        page = await context.new_page()
        await page.goto("https://osinfo.prefeitura.rio/pages/application-container.html")

        # 1. Fechar Modal de Aviso (se aparecer)
        try:
            await page.click('#avisoRH .btn-secondary', timeout=5000)
        except: pass

        # 2. Navegação: Financeiro > Despesas
        print("Navegando nos menus...")
        await page.click('a[href="#SubMenu2"]') # Clica em Financeiro
        await page.wait_for_selector('#Despesa', state="visible")
        await page.click('#Despesa') # Clica em Despesas

        # 3. Ativar Filtro e Inserir Contrato
        print(f"Filtrando pelo contrato: {CONTRATO_ALVO}")
        await page.wait_for_selector('#expensesTableColumnFilterButton')
        await page.click('#expensesTableColumnFilterButton')
        
        await page.wait_for_selector('#numeroContrato')
        await page.fill('#numeroContrato', CONTRATO_ALVO)
        await page.keyboard.press("Enter")
        
        # Aguarda a tabela atualizar (importante para sites dinâmicos)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3) 

        # 4. Capturar e Baixar arquivos via função showSelectedDocument
        print("Iniciando captura de documentos dinâmicos...")

        # Seleciona todos os links na coluna Descrição que chamam a função de documento
        # O seletor a[onclick*="showSelectedDocument"] busca links que contenham esse texto no clique
        links_documentos = await page.query_selector_all('a[onclick*="showSelectedDocument"]')

        textos_processados = set()

        for link in links_documentos:
            # Obtém o nome amigável do arquivo (ex: A2_Aguas_Fevereiro_2026_52)
            nome_exibicao = await link.inner_text()
            nome_exibicao = nome_exibicao.strip()

            if nome_exibicao and nome_exibicao not in textos_processados:
                textos_processados.add(nome_exibicao)
                
                print(f"Preparando download: {nome_exibicao}...")

                try:
                    # O segredo: esperar o evento de download antes de clicar no link com JS
                    async with page.expect_download(timeout=60000) as download_info:
                        await link.click()
                    
                    download = await download_info.value
                    
                    # Sugestão: usar o nome que aparece na tela se o arquivo vier com nome genérico
                    extensao = ".pdf" # Geralmente são PDFs nesse portal
                    final_name = f"{nome_exibicao}{extensao}"
                    
                    save_path = os.path.join("downloads", final_name)
                    await download.save_as(save_path)
                    print(f"✅ Sucesso: {final_name}")
                    
                except Exception as e:
                    print(f"❌ Erro ao baixar {nome_exibicao}: {e}")
                    # Caso o clique abra uma nova aba em vez de baixar direto, 
                    # o Playwright pode exigir um tratamento de 'page.expect_popup()'

if __name__ == "__main__":
    if not os.path.exists("downloads"): os.makedirs("downloads")
    asyncio.run(automate_osinfo())