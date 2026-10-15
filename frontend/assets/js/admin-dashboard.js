const token =
    sessionStorage.getItem('token');

const container =
    document.getElementById('solicitacoes');

if (!token) {

    window.location.href =
        '/pages/admin-login.html';

}

async function carregarSolicitacoes() {

    try {

        const resposta = await fetch(
            '/solicitacoes/pendentes',
            {
                headers: {
                    Authorization:
                        `Bearer ${token}`
                }
            }
        );

        if (resposta.status === 401) {

            sessionStorage.clear();

            window.location.href =
                '/pages/admin-login.html';

            return;
        }

        const solicitacoes =
            await resposta.json();

        container.innerHTML = '';

        if (solicitacoes.length === 0) {

            container.innerHTML =
                '<p>Nenhuma solicitação pendente.</p>';

            return;
        }

        solicitacoes.forEach(solicitacao => {

            const card =
                document.createElement('div');

            card.classList.add('solicitacao');

            card.innerHTML = `
                <h3>
                    ${solicitacao.estudante_nome}
                </h3>

                <p>
                    <strong>Matrícula:</strong>
                    ${solicitacao.matricula}
                </p>

                <p>
                    <strong>Responsável:</strong>
                    ${solicitacao.responsavel_nome ?? 'Não informado'}
                </p>

                <p>
                    <strong>Tipo:</strong>
                    ${solicitacao.tipo}
                </p>

                <p>
                    <strong>Justificativa:</strong>
                    ${solicitacao.justificativa}
                </p>

                <p>
                    <strong>Data:</strong>
                    ${solicitacao.data_solicitada ?? '-'}
                </p>

                <p>
                    <strong>Horário:</strong>
                    ${solicitacao.horario_solicitado ?? '-'}
                </p>

                <div class="acoes">

                    <button
                        class="aprovar"
                        onclick="analisar(
                            ${solicitacao.id},
                            'aprovar'
                        )"
                    >
                        Aprovar
                    </button>

                    <button
                        class="reprovar"
                        onclick="analisar(
                            ${solicitacao.id},
                            'reprovar'
                        )"
                    >
                        Reprovar
                    </button>

                </div>
            `;

            container.appendChild(card);

        });

    } catch (erro) {

        console.error(erro);

        container.innerHTML =
            '<p>Erro ao carregar solicitações.</p>';

    }

}

async function analisar(id, acao) {

    const observacao = prompt(
        'Observação da coordenação:'
    );

    if (observacao === null) {
        return;
    }

    try {

        const resposta = await fetch(
            `/solicitacoes/${id}/${acao}`,
            {

                method: 'PATCH',

                headers: {

                    'Content-Type':
                        'application/json',

                    Authorization:
                        `Bearer ${token}`

                },

                body: JSON.stringify({
                    observacao
                })

            }
        );

        const dados =
            await resposta.json();

        if (!resposta.ok) {

            alert(
                dados.erro ||
                'Erro ao analisar solicitação'
            );

            return;
        }

        alert(dados.mensagem);

        carregarSolicitacoes();

    } catch (erro) {

        console.error(erro);

        alert(
            'Erro ao conectar com o servidor'
        );

    }

}

document
    .getElementById('logout')
    .addEventListener('click', () => {

        sessionStorage.clear();

        window.location.href =
            '/pages/admin-login.html';

    });

carregarSolicitacoes();