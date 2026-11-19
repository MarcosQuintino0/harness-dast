# Usuários de teste

Contas sintéticas do ambiente de teste. Este arquivo traz só os apelidos, os papéis e os **nomes**
das variáveis de ambiente onde ficam o login e a senha de cada conta. Os valores não estão aqui:
o hdast os lê por referência (`env:NOME`).

| Apelido | Papel | Login (variável) | Senha (variável) |
| --- | --- | --- | --- |
| `user_a` | `user` (cliente comum) | `env:CRAPI_USER_A_EMAIL` | `env:CRAPI_USER_A_PASSWORD` |
| `user_b` | `user` (cliente comum) | `env:CRAPI_USER_B_EMAIL` | `env:CRAPI_USER_B_PASSWORD` |

- O login é `POST /identity/api/auth/login`, com `email` e `password` em JSON. O token vem no campo
  `token`.
- As duas contas têm o mesmo papel e já têm um veículo cadastrado cada uma.
