import sqlite3
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash

class Medico:
    def __init__(self, id, nome, percentual_repasse):
        self.id = id
        self.nome = nome
        self.percentual_repasse = percentual_repasse

    def to_dict(self):
        return {
            "id": self.id,
            "nome": self.nome,
            "percentual_repasse": self.percentual_repasse
        }

class Atendimento:
    def __init__(self, id, medico: Medico, valor: float):
        self.id = id
        self.medico = medico
        self.valor = valor

    def calcular_repasse(self):
        return self.valor * (self.medico.percentual_repasse / 100)

    def to_dict(self):
        return {
            "id": self.id,
            "medico": self.medico.to_dict(),
            "valor": self.valor,
            "repasse": self.calcular_repasse()
        }

class Financeiro:
    def __init__(self):
        self.medicos = []
        self.atendimentos = []
        self._db_path = Path("database/medipay.db")
        self._inicializar_banco()
        self.carregar_dados()

    def _inicializar_banco(self):
        self._db_path.parent.mkdir(exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS medicos (
                id INTEGER PRIMARY KEY,
                nome TEXT NOT NULL,
                percentual_repasse REAL NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS atendimentos (
                id INTEGER PRIMARY KEY,
                medico_id INTEGER NOT NULL,
                valor REAL NOT NULL,
                FOREIGN KEY(medico_id) REFERENCES medicos(id)
            )
        ''')
        conn.commit()
        conn.close()

    def carregar_dados(self):
        self.medicos.clear()
        self.atendimentos.clear()
        conn = sqlite3.connect(self._db_path)
        for row in conn.execute("SELECT id, nome, percentual_repasse FROM medicos"):
            self.medicos.append(Medico(*row))
        for row in conn.execute("SELECT id, medico_id, valor FROM atendimentos"):
            at_id, med_id, valor = row
            medico = next((m for m in self.medicos if m.id == med_id), None)
            if medico:
                self.atendimentos.append(Atendimento(at_id, medico, valor))
        conn.close()

    def salvar_dados(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("DELETE FROM atendimentos")
        conn.execute("DELETE FROM medicos")

        for m in self.medicos:
            conn.execute(
                "INSERT INTO medicos (id, nome, percentual_repasse) VALUES (?, ?, ?)",
                (m.id, m.nome, m.percentual_repasse)
            )
        for a in self.atendimentos:
            conn.execute(
                "INSERT INTO atendimentos (id, medico_id, valor) VALUES (?, ?, ?)",
                (a.id, a.medico.id, a.valor)
            )
        conn.commit()
        conn.close()

    def cadastrar_medico(self, nome: str, percentual_repasse: float) -> Medico:
        medico_id = len(self.medicos) + 1
        medico = Medico(medico_id, nome, percentual_repasse)
        self.medicos.append(medico)
        self.salvar_dados()
        return medico

    def obter_medico_por_id(self, medico_id: int) -> Medico | None:
        return next((m for m in self.medicos if m.id == medico_id), None)

    def listar_medicos(self):
        return self.medicos

    def atualizar_medico(self, medico_id: int, nome: str = None, percentual_repasse: float = None) -> bool:
        medico = self.obter_medico_por_id(medico_id)
        if not medico:
            return False
        if nome is not None:
            medico.nome = nome
        if percentual_repasse is not None:
            medico.percentual_repasse = percentual_repasse
        self.salvar_dados()
        return True

    def remover_medico(self, medico_id: int) -> bool:
        medico = self.obter_medico_por_id(medico_id)
        if medico:
            self.medicos.remove(medico)
            self.salvar_dados()
            return True
        return False

    def registrar_atendimento(self, medico_id: int, valor: float) -> Atendimento | None:
        medico = self.obter_medico_por_id(medico_id)
        if not medico:
            return None
        atendimento_id = len(self.atendimentos) + 1
        atendimento = Atendimento(atendimento_id, medico, valor)
        self.atendimentos.append(atendimento)
        self.salvar_dados()
        return atendimento

    def listar_atendimentos(self):
        return self.atendimentos

    def relatorio_financeiro(self):
        total = sum(a.valor for a in self.atendimentos)
        total_repasse = sum(a.calcular_repasse() for a in self.atendimentos)
        return {
            "faturamento_total": total,
            "total_repasse": total_repasse,
            "lucro_liquido": total - total_repasse,
            "qtd_atendimentos": len(self.atendimentos),
            "qtd_medicos": len(self.medicos)
        }

financeiro = Financeiro()
app = Flask(__name__)
app.secret_key = "medipay-2025-segredo"

@app.route('/')
def index():
    # Passa as contagens para o template
    medicos_count = len(financeiro.listar_medicos())
    atendimentos_count = len(financeiro.listar_atendimentos())
    return render_template(
        'index.html',
        medicos_count=medicos_count,
        atendimentos_count=atendimentos_count
    )

@app.route('/medicos')
def listar_medicos():
    busca = request.args.get('busca', '').strip().lower()
    medicos = financeiro.listar_medicos()
    if busca:
        medicos = [m for m in medicos if busca in m.nome.lower()]
    return render_template('medicos.html', medicos=medicos)

@app.route('/medicos/novo', methods=['GET', 'POST'])
def novo_medico():
    if request.method == 'POST':
        nome = request.form['nome'].strip()
        try:
            perc = float(request.form['percentual'])
            if nome and perc >= 0:
                financeiro.cadastrar_medico(nome, perc)
                flash("✅ Médico cadastrado com sucesso!", "success")
                return redirect(url_for('listar_medicos'))
            else:
                flash("❌ Nome obrigatório e percentual ≥ 0.", "error")
        except ValueError:
            flash("❌ Percentual inválido.", "error")
    return render_template('medico_form.html', medico=None)

@app.route('/medicos/<int:id>/editar', methods=['GET', 'POST'])
def editar_medico(id):
    medico = financeiro.obter_medico_por_id(id)
    if not medico:
        flash("❌ Médico não encontrado.", "error")
        return redirect(url_for('listar_medicos'))
    if request.method == 'POST':
        nome = request.form['nome'].strip()
        try:
            perc = float(request.form['percentual'])
            if financeiro.atualizar_medico(id, nome, perc):
                flash("✅ Médico atualizado!", "success")
                return redirect(url_for('listar_medicos'))
            else:
                flash("❌ Erro ao atualizar.", "error")
        except ValueError:
            flash("❌ Percentual inválido.", "error")
    return render_template('medico_form.html', medico=medico)

@app.route('/medicos/<int:id>/excluir')
def excluir_medico(id):
    if financeiro.remover_medico(id):
        flash("🗑️ Médico excluído.", "success")
    else:
        flash("❌ Erro ao excluir médico.", "error")
    return redirect(url_for('listar_medicos'))

@app.route('/atendimentos')
def listar_atendimentos():
    return render_template('atendimentos.html', atendimentos=financeiro.listar_atendimentos())

@app.route('/atendimentos/novo', methods=['GET', 'POST'])
def novo_atendimento():
    if request.method == 'POST':
        try:
            medico_id = int(request.form['medico_id'])
            valor = float(request.form['valor'])
            if valor > 0:
                atendimento = financeiro.registrar_atendimento(medico_id, valor)
                if atendimento:
                    flash(f"✅ Atendimento registrado! Repasse: R$ {atendimento.calcular_repasse():.2f}", "success")
                    return redirect(url_for('listar_atendimentos'))
                else:
                    flash("❌ Médico inválido.", "error")
            else:
                flash("❌ Valor deve ser maior que zero.", "error")
        except (ValueError, KeyError):
            flash("❌ Dados inválidos.", "error")
    return render_template('atendimento_form.html', medicos=financeiro.listar_medicos())

@app.route('/relatorio')
def relatorio():
    dados = financeiro.relatorio_financeiro()
    dados["faturamento_total_fmt"] = f"R$ {dados['faturamento_total']:.2f}".replace('.', ',')
    dados["total_repasse_fmt"] = f"R$ {dados['total_repasse']:.2f}".replace('.', ',')
    dados["lucro_liquido_fmt"] = f"R$ {dados['lucro_liquido']:.2f}".replace('.', ',')
    return render_template('relatorio.html', **dados)

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)