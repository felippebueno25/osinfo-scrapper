import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import threading
import asyncio
import datetime
import os
import sys

# Garante que os módulos locais da pasta GUI_Geral sejam priorizados na importação
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from terceiros import automate_osinfo, MESES_PT, PASTA_OFICIAL_PADRAO

class Application:
    def __init__(self, root):
        self.root = root
        self.root.title("Robô OSINFO [CONTRATOS] - Extração Geral de Arquivos Únicos")
        self.root.geometry("640x700") # Janela confortável para visualização do formulário e log
        self.root.eval('tk::PlaceWindow . center')

        style = ttk.Style()
        style.configure("TButton", font=("Arial", 10, "bold"), padding=6)
        style.configure("TLabel", font=("Arial", 10))

        ttk.Label(root, text="⚙️ Extração Massiva de Arquivos Únicos [CONTRATOS]", font=("Arial", 14, "bold")).pack(pady=(15, 10))
        ttk.Label(root, text="Este módulo baixa 1 cópia de cada arquivo único em sua respectiva pasta de fornecedor.", font=("Arial", 9, "italic"), foreground="gray").pack(pady=(0, 15))

        # --- Frame Principal para Agrupar os Campos ---
        frame_inputs = ttk.Frame(root)
        frame_inputs.pack(fill="x", padx=20)

        # Pasta de Destino
        frame_pasta = ttk.Frame(frame_inputs)
        frame_pasta.pack(fill="x", pady=5)
        ttk.Label(frame_pasta, text="Pasta Destino:", width=15).pack(side="left")
        self.entry_pasta = ttk.Entry(frame_pasta, font=("Arial", 9))
        self.entry_pasta.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.entry_pasta.insert(0, PASTA_OFICIAL_PADRAO)
        self.btn_procurar = ttk.Button(frame_pasta, text="📁 Procurar...", command=self.selecionar_pasta)
        self.btn_procurar.pack(side="right")

        # Mês
        frame_mes = ttk.Frame(frame_inputs)
        frame_mes.pack(fill="x", pady=5)
        ttk.Label(frame_mes, text="Selecione o Mês:", width=15).pack(side="left")
        self.combo_mes = ttk.Combobox(frame_mes, values=MESES_PT, state="readonly", font=("Arial", 10))
        self.combo_mes.pack(side="left", fill="x", expand=True)
        self.combo_mes.current(datetime.datetime.now().month - 1)

        # Ano
        frame_ano = ttk.Frame(frame_inputs)
        frame_ano.pack(fill="x", pady=5)
        ttk.Label(frame_ano, text="Digite o Ano:", width=15).pack(side="left")
        self.entry_ano = ttk.Entry(frame_ano, font=("Arial", 10))
        self.entry_ano.pack(side="left", fill="x", expand=True)
        self.entry_ano.insert(0, str(datetime.datetime.now().year))

        # Contrato
        frame_contrato = ttk.Frame(frame_inputs)
        frame_contrato.pack(fill="x", pady=5)
        ttk.Label(frame_contrato, text="Nº do Contrato:", width=15).pack(side="left")
        self.entry_contrato = ttk.Entry(frame_contrato, font=("Arial", 10))
        self.entry_contrato.pack(side="left", fill="x", expand=True)
        self.entry_contrato.insert(0, "002/2021-52")

        # Headless Checkbox
        frame_headless = ttk.Frame(frame_inputs)
        frame_headless.pack(fill="x", pady=5)
        self.var_headless = tk.BooleanVar(value=True)
        self.chk_headless = ttk.Checkbutton(
            frame_headless,
            text="Executar navegador em segundo plano (Headless)",
            variable=self.var_headless
        )
        self.chk_headless.pack(side="left")

        # --- Botões Iniciar / Abortar ---
        frame_botoes = ttk.Frame(root)
        frame_botoes.pack(pady=15, padx=20, fill="x")

        self.btn_iniciar = ttk.Button(frame_botoes, text="🚀 INICIAR EXTRAÇÃO DE ARQUIVOS ÚNICOS", command=self.iniciar_robo)
        self.btn_iniciar.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.btn_abortar = ttk.Button(frame_botoes, text="⛔ ABORTAR", command=self.abortar_robo, state="disabled")
        self.btn_abortar.pack(side="right")

        self._abort_event = threading.Event()


        # --- Console / Log ---
        ttk.Label(root, text="Log de Execução:").pack(anchor="w", padx=20)

        self.txt_log = scrolledtext.ScrolledText(root, height=16, bg="black", fg="lightgray", font=("Consolas", 9))
        self.txt_log.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        self.txt_log.config(state="disabled")

    def selecionar_pasta(self):
        caminho_atual = self.entry_pasta.get().strip()
        inicial = caminho_atual if os.path.exists(caminho_atual) else os.path.expanduser("~")
        pasta_sel = filedialog.askdirectory(initialdir=inicial, title="Selecione a Pasta de Destino dos Contratos")
        if pasta_sel:
            self.entry_pasta.delete(0, tk.END)
            self.entry_pasta.insert(0, os.path.normpath(pasta_sel))

    def escrever_log(self, mensagem):
        """Função Thread-Safe para atualizar o log na tela"""
        def atualizar_texto():
            self.txt_log.config(state="normal")
            self.txt_log.insert(tk.END, mensagem + "\n")
            self.txt_log.see(tk.END)
            self.txt_log.config(state="disabled")

        self.root.after(0, atualizar_texto)

    def iniciar_robo(self):
        pasta_base = self.entry_pasta.get().strip()
        mes_nome = self.combo_mes.get()
        ano_alvo = self.entry_ano.get().strip()
        contrato_alvo = self.entry_contrato.get().strip()
        is_headless = self.var_headless.get()

        if not pasta_base:
            messagebox.showwarning("Atenção", "Por favor, especifique uma pasta de destino.")
            return

        if not os.path.exists(pasta_base):
            try:
                os.makedirs(pasta_base, exist_ok=True)
            except Exception as e:
                messagebox.showerror("Erro na Pasta", f"Não foi possível acessar ou criar a pasta de destino:\n{pasta_base}\n\nErro: {e}")
                return

        if not ano_alvo.isdigit() or len(ano_alvo) != 4:
            messagebox.showwarning("Atenção", "Por favor, digite um ano válido com 4 dígitos.")
            return
        if not contrato_alvo:
            messagebox.showwarning("Atenção", "O número do contrato é obrigatório.")
            return

        mes_data_value = str(MESES_PT.index(mes_nome) + 1)

        self._abort_event.clear()
        self.btn_iniciar.config(state="disabled")
        self.btn_abortar.config(state="normal")

        self.txt_log.config(state="normal")
        self.txt_log.delete(1.0, tk.END)
        self.txt_log.config(state="disabled")

        modo_str = "Headless (Oculto)" if is_headless else "Visível"
        self.escrever_log(f"Iniciando extração para {mes_nome}/{ano_alvo} - Contrato {contrato_alvo} [{modo_str}]...")
        self.escrever_log(f"Pasta base definida: '{pasta_base}'")

        thread = threading.Thread(
            target=self.rodar_playwright,
            args=(pasta_base, ano_alvo, mes_data_value, mes_nome, contrato_alvo, is_headless)
        )
        thread.daemon = True
        thread.start()

    def abortar_robo(self):
        self._abort_event.set()
        self.btn_abortar.config(state="disabled")
        self.escrever_log("\n[Abortar] Sinal de parada enviado. Aguardando o fim do download atual...")

    def rodar_playwright(self, pasta_base, ano, mes, nome_mes, contrato, headless):
        try:
            asyncio.run(automate_osinfo(
                ano_alvo=ano,
                mes_data_value=mes,
                nome_mes_pasta=nome_mes,
                contrato_alvo=contrato,
                log_callback=self.escrever_log,
                pasta_base=pasta_base,
                headless=headless,
                abort_event=self._abort_event,
            )) # type:ignore
            if self._abort_event.is_set():
                self.root.after(0, self.finalizar_abortado)
            else:
                self.root.after(0, self.finalizar_sucesso)
        except Exception as e:
            err_msg = str(e)
            self.root.after(0, lambda: self.finalizar_erro(err_msg))

    def finalizar_sucesso(self):
        self.btn_iniciar.config(state="normal")
        self.btn_abortar.config(state="disabled")
        self.escrever_log("\n✓ Processo finalizado com sucesso!")
        messagebox.showinfo("Concluído", "Extração de arquivos únicos finalizada com sucesso!")

    def finalizar_abortado(self):
        self.btn_iniciar.config(state="normal")
        self.btn_abortar.config(state="disabled")
        self.escrever_log("\n⛔ Processo abortado pelo usuário.")
        messagebox.showwarning("Abortado", "A extração foi interrompida pelo usuário.")

    def finalizar_erro(self, erro_msg):
        self.btn_iniciar.config(state="normal")
        self.btn_abortar.config(state="disabled")
        self.escrever_log(f"\n❌ ERRO CRÍTICO: {erro_msg}")
        messagebox.showerror("Erro Crítico", f"O processo foi interrompido:\n\n{erro_msg}")



if __name__ == "__main__":
    root = tk.Tk()
    app = Application(root)
    root.mainloop()
