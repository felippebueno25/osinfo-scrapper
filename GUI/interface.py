import tkinter as tk
from tkinter import ttk, messagebox
import threading
import asyncio
import datetime

# Importa as configurações do motor do robô
from terceiros import automate_osinfo, MESES_PT 

class Application:
    def __init__(self, root):
        self.root = root
        self.root.title("Robô OSINFO - Automação de Downloads")
        self.root.geometry("400x260")
        self.root.configure(padx=20, pady=20)
        
        # Centraliza a janela na tela
        self.root.eval('tk::PlaceWindow . center')

        # Estilo
        style = ttk.Style()
        style.configure("TButton", font=("Arial", 10, "bold"), padding=6)
        style.configure("TLabel", font=("Arial", 10))

        # Título
        ttk.Label(root, text="⚙️ Configuração de Extração", font=("Arial", 14, "bold")).pack(pady=(0, 20))

        # --- Mês ---
        frame_mes = ttk.Frame(root)
        frame_mes.pack(fill="x", pady=5)
        ttk.Label(frame_mes, text="Selecione o Mês:", width=15).pack(side="left")
        
        self.combo_mes = ttk.Combobox(frame_mes, values=MESES_PT, state="readonly", font=("Arial", 10))
        self.combo_mes.pack(side="left", fill="x", expand=True)
        # Define o mês atual como padrão
        mes_atual = datetime.datetime.now().month - 1 # Competencia passada
        self.combo_mes.current(mes_atual - 1) 

        # --- Ano ---
        frame_ano = ttk.Frame(root)
        frame_ano.pack(fill="x", pady=10)
        ttk.Label(frame_ano, text="Digite o Ano:", width=15).pack(side="left")
        
        self.entry_ano = ttk.Entry(frame_ano, font=("Arial", 10))
        self.entry_ano.pack(side="left", fill="x", expand=True)
        # Define o ano atual como padrão
        self.entry_ano.insert(0, str(datetime.datetime.now().year)) 

        # --- Botão Iniciar ---
        self.btn_iniciar = ttk.Button(root, text="🚀 INICIAR EXTRAÇÃO", command=self.iniciar_robo)
        self.btn_iniciar.pack(pady=20, fill="x")

        # Status
        self.lbl_status = ttk.Label(root, text="Pronto para iniciar.", foreground="gray", font=("Arial", 9))
        self.lbl_status.pack()

    def iniciar_robo(self):
        mes_nome = self.combo_mes.get()
        ano_alvo = self.entry_ano.get().strip()

        if not ano_alvo.isdigit() or len(ano_alvo) != 4:
            messagebox.showwarning("Atenção", "Por favor, digite um ano válido com 4 dígitos.")
            return

        mes_data_value = str(MESES_PT.index(mes_nome) + 1)

        # Atualiza a interface
        self.btn_iniciar.config(state="disabled")
        self.lbl_status.config(text="Robô em execução (Acompanhe pelo terminal negro).", foreground="blue")

        # Dispara a Thread para não travar o Tkinter
        thread = threading.Thread(
            target=self.rodar_playwright, 
            args=(ano_alvo, mes_data_value, mes_nome)
        )
        thread.daemon = True
        thread.start()

    def rodar_playwright(self, ano, mes, nome_mes):
        try:
            # Executa o loop assíncrono isolado
            asyncio.run(automate_osinfo(ano, mes, nome_mes)) # type:ignore
            self.root.after(0, self.finalizar_sucesso)
        except Exception as e:
            self.root.after(0, lambda: self.finalizar_erro(str(e)))

    def finalizar_sucesso(self):
        self.btn_iniciar.config(state="normal")
        self.lbl_status.config(text="✓ Processo finalizado com sucesso!", foreground="green")
        messagebox.showinfo("Concluído", "Todos os downloads foram finalizados com sucesso!")

    def finalizar_erro(self, erro_msg):
        self.btn_iniciar.config(state="normal")
        self.lbl_status.config(text="❌ Ocorreu um erro.", foreground="red")
        messagebox.showerror("Erro Crítico", f"O processo foi interrompido:\n\n{erro_msg}")


if __name__ == "__main__":
    root = tk.Tk()
    app = Application(root)
    root.mainloop()