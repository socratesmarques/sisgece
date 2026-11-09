'use strict';
const container = document.getElementById('solicitacoes');
const aviso = document.getElementById('aviso');
async function api(path, options = {}) {
    const resposta = await fetch(path, { credentials: 'same-origin', ...options });
    if (resposta.status === 401) {
        window.location.replace('/pages/admin-login.html');
        throw new Error('Sessão expirada');
    }
    const dados = resposta.status === 204 ? null : await resposta.json();
    if (!resposta.ok) throw new Error(dados?.erro || 'Falha na requisição');
    return dados;
}
function linha(card, titulo, valor) {
    const p = document.createElement('p');
    const strong = document.createElement('strong');
    strong.textContent = titulo + ': ';
    p.append(strong, document.createTextNode(valor ?? '-'));
    card.append(p);
}
async function carregarSolicitacoes() {
    container.textContent = 'Carregando...';
    try {
        const historico = document.getElementById('historico').checked;
        const solicitacoes = await api(historico ? '/solicitacoes' : '/solicitacoes/pendentes');
        container.replaceChildren();
        if (!solicitacoes.length) container.textContent = 'Nenhuma solicitação encontrada.';
        for (const s of solicitacoes) {
            const card = document.createElement('article');
            card.className = 'solicitacao';
            const titulo = document.createElement('h3');
            titulo.textContent = s.estudante_nome;
            card.append(titulo);
            for (const [label, value] of [['Protocolo', s.id], ['Matrícula', s.matricula],
                ['Responsável', s.responsavel_nome], ['Tipo', s.tipo], ['Justificativa', s.justificativa],
                ['Data', s.data_solicitada?.slice(0, 10)], ['Horário', s.horario_solicitado], ['Status', s.status],
                ['Analisado por (ID)', s.administrador_id], ['Observação da coordenação', s.observacao_coordenacao]]) linha(card, label, value);
            if (s.status === 'PENDENTE') {
                const acoes = document.createElement('div');
                acoes.className = 'acoes';
                for (const [acao, label] of [['aprovar', 'Aprovar'], ['reprovar', 'Reprovar']]) {
                    const button = document.createElement('button');
                    button.className = acao;
                    button.textContent = label;
                    button.addEventListener('click', () => analisar(s.id, acao, acoes));
                    acoes.append(button);
                }
                card.append(acoes);
            }
            container.append(card);
        }
    } catch (erro) { container.textContent = erro.message; }
}
async function analisar(id, acao, acoes) {
    const observacao = prompt('Observação da coordenação (máximo 2000 caracteres):');
    if (observacao === null) return;
    acoes.querySelectorAll('button').forEach(b => { b.disabled = true; });
    try {
        await api(`/solicitacoes/${id}/${acao}`, { method: 'PATCH',
            headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ observacao }) });
        aviso.textContent = 'Decisão registrada.';
        await carregarSolicitacoes();
    } catch (erro) { aviso.textContent = erro.message; }
    finally { acoes.querySelectorAll('button').forEach(b => { b.disabled = false; }); }
}
document.getElementById('logout').addEventListener('click', async () => {
    try {
        await api('/auth/logout', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
        window.location.replace('/pages/admin-login.html');
    } catch (erro) { aviso.textContent = erro.message; }
});
document.getElementById('historico').addEventListener('change', carregarSolicitacoes);
document.getElementById('atualizar').addEventListener('click', carregarSolicitacoes);
document.getElementById('solicitacao-form').addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector('button');
    button.disabled = true;
    aviso.textContent = '';
    try {
        const data = Object.fromEntries(new FormData(form));
        const estudante = await api('/estudantes/' + encodeURIComponent(data.matricula.trim()));
        await api('/solicitacoes', { method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ estudante_id: estudante.id, tipo: data.tipo,
                justificativa: data.justificativa, data_solicitada: data.data_solicitada,
                horario_solicitado: data.horario_solicitado }) });
        form.reset();
        aviso.textContent = 'Solicitação salva no banco de dados.';
        await carregarSolicitacoes();
    } catch (erro) { aviso.textContent = erro.message; }
    finally { button.disabled = false; }
});
api('/auth/me').then(dados => {
    document.getElementById('usuario').textContent = dados.administrador.nome;
    return carregarSolicitacoes();
}).catch(erro => { aviso.textContent = erro.message; });
