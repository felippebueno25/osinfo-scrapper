import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import asyncio
import datetime
import os
import sys

# Garante que os módulos locais da pasta GUI_Geral sejam priorizados na importação
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from terceiros import automate_osinfo, MESES_PT

class Application:
    def __init__(self, root):
        self.root = root
        self.root.title("Robô OSINFO - Extração Geral de Arquivos Únicos")
        self.root.geometry("600x650") # Janela confortável para visualização do log
        self.root.eval('tk::PlaceWindow . center')

        style = ttk.Style()
        style.configure("TButton", font=("Arial", 10, "bold"), padding=6)
        style.configure("TLabel", font=("Arial", 10))

        ttk.Label(root, text="⚙️ Extração Massiva de Arquivos Únicos", font=("Arial", 14, "bold")).pack(pady=(15, 10))
        ttk.Label(root, text="Este módulo baixa 1 cópia de cada arquivo único (sem filtro de termos).", font=("Arial", 9, "italic"), foreground="gray").pack(pady=(0, 15))

        # --- Frame Principal para Agrupar os Campos ---
        frame_inputs = ttk.Frame(root)
        frame_inputs.pack(fill="x", padx=20)

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

        # --- Botão Iniciar ---
        self.btn_iniciar = ttk.Button(root, text="🚀 INICIAR EXTRAÇÃO DE ARQUIVOS ÚNICOS", command=self.iniciar_robo)
        self.btn_iniciar.pack(pady=15, padx=20, fill="x")

        # --- Console / Log ---
        ttk.Label(root, text="Log de Execução:").pack(anchor="w", padx=20)

        self.txt_log = scrolledtext.ScrolledText(root, height=16, bg="black", fg="lightgray", font=("Consolas", 9))
        self.txt_log.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        self.txt_log.config(state="disabled")

    def escrever_log(self, mensagem):
        """Função Thread-Safe para atualizar o log na tela"""
        def atualizar_texto():
            self.txt_log.config(state="normal")
            self.txt_log.insert(tk.END, mensagem + "\n")
            self.txt_log.see(tk.END)
            self.txt_log.config(state="disabled")

        self.root.after(0, atualizar_texto)

    def iniciar_robo(self):
        mes_nome = self.combo_mes.get()
        ano_alvo = self.entry_ano.get().strip()
        contrato_alvo = self.entry_contrato.get().strip()
        is_headless = self.var_headless.get()

        if not ano_alvo.isdigit() or len(ano_alvo) != 4:
            messagebox.showwarning("Atenção", "Por favor, digite um ano válido com 4 dígitos.")
            return
        if not contrato_alvo:
            messagebox.showwarning("Atenção", "O número do contrato é obrigatório.")
            return

        mes_data_value = str(MESES_PT.index(mes_nome) + 1)

        self.btn_iniciar.config(state="disabled")

        self.txt_log.config(state="normal")
        self.txt_log.delete(1.0, tk.END)
        self.txt_log.config(state="disabled")

        modo_str = "Headless (Oculto)" if is_headless else "Visível"
        self.escrever_log(f"Iniciando extração de arquivos únicos para {mes_nome}/{ano_alvo} - Contrato {contrato_alvo} [{modo_str}]...")

        thread = threading.Thread(
            target=self.rodar_playwright,
            args=(ano_alvo, mes_data_value, mes_nome, contrato_alvo, is_headless)
        )
        thread.daemon = True
        thread.start()

    def rodar_playwright(self, ano, mes, nome_mes, contrato, headless):
        try:
            asyncio.run(automate_osinfo(ano, mes, nome_mes, contrato, self.escrever_log, headless=headless)) # type:ignore
            self.root.after(0, self.finalizar_sucesso)
        except Exception as e:
            err_msg = str(e)
            self.root.after(0, lambda: self.finalizar_erro(err_msg))

    def finalizar_sucesso(self):
        self.btn_iniciar.config(state="normal")
        self.escrever_log("\n✓ Processo finalizado com sucesso!")
        messagebox.showinfo("Concluído", "Extração de arquivos únicos finalizada com sucesso!")

    def finalizar_erro(self, erro_msg):
        self.btn_iniciar.config(state="normal")
        self.escrever_log(f"\n❌ ERRO CRÍTICO: {erro_msg}")
        messagebox.showerror("Erro Crítico", f"O processo foi interrompido:\n\n{erro_msg}")


if __name__ == "__main__":
    root = tk.Tk()
    app = Application(root)
    root.mainloop()
