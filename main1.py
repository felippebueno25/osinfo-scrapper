import asyncio
import os
from playwright.async_api import async_playwright

# === CONFIGURAÇÕES TÉCNICAS E CREDENCIAIS ===
SEU_USUARIO = "fbueno"
SUA_SENHA = "310710"
CONTRATO_ALVO = "002/2021-52"
SESSION_FILE = "session_osinfo.json"

# Caminho absoluto para o seu Drive de Rede (Z:)
# O 'r' antes das aspas é vital para o Windows aceitar as barras invertidas
CAMINHO_DESTINO = r"Z:\PRESTAÇÃO DE CONTAS OS\OSINFO_DESPESAS_DOWNLOADS"

async def automate_osinfo():
    # Validação do Drive Z:
    if not os.path.exists(r"Z:"):
        print("❌ ERRO: Drive Z: não detectado. Mapeie a rede antes de rodar o script.")
        return

    # Garante a existência da pasta de destino
    if not os.path.exists(CAMINHO_DESTINO):
        os.makedirs(CAMINHO_DESTINO)
        print(f"📁 Pasta de destino verificada/criada em: {CAMINHO_DESTINO}")

    async with async_playwright() as p:
        # Lançamento do navegador (headless=False para acompanhamento visual)
        browser = await p.chromium.launch(headless=False, slow_mo=500)
        
        # Gestão de Sessão: Tenta carregar cookies anteriores para evitar logins repetitivos
        if os.path.exists(SESSION_FILE):
            print("🔄 Carregando sessão existente...")
            context = await browser.new_context(storage_state=SESSION_FILE, accept_downloads=True)
        else:
            print("🔑 Realizando login inicial...")
            context = await browser.new_context(accept_downloads=True)
            page = await context.new_page()
            await page.goto("https://osinfo.prefeitura.rio/")
            await page.fill('#user', SEU_USUARIO)
            await page.fill('#password', SUA_SENHA)
            await page.click('#signinButton')
            await page.wait_for_load_state("networkidle")
            # Salva o estado para as próximas execuções
            await context.storage_state(path=SESSION_FILE)

        # Início da navegação interna
        page = await context.new_page()
        await page.goto("https://osinfo.prefeitura.rio/pages/application-container.html")

        # 1. Fechar Modal de Aviso (Aviso RH)
        try:
            await page.click('#avisoRH .btn-secondary', timeout=5000)
            print("✅ Modal de aviso fechado.")
        except: 
            pass

        # 2. Navegação nos Menus (Financeiro > Despesas)
        print("📂 Navegando para Financeiro > Despesas...")
        await page.click('a[href="#SubMenu2"]') # Menu Financeiro
        await page.wait_for_selector('#Despesa', state="visible")
        await page.click('#Despesa') # Submenu Despesas

        # 3. Filtragem e Ajuste de Linhas por Página
        print(f"🔍 Filtrando contrato: {CONTRATO_ALVO}")
        await page.wait_for_selector('#expensesTableColumnFilterButton')
        await page.click('#expensesTableColumnFilterButton')
        await page.fill('#numeroContrato', CONTRATO_ALVO)
        await page.keyboard.press("Enter")
        
        # AGORA O PULO DO GATO: Mudar para 1000 linhas ou "Todos"
        print("📊 Expandindo a visualização para 1000 linhas por página...")
        try:
            # Seleciona o dropdown de quantidade de linhas
            # '1000' é mais seguro que '-1', mas se quiser tentar tudo, use '-1'
            await page.select_option('select[name="expensesTable_length"]', '1000') 
            
            # Aguarda o carregamento massivo (aumentamos o tempo aqui)
            print("⏳ Aguardando renderização da tabela expandida...")
            await page.wait_for_load_state("networkidle", timeout=90000)
            await asyncio.sleep(5) # Delay extra para o JavaScript processar as 1000 linhas
        except Exception as e:
            print(f"⚠️ Erro ao expandir linhas: {e}. Prosseguindo com a visualização padrão.") 

        # 4. Ciclo de Captura: Link -> Modal -> Download -> Z:
        print("💾 Iniciando captura de arquivos para o Drive Z...")
        links = await page.query_selector_all('a[onclick*="showSelectedDocument"]')
        
        processados = 0
        for link in links:
            texto_link = (await link.inner_text()).strip()
            # Limpa o nome para evitar erros de arquivo no Windows
            nome_limpo = "".join([c for c in texto_link if c.isalnum() or c in (' ', '_', '-')]).strip()

            if nome_limpo:
                try:
                    print(f"📄 Processando item: {nome_limpo}")
                    # Abre o modal de visualização
                    await link.click()
                    
                    # Espera o botão 'Baixar' interno do modal aparecer
                    await page.wait_for_selector('#documentViewDownloadButton', state="visible", timeout=15000)

                    # Intercepta o download gerado pelo botão do modal
                    async with page.expect_download(timeout=60000) as download_info:
                        await page.click('#documentViewDownloadButton')
                    
                    download = await download_info.value
                    
                    # Constrói o caminho final no drive Z
                    nome_final = f"{nome_limpo}.pdf"
                    caminho_final = os.path.join(CAMINHO_DESTINO, nome_final)
                    
                    # Salva o arquivo no destino definitivo
                    await download.save_as(caminho_final)
                    
                    print(f"✅ Salvo em Z: {nome_final}")
                    processados += 1

                    # Fecha o modal para liberar o próximo clique na tabela
                    await page.click('#documentViewBackButton')
                    await page.wait_for_selector('#documentView', state="hidden")

                except Exception as e:
                    print(f"❌ Falha no item {nome_limpo}: {e}")
                    # Garante que o modal feche mesmo em caso de erro
                    await page.keyboard.press("Escape")

        print(f"\n🚀 Automação concluída! {processados} arquivos salvos no Drive Z.")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(automate_osinfo())