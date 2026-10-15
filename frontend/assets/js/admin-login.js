const form = document.getElementById('login-form');
const erro = document.getElementById('erro');

form.addEventListener('submit', async (event) => {

    event.preventDefault();

    erro.textContent = '';

    const email = document.getElementById('email').value;
    const senha = document.getElementById('senha').value;

    try {

        const resposta = await fetch('/auth/login', {

            method: 'POST',

            headers: {
                'Content-Type': 'application/json'
            },

            body: JSON.stringify({
                email,
                senha
            })

        });

        const dados = await resposta.json();

        if (!resposta.ok) {

            erro.textContent =
                dados.erro || 'Erro ao realizar login';

            return;
        }

        sessionStorage.setItem(
            'token',
            dados.token
        );

        sessionStorage.setItem(
            'administrador',
            JSON.stringify(dados.administrador)
        );

        window.location.href =
            '/pages/admin-dashboard.html';

    } catch (error) {

        console.error(error);

        erro.textContent =
            'Não foi possível conectar ao servidor';

    }

});